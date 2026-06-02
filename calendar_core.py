"""Kalendarz — przechowuje wydarzenia w SQLite.

Obsługuje:
  "dodaj do kalendarza spotkanie z dentystą 3 czerwca o 10:30"
  "dodaj wydarzenie wizyta jutro o 15:00"
  "co mam dzisiaj"
  "najbliższe wydarzenia"
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Optional, Tuple

from core.logging_setup import get_logger

log = get_logger(__name__)

# Importujemy mapper miesięcy z scheduler_core
from actions.scheduler_core import _MONTHS_PL, _WEEKDAYS_PL


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class CalendarEvent:
    id: int
    title: str
    start_dt: str    # ISO datetime
    end_dt: str      # ISO datetime (może być = start_dt)
    location: str
    notes: str
    active: int

    def format_start(self) -> str:
        try:
            dt = datetime.fromisoformat(self.start_dt)
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return self.start_dt

    def format_short(self) -> str:
        try:
            dt = datetime.fromisoformat(self.start_dt)
            return dt.strftime("%d.%m %H:%M")
        except Exception:
            return self.start_dt


# ---------------------------------------------------------------------------
# Parsowanie daty/czasu z polskiego tekstu
# ---------------------------------------------------------------------------

def parse_event_datetime(tekst: str) -> Tuple[Optional[datetime], str]:
    """Zwraca (start_dt, title_without_datetime).

    Próbuje wyłuskać datę i godzinę z naturalnego opisu.
    """
    now = datetime.now()
    t = tekst.strip()
    t = re.sub(r"^(dodaj\s+(do\s+)?kalendarza?\s*|dodaj\s+wydarzenie\s*|zaplanuj\s*)", "", t, flags=re.I)
    t = t.strip()

    when: Optional[datetime] = None
    cleaned = t

    # Słowa kluczowe dnia
    for kw, days in [("pojutrze", 2), ("jutro", 1), ("dzisiaj", 0), ("dziś", 0), ("dzis", 0)]:
        m = re.search(rf"\b{kw}\s+o\s+(\d{{1,2}})(?::(\d{{2}}))?", t, re.I)
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            base = now + timedelta(days=days)
            when = base.replace(hour=h, minute=mi, second=0, microsecond=0)
            cleaned = t[: m.start()] + t[m.end():]
            break

    # Dzień tygodnia
    if when is None:
        for day_pl, day_num in _WEEKDAYS_PL.items():
            m = re.search(
                rf"\b(?:w\s+)?{re.escape(day_pl)}\s+o\s+(\d{{1,2}})(?::(\d{{2}}))?",
                t, re.I,
            )
            if m:
                h, mi = int(m.group(1)), int(m.group(2) or 0)
                days_ahead = (day_num - now.weekday()) % 7 or 7
                base = now + timedelta(days=days_ahead)
                when = base.replace(hour=h, minute=mi, second=0, microsecond=0)
                cleaned = t[: m.start()] + t[m.end():]
                break

    # "N <miesiąc> o X:Y"
    if when is None:
        m = re.search(
            r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_PL.keys()) + r")\s+o\s+(\d{1,2})(?::(\d{2}))?",
            t, re.I,
        )
        if m:
            day_n = int(m.group(1))
            month_n = _MONTHS_PL[m.group(2).lower()]
            h, mi = int(m.group(3)), int(m.group(4) or 0)
            year = now.year
            try:
                candidate = datetime(year, month_n, day_n, h, mi)
                if candidate < now:
                    candidate = datetime(year + 1, month_n, day_n, h, mi)
                when = candidate
            except ValueError:
                pass
            cleaned = t[: m.start()] + t[m.end():]

    # "N <miesiąc>" bez godziny
    if when is None:
        m = re.search(
            r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_PL.keys()) + r")\b",
            t, re.I,
        )
        if m:
            day_n = int(m.group(1))
            month_n = _MONTHS_PL[m.group(2).lower()]
            year = now.year
            try:
                when = datetime(year, month_n, day_n, 12, 0)
                if when.date() < now.date():
                    when = datetime(year + 1, month_n, day_n, 12, 0)
            except ValueError:
                pass
            cleaned = t[: m.start()] + t[m.end():]

    # Sama godzina "o X:Y"
    if when is None:
        m = re.search(r"\bo\s+(\d{1,2})(?::(\d{2}))?\b", t, re.I)
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if candidate < now:
                candidate += timedelta(days=1)
            when = candidate
            cleaned = t[: m.start()] + t[m.end():]

    title = re.sub(r"\s+", " ", cleaned).strip(" ,.;:!?")
    return when, title


# ---------------------------------------------------------------------------
# Silnik kalendarza
# ---------------------------------------------------------------------------

class CalendarEngine:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        start_dt    TEXT NOT NULL,
        end_dt      TEXT NOT NULL,
        location    TEXT NOT NULL DEFAULT '',
        notes       TEXT NOT NULL DEFAULT '',
        active      INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_dt);
    CREATE INDEX IF NOT EXISTS idx_events_active ON events(active);
    """

    def __init__(self, db_path: Path):
        self._db = db_path
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._db)) as c:
            c.executescript(self.SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db)
        c.row_factory = sqlite3.Row
        return c

    def add(self, title: str, start_dt: datetime, end_dt: Optional[datetime] = None,
            location: str = "", notes: str = "") -> CalendarEvent:
        if end_dt is None:
            end_dt = start_dt
        s = start_dt.isoformat(timespec="minutes")
        e = end_dt.isoformat(timespec="minutes")
        with closing(self._conn()) as c:
            cur = c.execute(
                "INSERT INTO events(title, start_dt, end_dt, location, notes, active) "
                "VALUES(?,?,?,?,?,1)",
                (title, s, e, location, notes),
            )
            c.commit()
            eid = cur.lastrowid
        return self._get(eid)

    def remove(self, eid: int) -> bool:
        with closing(self._conn()) as c:
            cur = c.execute("UPDATE events SET active=0 WHERE id=? AND active=1", (eid,))
            c.commit()
        return cur.rowcount > 0

    def _get(self, eid: int) -> CalendarEvent:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
        return _row_to_event(row)

    def today(self) -> List[CalendarEvent]:
        today_str = date.today().isoformat()
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM events WHERE active=1 AND DATE(start_dt)=? ORDER BY start_dt",
                (today_str,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def upcoming(self, days: int = 7) -> List[CalendarEvent]:
        now_str = datetime.now().isoformat(timespec="minutes")
        until = (datetime.now() + timedelta(days=days)).isoformat(timespec="minutes")
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM events WHERE active=1 AND start_dt>=? AND start_dt<=? ORDER BY start_dt",
                (now_str, until),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def next(self) -> Optional[CalendarEvent]:
        now_str = datetime.now().isoformat(timespec="minutes")
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT * FROM events WHERE active=1 AND start_dt>? ORDER BY start_dt LIMIT 1",
                (now_str,),
            ).fetchone()
        return _row_to_event(row) if row else None

    def format_list(self, events: List[CalendarEvent], header: str = "Kalendarz") -> str:
        if not events:
            return f"{header}: brak wydarzeń."
        linie = [f"{header}:"]
        for ev in events:
            loc = f" @ {ev.location}" if ev.location else ""
            linie.append(f"  • {ev.format_start()} — {ev.title}{loc}")
        return "\n".join(linie)


def _row_to_event(row) -> CalendarEvent:
    return CalendarEvent(
        id=row["id"], title=row["title"],
        start_dt=row["start_dt"], end_dt=row["end_dt"],
        location=row["location"] or "", notes=row["notes"] or "",
        active=row["active"],
    )
