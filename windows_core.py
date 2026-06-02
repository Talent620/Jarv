"""Windows Agent Core"""
from core.logging_setup import get_logger

log = get_logger(__name__)

class WindowsAgent:
    def launch_app(self, app_name: str) -> bool:
        log.info(f"Uruchamianie aplikacji: {app_name}")
        return True
        
    def close_app(self, app_name: str) -> bool:
        log.info(f"Zamykanie aplikacji: {app_name}")
        return True
    
    def take_screenshot(self) -> str:
        log.info("Wykonywanie zrzutu ekranu okna Windows")
        return "/tmp/screenshot.png"
