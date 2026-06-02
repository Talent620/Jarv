"""JarvisAssistant V3 — slim orchestrator.

Nowe w V3:
- AdaptationEngine wstrzykiwany do system promptu (aliasy + własne instrukcje)
- HistoryStore — każda para (user→assistant) trafia do SQLite
- TTS_STOP — przerwij wypowiedź komendą głosową lub tekstową
- Historia, kalendarz, przypomnienia, research — przez registry
"""
from __future__ import annotations
import sys
import time
from typing import List, Optional

from core.context import AppContext
from core.events import E, EventBus
from core.registry import registry
from core.logging_setup import get_logger
from ai.intent import IntentDetector, Intent, IntentType
from actions.base import ActionResult

log = get_logger(__name__)


class JarvisAssistant:

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.intents = IntentDetector()
        self._running = False
        self._mode = ctx.config.ui.default_mode
        self._history: List[dict] = []

        bus = ctx.bus
        bus.subscribe(E.TEXT_INPUT,    self._on_text_input)
        bus.subscribe(E.WAKE_DETECTED, self._on_wake_detected)
        bus.subscribe(E.SPEAK,         self._on_speak)

    def start(self) -> None:
        self._running = True
        if self._mode == "voice" and self.ctx.wake_word:
            self.ctx.wake_word.on_detected = lambda: self.ctx.bus.emit(E.WAKE_DETECTED)
            self.ctx.wake_word.start()
            log.info("Tryb głosowy z wake word")
            self._greet()
            self._idle_loop()
        else:
            self._text_loop()

    def stop(self) -> None:
        self._running = False
        if self.ctx.wake_word:
            self.ctx.wake_word.stop()

    def _text_loop(self) -> None:
        self._greet()
        while self._running:
            try:
                tekst = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                self._say(f"Do zobaczenia, {self.ctx.config.ui.user_name}.")
                break
            if tekst:
                self.ctx.bus.emit(E.TEXT_INPUT, text=tekst, source="cli")

    def _idle_loop(self) -> None:
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self._say(f"Do zobaczenia, {self.ctx.config.ui.user_name}.")

    def _on_wake_detected(self, **_) -> None:
        if not self.ctx.stt:
            return
        if self.ctx.tts:
            self.ctx.tts.mute()
        tekst = self.ctx.stt.listen_and_transcribe()
        if self.ctx.tts:
            self.ctx.tts.unmute()
        if tekst:
            log.info("STT: %r", tekst)
            self.ctx.bus.emit(E.TEXT_INPUT, text=tekst, source="voice")

    def _on_text_input(self, text: str = "", source: str = "cli", **_) -> None:
        sys.stdout.write(f"\n{self.ctx.config.ui.user_name}: {text}\n")
        sys.stdout.flush()

        # ── Rozwiń aliasy (AdaptationEngine) ────────────────────────────
        original_text = text
        try:
            if self.ctx.has("adaptation") and self.ctx.adaptation:
                text, used_aliases = self.ctx.adaptation.expand_aliases(text)
                if used_aliases:
                    log.debug("Aliasy użyte: %s", used_aliases)
        except Exception:
            pass

        intent = self.intents.detect(text)
        self.ctx.bus.emit(E.INTENT_DETECTED, intent=intent)
        result = self._dispatch(intent)
        if result:
            self._output(result, user_text=original_text)

    def _on_speak(self, text: str = "", **_) -> None:
        if self.ctx.tts:
            self.ctx.tts.say(text)

    def _dispatch(self, intent: Intent) -> Optional[ActionResult]:
        # ── TTS STOP — najwyższy priorytet ──────────────────────────────
        if intent.typ == IntentType.TTS_STOP:
            if self.ctx.tts:
                self.ctx.tts.interrupt()
                return ActionResult(".", speak=False)
            return None

        if intent.typ.value == "exit":
            self._say(f"Do zobaczenia, {self.ctx.config.ui.user_name}.")
            self._running = False
            return None

        # Sprawdź custom typ (z register_pattern dla stringów)
        custom_typ = getattr(intent, "_custom_typ", None)
        intent_key = custom_typ if custom_typ else intent.typ.value
        action_cls = registry.get(intent_key)
        if action_cls is None:
            return self._chat_fallback(intent)

        action = action_cls()
        if not action.can_handle(intent, self.ctx):
            return ActionResult("Nie mogę wykonać tej akcji.", success=False)

        try:
            self.ctx.bus.emit(E.ACTION_START, intent=intent)
            result = action.run(intent, self.ctx)
            self.ctx.bus.emit(E.ACTION_DONE, intent=intent, result=result)
            return result
        except Exception as e:
            log.exception("Akcja %s: %s", action_cls.__name__, e)
            self.ctx.bus.emit(E.ACTION_ERROR, intent=intent, error=e)
            return ActionResult("Coś poszło nie tak. Sprawdź logi.", success=False)

    def _chat_fallback(self, intent: Intent) -> ActionResult:
        from ai.ollama_client import OllamaError
        from ai.prompt import build_system_prompt, build_user_message, MemoryHit

        if not self.ctx.ollama.is_running():
            return ActionResult(
                "Ollama nie odpowiada. Uruchom: ollama serve", success=False
            )

        hits = []
        for w in self.ctx.memory.search(intent.surowy_tekst, limit=3):
            hits.append(MemoryHit(tresc=w.tresc, kategoria=w.kategoria,
                                  data=getattr(w, "data", "")))

        # ── Master Edition: User Profile & Project Context ─────────
        user_profile_summary = ""
        project_context = ""
        try:
            if self.ctx.has("user_profile"):
                user_profile_summary = self.ctx.user_profile.get_profile_summary()
            if self.ctx.has("project_memory"):
                project_context = self.ctx.project_memory.get_active_context()
        except Exception as e:
            log.warning(f"Błąd przy pobieraniu kontekstu Master Edition: {e}")

        # ── Adaptation: style + instrukcje użytkownika ───────────────────
        style_directive = ""
        user_instructions = ""
        try:
            if self.ctx.has("adaptation"):
                style_directive = self.ctx.adaptation.style_directive()
                user_instructions = self.ctx.adaptation.instructions_block()
        except Exception:
            pass

        system_msg = build_system_prompt(
            user_name=self.ctx.config.ui.user_name,
            user_instructions=user_instructions,
            style_directive=style_directive,
            user_profile=user_profile_summary,
            project_context=project_context,
        )
        user_msg = build_user_message(
            pytanie=intent.surowy_tekst,
            pamiec_hits=hits,
            user_name=self.ctx.config.ui.user_name,
        )

        from ai.ollama_client import ChatMessage
        messages = [
            ChatMessage("system", system_msg),
            *[ChatMessage(m["role"], m["content"]) for m in self._history[-20:]],
            ChatMessage("user", user_msg),
        ]

        try:
            odp = self.ctx.ollama.chat(messages)
        except OllamaError as e:
            return ActionResult(str(e), success=False)

        self._history.append({"role": "user",      "content": intent.surowy_tekst})
        self._history.append({"role": "assistant", "content": odp})
        while len(self._history) > getattr(self.ctx.config.ui, "history_size", 20) * 2:
            self._history.pop(0)

        # ── Proaktywna sugestia adaptacji ───────────────────────────────
        try:
            if self.ctx.has("adaptation"):
                sugestia = self.ctx.adaptation.suggest_adaptation()
                if sugestia:
                    _, opis, _ = sugestia
                    log.info("Sugestia adaptacji: %s", opis)
        except Exception:
            pass

        return ActionResult(odp)

    def _output(self, result: ActionResult, user_text: str = "") -> None:
        sys.stdout.write(f"Jarvis: {result.text}\n\n")
        sys.stdout.flush()
        if result.speak and result.text:
            self.ctx.bus.emit(E.SPEAK, text=result.text)
        self.ctx.bus.emit_async(E.WEB_PUSH, event="response", data={
            "text": result.text, "success": result.success, "data": result.data,
        })

        # ── Zapisz do historii ───────────────────────────────────────────
        if user_text and result.text and self.ctx.has("history_store"):
            try:
                self.ctx.history_store.save(
                    user_msg=user_text,
                    assistant_msg=result.text,
                )
            except Exception as e:
                log.debug("Zapis historii: %s", e)

    def _say(self, text: str) -> None:
        sys.stdout.write(f"Jarvis: {text}\n\n")
        sys.stdout.flush()
        self.ctx.bus.emit(E.SPEAK, text=text)

    def _greet(self) -> None:
        ile = self.ctx.memory.count()
        name = self.ctx.config.ui.user_name
        if ile == 0:
            self._say(f"Cześć, {name}. Jestem Jarvis. Pamięć pusta — zaczynamy od zera.")
        else:
            self._say(f"Cześć, {name}. Pamiętam {ile} rzeczy. W czym pomóc?")
