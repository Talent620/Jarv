"""Vision Agent Core - analiza obrazu przy uyciu LlamaVision"""
import base64
import requests
import os
from core.logging_setup import get_logger

log = get_logger(__name__)

class VisionAgent:
    def __init__(self, config=None, ctx=None):
        self.config = config or {}
        self.ctx = ctx
        self.model = self.config.get("model", "llama3.2-vision")
        self.host = "http://localhost:11434"
        if self.ctx and self.ctx.has("config"):
            self.host = self.ctx.config.llm.host.rstrip("/")

    def _encode_image(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def analyze_image(self, path: str, prompt: str = "Opisz ten obraz krótko i zwięźle.") -> str:
        log.info(f"Analiza obrazu: {path}")
        if not os.path.exists(path):
            return f"Błąd: {path} nie istnieje."
            
        try:
            b64_img = self._encode_image(path)
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [b64_img],
                "stream": False
            }
            resp = requests.post(f"{self.host}/api/generate", json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json().get("response", "Brak odpowiedzi od modelu vision.")
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 404:
                return f"Błąd: Model '{self.model}' jest niedostępny. (ollama pull {self.model})"
            return f"HTTP Błąd Ollama: {e}"
        except Exception as e:
            log.error(f"Błąd VisionAgent: {e}")
            return f"Wystąpił błąd analizy wizyjnej: {e}"
