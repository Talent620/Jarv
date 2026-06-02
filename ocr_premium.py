"""OCR Premium - Tesseract"""
import os
try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image, pytesseract = None, None

from core.logging_setup import get_logger

log = get_logger(__name__)

class OCRPremium:
    def __init__(self, config=None):
        self.config = config or {}
        
    def scan(self, source: str) -> str:
        if not Image or not pytesseract:
            log.warning("Brak bibliotek PIL lub pytesseract. OCR nie zadziała.")
            return "Brak wymaganych bibliotek OCR."
            
        log.info(f"OCR działanie na: {source}")
        
        if not os.path.exists(source):
            return f"Błąd: Plik docelowy nie istnieje '{source}'."
            
        try:
            image = Image.open(source)
            text = pytesseract.image_to_string(image, lang='pol+eng')
            return text.strip()
        except Exception as e:
            log.error(f"Błąd OCR podczas skanowania {source}: {e}")
            return f"Błąd OCR: {e}"
