"""Windows Agent - kontrola systemu OS Windows (uruchamianie i zamykanie aplikacji)"""
import os
import subprocess
try:
    import psutil
except ImportError:
    psutil = None

from core.logging_setup import get_logger

log = get_logger(__name__)

class WindowsAgent:
    def __init__(self, config=None):
        self.config = config or {}

    def launch_app(self, app_name: str) -> bool:
        """Uruchamia podaną aplikacje (przez start w Windows)."""
        log.info(f"Otwieranie programu: {app_name}")
        try:
            # shell=True i 'start' dziala na sztywno dla Windows
            subprocess.Popen(f"start {app_name}", shell=True)
            return True
        except Exception as e:
            log.error(f"Nie udało się otworzyć programu {app_name}: {e}")
            return False

    def close_app(self, app_name: str) -> bool:
        """Próbuje zamknąć dany proces po nazwie."""
        log.info(f"Zamykanie programu: {app_name}")
        if not psutil:
            log.warning("Brak modułu psutil.")
            return False
            
        killed_any = False
        target_lower = app_name.lower().replace(".exe", "")
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                name = proc.info.get('name')
                if name and target_lower in name.lower():
                    proc.terminate()
                    killed_any = True
            
            if killed_any:
                log.info(f"Zamknięto procesy pasujące do: {app_name}")
            return killed_any
        except Exception as e:
            log.error(f"Błąd podczas zamykania {app_name}: {e}")
            return False
            
    def take_screenshot(self) -> str:
        """Realizuje screenshot i zwraca sciezke do pliku."""
        try:
            from PIL import ImageGrab
            path = "windows_screenshot.png"
            img = ImageGrab.grab()
            img.save(path)
            log.info(f"Screenshot zrobiony i zapisany w {path}")
            return path
        except Exception as e:
            log.error(f"WindowsAgent Screenshot błąd: {e}")
            return ""

    def execute(self, action: str, target: str):
        log.info(f"WindowsAgent Execute: {action} -> {target}")
        if action == "open":
            return self.launch_app(target)
        elif action == "close":
            return self.close_app(target)
        elif action == "screenshot":
            return self.take_screenshot()
        return False
