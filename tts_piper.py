"""Piper TTS integration."""
import os
import subprocess
from core.logging_setup import get_logger

log = get_logger(__name__)

class PiperTTS:
    def __init__(self, config=None):
        self.config = config or {}
        self.voice = self.config.get("voice", "pl-pl-default")
        self.enabled = self.config.get("enabled", True)
        
    def speak(self, text: str):
        if not self.enabled:
            return
        log.info(f"Odtwarzanie audio: {text[:20]}...")
        try:
            # Użycie pliku wykonywalnego piper. Oczekuje echo "tekst" | piper --model [model.onnx] --output_file out.wav
            model_path = self.config.get("model_path", "model.onnx")
            
            # W środowisku Jarvis, Piper typowo wywoływany w strumieniu, tu przykładowa wygenerowana komenda:
            cmd = f'echo "{text}" | piper --model {model_path} --output_file temp_speech.wav'
            log.info(f"Wywolano TTS Piper: {cmd}")
            subprocess.run(cmd, shell=True, check=False)
            
            # Następnie mozna to odtworzyć, np aplay w linux lub coś z play.
            try:
                import sounddevice as sd
                import soundfile as sf
                data, fs = sf.read("temp_speech.wav")
                sd.play(data, fs)
                sd.wait()
            except Exception:
                log.warning("Otworzenie dzwieku nie powiodlo sie, ale wygenerowano tts_piper.")
        except Exception as e:
            log.error(f"TTS piper blad: {e}")
