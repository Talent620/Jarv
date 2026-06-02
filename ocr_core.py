"""OCR Core"""
from core.logging_setup import get_logger

log = get_logger(__name__)

class OCREngine:
    def __init__(self, config=None):
        self.config = config or {}
        
    def scan_image(self, path: str) -> str:
        log.info(f"Skanowanie obrazu: {path}")
        return f"Przykładowy tekst z obrazu {path}"
        
    def scan_screenshot(self) -> str:
        log.info("Skanowanie zrzutu ekranu")
        return "Przykładowy tekst ze zrzutu ekranu"
