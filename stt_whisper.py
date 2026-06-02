"""STT Whisper z obsługą mikrofonu (faster_whisper)"""
import os
import wave
import time
from typing import Optional

from core.logging_setup import get_logger

try:
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
except ImportError:
    np, sd, WhisperModel = None, None, None

log = get_logger(__name__)

class WhisperSTT:
    def __init__(self, config=None):
        self.config = config or {}
        self.model_size = self.config.get("model_size", "base")
        self.language = self.config.get("language", "pl")
        
        self.model = None
        if WhisperModel:
            log.info(f"Inicjalizacja WhisperSTT (model: {self.model_size})...")
            try:
                # "cpu" lub "cuda" w zależności od dostępności; domyślnie używamy compute_type="int8" na CPU 
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            except Exception as e:
                log.error(f"Nie udało się zainicjalizować WhisperModel: {e}")
        else:
            log.warning("Brak biblioteki faster_whisper lub sounddevice. STT nie zadziała poprawnie.")

    def listen(self, duration: int = 5, sample_rate: int = 16000) -> str:
        """Nasłuchuje z mikrofonu przez zadany czas i konwertuje na tekst."""
        if not sd or not self.model:
            log.warning("WhisperSTT_listen: Brak zaleznosci, zwracam pusty string.")
            return ""
            
        log.info(f"Nasłuch (Whisper STT)... mowi teraz, masz {duration} sekund.")
        try:
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
            sd.wait()
            
            # audio dla Whisper musi być 1D numpy array
            audio = np.squeeze(recording)
            
            log.info("Przetwarzanie audio...")
            segments, info = self.model.transcribe(audio, beam_size=5, language=self.language)
            
            text = " ".join([seg.text for seg in segments]).strip()
            log.info(f"Rozpoznano: {text}")
            return text
        except Exception as e:
            log.error(f"Błąd podczas nasłuchiwania: {e}")
            return ""

