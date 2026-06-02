"""Web Agent Core - pobieranie stron przez Playwright (Premium)"""
from core.logging_setup import get_logger
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

log = get_logger(__name__)

class WebAgent:
    def __init__(self, config=None):
        self.config = config or {}

    def fetch_page(self, url: str) -> str:
        """Pobiera i zwraca tekst ze strony przy uyciu Playwright."""
        log.info(f"Pobieranie strony: {url}")
        if not sync_playwright:
            log.warning("Brak biblioteki playwright.")
            return "Błąd: Playwright nie jest zainstalowany."
            
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                # Pobierz widoczny tekst
                text_content = page.evaluate("() => document.body.innerText")
                browser.close()
                return text_content or f"Zwrócono pusta strone: {url}"
        except Exception as e:
            log.error(f"Błąd WebAgent podczas pobierania {url}: {e}")
            return f"Błąd pobierania strony: {e}"
