"""STT — Speech To Text. Faster-Whisper z Vosk fallback."""
from __future__ import annotations
import os
import queue
import threading
import time
from typing import Optional

from core.logging_setup import get_logger
log = get_logger(__name__)

try:
    import sounddevice as sd
    import numpy as np
    _SD_OK = True
except ImportError:
    _SD_OK = False

try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except ImportError:
    _WHISPER_OK = False


class SpeechInput:
    """Nagrywa audio z mikrofonu i transkrybuje do tekstu."""

    def __init__(self, config):
        self.config = config
        self._model = None
        self._ready = False

    @property
    def available(self) -> bool:
        return self._ready

    def initialize(self) -> bool:
        if not _SD_OK:
            log.warning("STT: pip install sounddevice numpy")
            return False
        if not _WHISPER_OK:
            log.warning("STT: pip install faster-whisper")
            return False
        try:
            model_name = getattr(self.config, "whisper_model", "small")
            log.info("STT: ładuję Whisper '%s'…", model_name)
            self._model = WhisperModel(
                model_name, device="cpu",
                compute_type=getattr(self.config, "compute_type", "int8"),
                download_root=os.path.expanduser("~/.jarvis/whisper_models")
            )
            self._ready = True
            log.info("STT: Whisper '%s' gotowy", model_name)
            return True
        except Exception as e:
            log.error("STT init: %s", e)
            return False

    def listen_and_transcribe(self) -> Optional[str]:
        """Nagrywa do ciszy i transkrybuje. Zwraca tekst lub None."""
        if not self._ready:
            return None
        audio = self._record()
        if audio is None or len(audio) < 1000:
            return None
        return self._transcribe(audio)

    def _record(self) -> Optional[np.ndarray]:
        sr = getattr(self.config, "sample_rate", 16000)
        max_sec = getattr(self.config, "record_max_seconds", 12.0)
        silence_sec = getattr(self.config, "silence_seconds", 1.5)
        threshold = getattr(self.config, "silence_threshold", "auto")

        try:
            chunks = []
            silence_chunks = 0
            chunk_size = int(sr * 0.1)
            silence_needed = int(silence_sec / 0.1)

            if threshold == "auto":
                # Kalibracja szumu tła
                cal_sec = getattr(self.config, "calibration_seconds", 1.0)
                cal_data = sd.rec(int(sr * cal_sec), samplerate=sr, channels=1,
                                  dtype="float32")
                sd.wait()
                noise = float(np.abs(cal_data).mean())
                threshold = noise * 3.5

            log.debug("STT: nagrywam (threshold=%.4f)…", threshold)

            with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                blocksize=chunk_size) as stream:
                elapsed = 0.0
                started = False
                while elapsed < max_sec:
                    chunk, _ = stream.read(chunk_size)
                    level = float(np.abs(chunk).mean())
                    elapsed += chunk_size / sr

                    if level > threshold:
                        started = True
                        silence_chunks = 0
                        chunks.append(chunk.copy())
                    elif started:
                        silence_chunks += 1
                        chunks.append(chunk.copy())
                        if silence_chunks >= silence_needed:
                            break

            if not chunks:
                return None
            return np.concatenate(chunks, axis=0).flatten()

        except Exception as e:
            log.error("STT record: %s", e)
            return None

    def _transcribe(self, audio: "np.ndarray") -> Optional[str]:
        try:
            lang = getattr(self.config, "language", "pl")
            segments, info = self._model.transcribe(
                audio,
                language=lang,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500}
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            if text:
                log.debug("STT: '%s' (%.2fs)", text, info.duration)
            return text if text else None
        except Exception as e:
            log.error("STT transcribe: %s", e)
            return None
