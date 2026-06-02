"""Wake Word Detector — openWakeWord."""
from __future__ import annotations
import threading
import time
from typing import Callable, Optional

from core.logging_setup import get_logger
log = get_logger(__name__)

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
    import sounddevice as sd
    import numpy as np
    _OWW_OK = True
except ImportError:
    _OWW_OK = False


class WakeWordDetector:
    """Nasłuchuje w tle na wake word i wywołuje callback."""

    def __init__(self, config):
        self.config = config
        self.on_detected: Optional[Callable] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._model = None
        self._available = False
        self._init()

    @property
    def available(self) -> bool:
        return self._available

    def _init(self):
        if not _OWW_OK:
            log.warning("Wake word: pip install openwakeword sounddevice")
            return
        try:
            model_name = getattr(self.config, "model", "hey_jarvis")
            openwakeword.utils.download_models([model_name])
            self._model = OWWModel(wakeword_models=[model_name], inference_framework="onnx")
            self._threshold = getattr(self.config, "threshold", 0.5)
            self._available = True
            log.info("Wake word: model '%s' załadowany (próg %.2f)", model_name, self._threshold)
        except Exception as e:
            log.warning("Wake word init: %s", e)

    def start(self):
        if not self._available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-ww")
        self._thread.start()
        log.info("Wake word: nasłuchuję…")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        sr = 16000
        chunk = int(sr * 0.08)
        device = getattr(self.config, "device", None)

        try:
            with sd.InputStream(samplerate=sr, channels=1, dtype="int16",
                                blocksize=chunk, device=device) as stream:
                while self._running:
                    audio, _ = stream.read(chunk)
                    audio_flat = audio.flatten().tolist()
                    self._model.predict(audio_flat)
                    scores = self._model.prediction_buffer
                    for name, buf in scores.items():
                        if buf and max(buf) >= self._threshold:
                            log.info("Wake word wykryty: %s (%.2f)", name, max(buf))
                            self._model.reset()
                            if self.on_detected:
                                threading.Thread(
                                    target=self.on_detected, daemon=True
                                ).start()
                            time.sleep(1.5)  # cooldown
                            break
        except Exception as e:
            log.error("Wake word loop: %s", e)
