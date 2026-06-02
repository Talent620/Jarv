"""TTS — async, nie blokuje głównego wątku."""
from __future__ import annotations
import queue
import threading
import time
from typing import Optional

from core.logging_setup import get_logger
log = get_logger(__name__)

try:
    import pyttsx3
    _PYTTSX3_OK = True
except ImportError:
    _PYTTSX3_OK = False

try:
    from TTS.api import TTS as CoquiTTS
    _COQUI_OK = True
except ImportError:
    _COQUI_OK = False

_STOP = object()


class SpeechOutput:
    """Async TTS z kolejką. say() wraca natychmiast."""

    def __init__(self, config):
        self.config = config
        self._queue: queue.Queue = queue.Queue()
        self._muted = threading.Event()
        self._ready = False
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._coqui = None
        self._backend = "none"

    @property
    def available(self) -> bool:
        return self._ready

    def initialize(self) -> bool:
        use_coqui = getattr(self.config, "use_coqui", False)
        if use_coqui and _COQUI_OK:
            if self._init_coqui():
                self._backend = "coqui"

        if self._backend == "none" and _PYTTSX3_OK:
            if self._init_pyttsx3():
                self._backend = "pyttsx3"

        if self._backend == "none":
            log.warning("TTS: brak backendu. Zainstaluj pyttsx3.")
            return False

        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jarvis-tts")
        self._thread.start()
        log.info("TTS gotowy (%s)", self._backend)
        return True

    def _init_pyttsx3(self) -> bool:
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate",   getattr(self.config, "rate", 175))
            engine.setProperty("volume", getattr(self.config, "volume", 1.0))
            self._set_polish_voice(engine)
            self._engine = engine
            return True
        except Exception as e:
            log.warning("pyttsx3 init: %s", e)
            return False

    def _init_coqui(self) -> bool:
        try:
            model = getattr(self.config, "coqui_model", "tts_models/pl/mai_female/vits")
            self._coqui = CoquiTTS(model, progress_bar=False, gpu=False)
            return True
        except Exception as e:
            log.warning("Coqui init: %s", e)
            return False

    def _set_polish_voice(self, engine) -> None:
        prefs = [p.lower() for p in getattr(self.config, "prefer_voice_contains", ["polish","pl"])]
        try:
            for v in engine.getProperty("voices"):
                desc = (str(getattr(v,"name","")) + " " + str(getattr(v,"id",""))).lower()
                if any(p in desc for p in prefs):
                    engine.setProperty("voice", v.id)
                    log.info("TTS głos: %s", getattr(v,"name",v.id))
                    return
        except Exception:
            pass

    def say(self, text: str) -> None:
        if text and self._ready:
            self._queue.put(text)

    say_async = say

    def interrupt(self) -> None:
        """Przerywa bieżącą wypowiedź i czyści kolejkę (TTS stop)."""
        # Opróżnij kolejkę
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break
        # Zatrzymaj silnik (jeśli pyttsx3)
        if self._backend == "pyttsx3" and self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
        log.info("TTS: przerwano wypowiedź")

    def mute(self):   self._muted.set()
    def unmute(self): self._muted.clear()

    def shutdown(self):
        self._queue.put(_STOP)
        if self._thread:
            self._thread.join(timeout=3)
        if self._engine:
            try: self._engine.stop()
            except Exception: pass

    def _loop(self):
        while True:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is _STOP:
                break
            while self._muted.is_set():
                time.sleep(0.05)
            try:
                if self._backend == "coqui":
                    self._speak_coqui(item)
                else:
                    self._speak_pyttsx3(item)
            except Exception as e:
                log.exception("TTS speak: %s", e)

    def _speak_pyttsx3(self, text: str):
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except RuntimeError:
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate",   getattr(self.config, "rate", 175))
                self._engine.setProperty("volume", getattr(self.config, "volume", 1.0))
                self._set_polish_voice(self._engine)
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                log.error("pyttsx3 restart: %s", e)

    def _speak_coqui(self, text: str):
        """Synteza Coqui — cross-platform (sounddevice/soundfile zamiast aplay)."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        try:
            self._coqui.tts_to_file(text=text, file_path=tmp)
            # Odtwarzanie cross-platform (Linux + Windows + Mac)
            try:
                import soundfile as sf
                import sounddevice as sd
                data, samplerate = sf.read(tmp)
                sd.play(data, samplerate)
                sd.wait()
            except ImportError:
                # Fallback: subprocess
                import subprocess, sys
                if sys.platform == "win32":
                    subprocess.run(["powershell", "-c",
                                    f"(New-Object Media.SoundPlayer '{tmp}').PlaySync()"],
                                   capture_output=True, timeout=30)
                elif sys.platform == "darwin":
                    subprocess.run(["afplay", tmp], check=False, capture_output=True, timeout=30)
                else:
                    subprocess.run(["aplay", tmp], check=False, capture_output=True, timeout=30)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
