"""AppContext — wszystkie zależności w jednym miejscu."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class AppContext:
    config: Any
    bus: Any
    memory: Any
    learning: Any
    ollama: Any
    stt: Optional[Any] = None
    tts: Optional[Any] = None
    wake_word: Optional[Any] = None
    timer_manager: Optional[Any] = None
    todo_tool: Optional[Any] = None
    inventory_tool: Optional[Any] = None
    weather_tool: Optional[Any] = None
    health_monitor: Optional[Any] = None
    esp32: Optional[Any] = None
    telegram: Optional[Any] = None

    # ── Nowe moduły V3 i Jarvis Master Edition ───────
    adaptation: Optional[Any] = None       # AdaptationEngine (aliasy + instrukcje)
    scheduler: Optional[Any] = None        # ReminderScheduler (APScheduler)
    calendar: Optional[Any] = None         # CalendarEngine
    research: Optional[Any] = None         # ResearchEngine (codzienny research)
    history_store: Optional[Any] = None    # HistoryStore (historia rozmów)
    user_profile: Optional[Any] = None     # UserProfile (Master Edition: profil usera)
    project_memory: Optional[Any] = None   # ProjectMemory (Master Edition: projekty)

    # ── Master Edition Agenci ───────
    piper: Optional[Any] = None
    ocr: Optional[Any] = None
    windows: Optional[Any] = None
    vision: Optional[Any] = None
    ha: Optional[Any] = None
    web: Optional[Any] = None
    orchestrator: Optional[Any] = None

    # ── Premium Modules ───────
    semantic_memory: Optional[Any] = None
    stt_whisper: Optional[Any] = None
    ocr_premium: Optional[Any] = None
    windows_agent: Optional[Any] = None
    ha_core: Optional[Any] = None
    deep_research: Optional[Any] = None
    model_router: Optional[Any] = None
    autonomy_engine: Optional[Any] = None

    def has(self, attr: str) -> bool:
        return getattr(self, attr, None) is not None
