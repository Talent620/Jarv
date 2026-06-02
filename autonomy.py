"""Autonomy Engine - zadania w tle i obserwacja (Premium)"""
import threading
import time
from typing import Optional
from core.logging_setup import get_logger

log = get_logger(__name__)

class AutonomyEngine:
    def __init__(self, config=None, ctx=None):
        self.config = config or {}
        self.ctx = ctx
        self.enabled = self.config.get("enabled", True)
        self.interval_mins = self.config.get("interval_mins", 15)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not self.enabled:
            return
        log.info("Uruchamianie silnika Autonomii w tle...")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        log.info("Zatrzymywanie silnika Autonomii...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        log.info(f"Autonomy Loop start, inteval {self.interval_mins} minut.")
        while not self._stop_event.is_set():
            # Czekamy odpowiednią ilość czasu (lub na zamknięcie)
            wait_seconds = self.interval_mins * 60
            if self._stop_event.wait(wait_seconds):
                break
                
            self._perform_autonomous_tasks()

    def _perform_autonomous_tasks(self):
        log.info(">>> Wykonywanie zadań autonomicznych...")
        # Mozna pobrac powiadomienia, sprawdzic nowosci itd.
        if self.ctx and self.ctx.has("health_monitor"):
             log.info("Autonomia: sprawdzanie logów lub stanu cpu...")
             
        if self.ctx and self.ctx.has("orchestrator"):
             # Przykładowe proaktywne pobieranie przypomnien
             log.info("Autonomia: delegowanie zadań proaktywnych do Orchestratora")
