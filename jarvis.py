#!/usr/bin/env python3
"""Jarvis V2 — entry point.

Użycie:
  python jarvis.py              # domyślnie z config.toml
  python jarvis.py --text       # tryb tekstowy
  python jarvis.py --voice      # tryb głosowy
  python jarvis.py --web        # + panel webowy na :8080
  python jarvis.py --web --port 9090
  python jarvis.py --no-wake    # głosowy bez wake word
  python jarvis.py --debug      # więcej logów
"""
from __future__ import annotations
import argparse
import importlib
import pkgutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Jarvis AI V2")
    p.add_argument("--config",   type=Path, help="Ścieżka do config.toml")
    p.add_argument("--text",     action="store_true")
    p.add_argument("--voice",    action="store_true")
    p.add_argument("--web",      action="store_true")
    p.add_argument("--port",     type=int, default=8080)
    p.add_argument("--no-wake",  action="store_true")
    p.add_argument("--debug",    action="store_true")
    return p.parse_args()


def load_plugins():
    """Ładuje wszystkie actions/* — sam import rejestruje przez @registry.register."""
    try:
        import actions
        _SKIP = {
            "base", "timer_core", "todo_core", "health_core", "inventory_core",
            "scheduler_core", "calendar_core", "research_core",  # V3 — tylko core, actions osobno
        }
        import pkgutil
        import importlib
        for _, name, _ in pkgutil.iter_modules(actions.__path__):
            if name not in _SKIP:
                try:
                    importlib.import_module(f"actions.{name}")
                except Exception as e:
                    print(f"  [!] Plugin '{name}' błąd: {e}")
    except ImportError:
        pass # Ignoruj jeśli nie ma modułu actions
        
    # Bezpośredni import by załadować i zarejestrować intencje
    try:
        import project_actions
    except Exception as e:
        print(f"  [!] Project Actions błąd: {e}")
        
    # Integracje z akcjami
    try:
        import integrations.weather
    except Exception:
        pass


def build_context(args: argparse.Namespace):
    from core.config import Config
    from core.events import bus
    from core.context import AppContext
    from core.logging_setup import setup_logging

    cfg_path = args.config or Path("config.toml")
    if not cfg_path.exists():
        cfg_path = Path.home() / ".jarvis" / "config.toml"

    cfg = Config.load(cfg_path if cfg_path.exists() else None)
    if args.text:  cfg.ui.default_mode = "text"
    if args.voice: cfg.ui.default_mode = "voice"

    log_path = Path(cfg.logging.file).expanduser() if cfg.logging.file else None
    setup_logging(cfg.logging, debug=args.debug, log_path=log_path)

    from memory.store import MemoryStore
    from memory.learning import LearningEngine
    memory   = MemoryStore(cfg.memory)
    learning = LearningEngine(cfg.learning)

    from ai.ollama_client import OllamaClient
    ollama = OllamaClient(cfg.llm)

    ctx = AppContext(config=cfg, bus=bus, memory=memory, learning=learning, ollama=ollama)

    _setup_adaptation(ctx)
    _setup_voice(ctx, args)
    _setup_tools(ctx)
    _setup_integrations(ctx)
    _setup_v3(ctx)
    _setup_master_edition(ctx)
    _setup_agents_and_tools(ctx)
    return ctx


def _setup_master_edition(ctx):
    """Podłącza nowe moduły z Master Edition: User Profile, Project Memory itd."""
    try:
        from profile_core import UserProfile, ProfileConfig
        ctx.user_profile = UserProfile(ProfileConfig())
        print("  [✓] User Profile (Master Edition)")
    except Exception as e:
        print(f"  [!] User Profile: {e}")
        
    try:
        from project_core import ProjectMemory, ProjectConfig
        ctx.project_memory = ProjectMemory(ProjectConfig())
        print("  [✓] Project Memory (Master Edition)")
    except Exception as e:
        print(f"  [!] Project Memory: {e}")

def _setup_agents_and_tools(ctx):
    try:
        from tts_piper import PiperTTS
        ctx.piper = PiperTTS()
        
        from ocr_core import OCREngine
        ctx.ocr = OCREngine()
        
        from windows_core import WindowsAgent
        ctx.windows = WindowsAgent()
        
        from vision_core import VisionAgent
        ctx.vision = VisionAgent()
        
        from ha_client import HAClient
        ctx.ha = HAClient()
        
        from browser_core import WebAgent
        ctx.web = WebAgent()
        
        from orchestrator import Orchestrator
        ctx.orchestrator = Orchestrator(ctx)
        
        print("  [✓] Jarvis Agents & Tools Loaded")
    except Exception as e:
        print(f"  [!] Błąd ładowania agentów: {e}")

    try:
        from semantic_core import SemanticMemory
        ctx.semantic_memory = SemanticMemory()
        from stt_whisper import WhisperSTT
        ctx.stt_whisper = WhisperSTT()
        from ocr_premium import OCRPremium
        ctx.ocr_premium = OCRPremium()
        from ha_core import HACore
        ctx.ha_core = HACore()
        from deep_research import DeepResearch
        ctx.deep_research = DeepResearch()
        from model_router import ModelRouter
        ctx.model_router = ModelRouter()
        try:
            from autonomy import AutonomyEngine
            ctx.autonomy_engine = AutonomyEngine(ctx=ctx)
            if ctx.autonomy_engine:
                ctx.autonomy_engine.start()
        except Exception as e:
            print(f"  [!] Błąd Autonomii: {e}")
        print("  [✓] Jarvis MASTER PREMIUM Agents & Tools Loaded")
    except Exception as e:
        print(f"  [!] Błąd ładowania Premium agentów: {e}")

def _setup_adaptation(ctx):
    """Podłącza AdaptationEngine — aliasy komend i własne instrukcje."""
    try:
        from ai.adaptation import AdaptationEngine
        from pathlib import Path
        db = Path(ctx.config.learning.db_path).expanduser()
        ctx.adaptation = AdaptationEngine(db_path=db)
        print("  [✓] AdaptationEngine (aliasy + instrukcje)")
    except Exception as e:
        print(f"  [!] AdaptationEngine: {e}")


def _setup_v3(ctx):
    """Podłącza moduły V3: scheduler, calendar, research, history."""
    from pathlib import Path

    # ── APScheduler / Przypomnienia ──────────────────────────────────────
    sched_cfg = getattr(ctx.config, "scheduler", None)
    if sched_cfg and getattr(sched_cfg, "enabled", True):
        try:
            from actions.scheduler_core import ReminderScheduler

            def _remind(label: str):
                msg = f"🔔 Przypomnienie: {label}"
                import sys
                sys.stdout.write(f"\nJarvis: {msg}\n> ")
                sys.stdout.flush()
                ctx.bus.emit_async("system.alert", title="Przypomnienie", body=label)
                if ctx.tts:
                    ctx.tts.say(f"Przypomnienie: {label}")

            db = Path(getattr(sched_cfg, "db_path", "~/.jarvis/scheduler.db")).expanduser()
            ctx.scheduler = ReminderScheduler(db_path=db, notify_fn=_remind)
            print("  [✓] Scheduler (APScheduler) — przypomnienia")
        except Exception as e:
            print(f"  [!] Scheduler: {e}")

    # ── Kalendarz ────────────────────────────────────────────────────────
    cal_cfg = getattr(ctx.config, "calendar", None)
    if cal_cfg and getattr(cal_cfg, "enabled", True):
        try:
            from actions.calendar_core import CalendarEngine
            db = Path(getattr(cal_cfg, "db_path", "~/.jarvis/calendar.db")).expanduser()
            ctx.calendar = CalendarEngine(db_path=db)
            print("  [✓] Kalendarz")
        except Exception as e:
            print(f"  [!] Kalendarz: {e}")

    # ── Research ─────────────────────────────────────────────────────────
    res_cfg = getattr(ctx.config, "research", None)
    if res_cfg and getattr(res_cfg, "enabled", True):
        try:
            from actions.research_core import ResearchEngine

            def _research_notify(topic: str, summary: str):
                msg = f"📰 Research '{topic}' gotowy."
                import sys
                sys.stdout.write(f"\nJarvis: {msg}\n> ")
                sys.stdout.flush()
                if ctx.tts:
                    ctx.tts.say(f"Gotowy research na temat: {topic}")

            db = Path(getattr(res_cfg, "db_path", "~/.jarvis/research.db")).expanduser()
            ctx.research = ResearchEngine(
                db_path=db,
                ollama=ctx.ollama,
                notify_fn=_research_notify,
            )
            print("  [✓] Research (codzienny research tematów)")
        except Exception as e:
            print(f"  [!] Research: {e}")

    # ── Historia rozmów ──────────────────────────────────────────────────
    hist_cfg = getattr(ctx.config, "history", None)
    if hist_cfg and getattr(hist_cfg, "enabled", True):
        try:
            from actions.history_actions import HistoryStore
            db = Path(getattr(hist_cfg, "db_path", "~/.jarvis/history.db")).expanduser()
            max_e = getattr(hist_cfg, "max_entries", 1000)
            ctx.history_store = HistoryStore(db_path=db, max_entries=max_e)
            print("  [✓] Historia rozmów")
        except Exception as e:
            print(f"  [!] Historia: {e}")


def _setup_voice(ctx, args):
    if ctx.config.ui.default_mode != "voice" and not args.voice:
        return
    try:
        from voice.stt import SpeechInput
        from voice.tts import SpeechOutput
        stt = SpeechInput(ctx.config.speech)
        tts = SpeechOutput(ctx.config.tts)
        if not stt.initialize():
            print("  [!] STT niedostępny — tryb tekstowy")
            ctx.config.ui.default_mode = "text"
            return
        tts.initialize()
        ctx.stt = stt
        ctx.tts = tts
    except Exception as e:
        print(f"  [!] Voice init: {e}")
        ctx.config.ui.default_mode = "text"
        return

    if not args.no_wake:
        try:
            ww_cfg = getattr(ctx.config, "wake_word", None)
            if ww_cfg and getattr(ww_cfg, "enabled", False):
                from voice.wake_word import WakeWordDetector
                ww = WakeWordDetector(ww_cfg)
                if ww.available:
                    ctx.wake_word = ww
                    print("  [✓] Wake word aktywny")
        except Exception as e:
            print(f"  [!] Wake word: {e}")


def _setup_tools(ctx):
    # Timer
    try:
        from actions.timer_core import TimerManager
        ctx.timer_manager = TimerManager()
        print("  [✓] Timer Manager")
    except Exception as e:
        print(f"  [!] Timer: {e}")

    # TODO
    try:
        from actions.todo_core import TodoTool, TodoConfig
        db = Path(ctx.config.learning.db_path).expanduser()
        ctx.todo_tool = TodoTool(TodoConfig(db_path=str(db)))
        print("  [✓] TODO Tool")
    except Exception as e:
        print(f"  [!] TODO: {e}")

    # Inventory
    inv_cfg = getattr(ctx.config, "inventory", None)
    if inv_cfg and getattr(inv_cfg, "enabled", False):
        try:
            from actions.inventory_core import InventoryTool, InventoryConfig
            ctx.inventory_tool = InventoryTool(InventoryConfig(
                db_path=str(Path(inv_cfg.db_path).expanduser()),
                auto_fetch=getattr(inv_cfg, "auto_fetch", False),
            ))
            print("  [✓] Inventory Tool")
        except Exception as e:
            print(f"  [!] Inventory: {e}")

    # Health Monitor
    try:
        from actions.health_core import HealthMonitor, HealthConfig

        def _alert(title, body="", source="system", **_):
            ctx.bus.emit_async("system.alert", title=title, body=body, source=source)
            if ctx.tts:
                ctx.tts.say(f"Uwaga: {title}")

        hm = HealthMonitor(HealthConfig())
        hm.alert_fn = _alert
        hm.start()
        ctx.health_monitor = hm
        print("  [✓] Health Monitor")
    except Exception as e:
        print(f"  [!] Health Monitor: {e}")


def _setup_integrations(ctx):
    esp_cfg = getattr(ctx.config, "esp32", None)
    if esp_cfg and getattr(esp_cfg, "enabled", False):
        try:
            from integrations.esp32 import ESP32Controller, DevicePin

            class _Cfg:
                pass

            c = _Cfg()
            c.enabled       = True
            c.host          = esp_cfg.host
            c.timeout       = getattr(esp_cfg, "timeout", 3.0)
            c.max_volts     = getattr(esp_cfg, "max_volts", 12.0)
            c.mqtt_enabled  = getattr(esp_cfg, "mqtt_enabled", False)
            c.mqtt_broker   = getattr(esp_cfg, "mqtt_broker", "")
            c.mqtt_port     = getattr(esp_cfg, "mqtt_port", 1883)
            c.mqtt_username = getattr(esp_cfg, "mqtt_username", "")
            c.mqtt_password = getattr(esp_cfg, "mqtt_password", "")
            c.mqtt_topic_cmd    = getattr(esp_cfg, "mqtt_topic_cmd", "jarvis/command")
            c.mqtt_topic_status = getattr(esp_cfg, "mqtt_topic_status", "jarvis/status")

            raw_devs = getattr(esp_cfg, "devices", [])
            if raw_devs:
                c.devices = [
                    DevicePin(
                        name=d.get("name", f"device_{i}"),
                        pin=int(d.get("pin", i+2)),
                        type=d.get("type", "relay"),
                        aliases=d.get("aliases", []),
                        inverted=d.get("inverted", False),
                    )
                    for i, d in enumerate(raw_devs)
                ]
            else:
                from integrations.esp32 import DevicePin as DP
                c.devices = [
                    DP("przekaznik_1", 2, "relay", ["przekaźnik", "relay 1"]),
                    DP("przekaznik_2", 4, "relay", ["relay 2"]),
                    DP("led",         5, "pwm",   ["światło","lampa"]),
                    DP("pompa",      16, "relay", ["woda","nawadnianie"]),
                    DP("wentylator", 17, "relay", ["wentylacja","chłodzenie"]),
                ]

            ctx.esp32 = ESP32Controller(c)
            print(f"  [✓] ESP32: {esp_cfg.host} ({len(c.devices)} urządzeń)")
        except Exception as e:
            print(f"  [!] ESP32: {e}")

    # Telegram
    tg_cfg = getattr(ctx.config, "telegram", None)
    if tg_cfg and getattr(tg_cfg, "enabled", False):
        print("  [i] Telegram: skonfiguruj integrations/telegram.py")


def banner(ctx):
    ollama_ok = False
    model_ok  = False
    try:
        ollama_ok = ctx.ollama.is_running()
        model_ok  = ollama_ok and ctx.ollama.has_model()
    except Exception:
        pass

    print(f"""
╔══════════════════════════════════════════╗
║          ⚡  JARVIS  V2.0                ║
╠══════════════════════════════════════════╣
║  Tryb:     {ctx.config.ui.default_mode:<30} ║
║  Ollama:   {'✓ ' + ctx.config.llm.model if ollama_ok else '✗ nie odpowiada':<30} ║
║  Model:    {'✓ gotowy' if model_ok else '✗ brak — patrz niżej':<30} ║
║  Pamięć:   {ctx.memory.count()} wpisów{'':<23} ║
║  ESP32:    {'✓ ' + getattr(getattr(ctx.config,'esp32',None),'host','') if ctx.has('esp32') else '—':<30} ║
╚══════════════════════════════════════════╝
""")
    if not ollama_ok:
        print("  [!] Uruchom Ollama: ollama serve")
        print(f"  [!] Pobierz model:  ollama pull {ctx.config.llm.model}")


def main() -> int:
    args = parse_args()
    print("⚡ Jarvis V2 — ładowanie…")

    load_plugins()
    ctx = build_context(args)
    banner(ctx)

    if args.web:
        try:
            from web.server import JarvisWebServer
            srv = JarvisWebServer(ctx, host="0.0.0.0", port=args.port)
            srv.start_background()
            print(f"  [✓] Panel webowy: http://localhost:{args.port}")
        except Exception as e:
            print(f"  [!] Web panel: {e}")

    from core.assistant import JarvisAssistant
    assistant = JarvisAssistant(ctx)
    try:
        assistant.start()
    except KeyboardInterrupt:
        pass
    finally:
        if ctx.tts:
            ctx.tts.shutdown()
        if ctx.has("health_monitor"):
            try: ctx.health_monitor.stop()
            except Exception: pass
        if ctx.has("wake_word"):
            try: ctx.wake_word.stop()
            except Exception: pass
        if ctx.has("scheduler"):
            try: ctx.scheduler.shutdown()
            except Exception: pass
        if ctx.has("research"):
            try: ctx.research.shutdown()
            except Exception: pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
