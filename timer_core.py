"""Timer i stoper głosowy dla Jarvisa v3.

Obsługuje wiele timerów jednocześnie, każdy z nazwą.
Zero zależności zewnętrznych.

Komendy:
  "Ustaw timer na 30 minut na klej"
  "Timer 15 minut — lakier"
  "Pokaż timery"
  "Anuluj timer klej"
  "Stoper start" / "Stoper stop" / "Stoper reset" / "Ile minął stoper?"
"""
from __future__ import annotations

import threading
import time
import datetime
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class TimerEntry:
    id: str
    label: str
    duration_s: float
    started_at: float           # time.monotonic()
    deadline: float             # started_at + duration_s
    thread: Optional[threading.Thread] = field(default=None, repr=False)
    cancelled: bool = False
    fired: bool = False

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    @property
    def elapsed_s(self) -> float:
        return min(self.duration_s, time.monotonic() - self.started_at)

    def format_remaining(self) -> str:
        return _fmt_seconds(self.remaining_s)

    def format_elapsed(self) -> str:
        return _fmt_seconds(self.elapsed_s)


def _fmt_seconds(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


class TimerManager:
    """Zarządza wieloma timerami + stoper."""

    def __init__(self, notify_fn: Optional[Callable] = None):
        self.notify_fn = notify_fn      # callable(title, body, source)
        self._timers: Dict[str, TimerEntry] = {}
        self._lock = threading.Lock()
        self._counter = 0

        # Stoper
        self._stopwatch_start: Optional[float] = None
        self._stopwatch_paused_at: Optional[float] = None
        self._stopwatch_elapsed: float = 0.0

    # ================================================================ TIMERY

    def add(self, label: str, duration_s: float) -> TimerEntry:
        """Dodaje nowy timer i uruchamia go w tle."""
        with self._lock:
            self._counter += 1
            tid = f"t{self._counter}"

        now = time.monotonic()
        entry = TimerEntry(
            id=tid,
            label=label,
            duration_s=duration_s,
            started_at=now,
            deadline=now + duration_s,
        )

        t = threading.Thread(
            target=self._run,
            args=(entry,),
            daemon=True,
            name=f"timer-{tid}",
        )
        entry.thread = t

        with self._lock:
            self._timers[tid] = entry
        t.start()
        log.info("Timer %s: '%s' na %s", tid, label, _fmt_seconds(duration_s))
        return entry

    def _run(self, entry: TimerEntry) -> None:
        while True:
            remaining = entry.deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.5, remaining))
            if entry.cancelled:
                return

        if entry.cancelled:
            return

        entry.fired = True
        log.info("⏱ Timer wyzwolony: '%s'", entry.label)
        if self.notify_fn:
            try:
                self.notify_fn(
                    title=f"⏱ Timer: {entry.label}",
                    body=f"Minęło {_fmt_seconds(entry.duration_s)}",
                    source="timer",
                )
            except Exception as e:
                log.error("Timer notify błąd: %s", e)

        # Auto-usuń po 60s
        threading.Timer(60.0, self._remove, args=(entry.id,)).start()

    def _remove(self, tid: str) -> None:
        with self._lock:
            self._timers.pop(tid, None)

    def cancel(self, label_or_id: str) -> bool:
        """Anuluje timer po nazwie lub ID."""
        with self._lock:
            # Szukaj po ID
            if label_or_id in self._timers:
                self._timers[label_or_id].cancelled = True
                del self._timers[label_or_id]
                return True
            # Szukaj po etykiecie (case-insensitive)
            lo = label_or_id.lower()
            for tid, entry in list(self._timers.items()):
                if lo in entry.label.lower():
                    entry.cancelled = True
                    del self._timers[tid]
                    return True
        return False

    def list_active(self) -> List[TimerEntry]:
        with self._lock:
            return [e for e in self._timers.values() if not e.fired]

    def format_list(self) -> str:
        active = self.list_active()
        if not active:
            return "Brak aktywnych timerów."
        lines = [f"Aktywne timery ({len(active)}):"]
        for e in active:
            lines.append(f"  ⏱ [{e.id}] \"{e.label}\" — zostało {e.format_remaining()}")
        return "\n".join(lines)

    # ============================================================== STOPER

    def stopwatch_start(self) -> str:
        if self._stopwatch_start is not None and self._stopwatch_paused_at is None:
            return "Stoper już działa."
        if self._stopwatch_paused_at is not None:
            # Wznów
            paused_duration = time.monotonic() - self._stopwatch_paused_at
            self._stopwatch_start += paused_duration  # type: ignore[operator]
            self._stopwatch_paused_at = None
            return "▶ Stoper wznowiony."
        self._stopwatch_start = time.monotonic()
        self._stopwatch_elapsed = 0.0
        self._stopwatch_paused_at = None
        return "▶ Stoper uruchomiony."

    def stopwatch_stop(self) -> str:
        if self._stopwatch_start is None:
            return "Stoper nie jest uruchomiony."
        if self._stopwatch_paused_at is not None:
            return f"⏸ Stoper już wstrzymany: {_fmt_seconds(self._stopwatch_elapsed)}"
        self._stopwatch_paused_at = time.monotonic()
        elapsed = self._stopwatch_paused_at - self._stopwatch_start  # type: ignore[operator]
        self._stopwatch_elapsed = elapsed
        return f"⏸ Stoper wstrzymany: {_fmt_seconds(elapsed)}"

    def stopwatch_reset(self) -> str:
        self._stopwatch_start = None
        self._stopwatch_paused_at = None
        self._stopwatch_elapsed = 0.0
        return "↺ Stoper zresetowany."

    def stopwatch_read(self) -> str:
        if self._stopwatch_start is None:
            return "Stoper nie jest uruchomiony. Powiedz 'Stoper start'."
        if self._stopwatch_paused_at is not None:
            return f"⏸ Stoper (wstrzymany): {_fmt_seconds(self._stopwatch_elapsed)}"
        elapsed = time.monotonic() - self._stopwatch_start  # type: ignore[operator]
        return f"▶ Stoper: {_fmt_seconds(elapsed)}"


# ================================================================ PARSER

import re

_CZAS_PATTERNS = [
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*godzin[yęa]?", re.I), 3600),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:minut[ay]?|min\b)", re.I), 60),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:sekund[ay]?|sek\b|s\b)", re.I), 1),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*h\b", re.I), 3600),
]


def parse_duration_seconds(text: str) -> Optional[float]:
    """Wyciąga czas w sekundach z polskiego tekstu."""
    total = 0.0
    found = False
    for pattern, mult in _CZAS_PATTERNS:
        for m in pattern.finditer(text):
            val = float(m.group(1).replace(",", "."))
            total += val * mult
            found = True
    return total if found else None


def parse_timer_label(text: str) -> str:
    """Wyciąga etykietę timera (część po czasie)."""
    # Usuń komendy i czas
    cleaned = re.sub(
        r"\b(ustaw|timer|alarm|na|przez|za|minuty?|minut[aya]?|godzin[yęa]?|sekund[ay]?|min|sek|[hms])\b",
        " ", text, flags=re.I,
    )
    cleaned = re.sub(r"\d+(?:[.,]\d+)?", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" —:-")
    return cleaned if len(cleaned) > 2 else "timer"
