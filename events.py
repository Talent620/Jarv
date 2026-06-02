"""EventBus — pub/sub wewnętrzny, thread-safe."""
from __future__ import annotations
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, handler: Callable) -> None:
        with self._lock:
            self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        with self._lock:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    def emit(self, event: str, **kwargs: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event, []))
        for h in handlers:
            try:
                h(**kwargs)
            except Exception as e:
                import logging
                logging.getLogger("jarvis.events").exception("Handler %s for '%s': %s", h, event, e)

    def emit_async(self, event: str, **kwargs: Any) -> None:
        t = threading.Thread(target=self.emit, args=(event,), kwargs=kwargs, daemon=True)
        t.start()


bus = EventBus()


class E:
    WAKE_DETECTED   = "voice.wake_detected"
    SPEECH_START    = "voice.speech_start"
    TEXT_INPUT      = "core.text_input"
    INTENT_DETECTED = "intent.detected"
    ACTION_START    = "action.start"
    ACTION_DONE     = "action.done"
    ACTION_ERROR    = "action.error"
    SPEAK           = "output.speak"
    DISPLAY         = "output.display"
    SYSTEM_ALERT    = "system.alert"
    HEALTH_SNAPSHOT = "system.health"
    ESP32_CMD       = "esp32.command"
    ESP32_ACK       = "esp32.ack"
    WEB_PUSH        = "web.push"
