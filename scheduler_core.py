"""Scheduler — przypomnienia o konkretnej godzinie / dacie.

Używa APScheduler (BackgroundScheduler) — działa w tle w osobnym wątku.
Wszystko persystowane w SQLite, automatycznie przywracane po restarcie.

Parsuje naturalne polskie opisy czasu:
  "przypomnij jutro o 15:30 zabrać lek"
  "przypomnij za 2 godziny sprawdzić piekarnik"
  "codziennie o 8:00 poranny brief"
  "przypomnij w piątek o 10 spotkanie"
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from core.logging_setup import get_logger

log = get_logger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    _APSCHEDULER_OK = True
except ImportError:
    _APSCHEDULER_OK = False
    log.warning("APScheduler niedostępny — pip install apscheduler")


# ---------------------------------------------------------------------------
# Model danych
# ---------------------------------------------------------------------------

@dataclass
class Reminder:
    id: str
    label: str
    when: str        # ISO 8601 datetime
    recurrence: str  # "" | "daily" | "weekly"
    active: int

    def format_when(self) -> str:
        try:
            dt = datetime.fromisoformat(self.when)
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return self.when

    def format_recurrence(self) -> str:
        return {"daily": " [codziennie]", "weekly": " [co tydzień]"}.get(self.recurrence, "")


# ---------------------------------------------------------------------------
# Parsowanie czasu z języka polskiego
# ---------------------------------------------------------------------------

_WEEKDAYS_PL = {
    "poniedziałek": 0, "poniedziałku": 0,
    "wtorek": 1, "wtorku": 1,
    "środę": 2, "środy": 2, "środa": 2,
    "czwartek": 3, "czwartku": 3,
    "piątek": 4, "piątku": 4,
    "sobota": 5, "soboty": 5, "sobotę": 5,
    "niedziela": 6, "niedzieli": 6, "niedzielę": 6,
}

_MONTHS_PL = {
    "stycznia": 1, "styczeń": 1, "styczen": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "kwiecien": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpień": 8, "sierpien": 8,
    "września": 9, "wrzesień": 9, "wrzesien": 9,
    "października": 10, "październik": 10, "pazdziernika": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12, "grudzien": 12,
}


def parse_reminder(tekst: str) -> Tuple[datetime, str, str]:
    """Parsuje tekst w języku polskim i zwraca (when_dt, label, recurrence).

    Obsługuje:
    - "za N minut/godzin"
    - "jutro/pojutrze o X:Y"
    - "w <dzień tygodnia> o X:Y"
    - "N <miesiąc> o X:Y"
    - "o X:Y" (dzisiaj lub jutro jeśli w przeszłości)
    - Cykliczność: "codziennie", "co dzień", "co tydzień"
    """
    now = datetime.now()
    recurrence = ""

    # Wykryj cykliczność
    t = tekst.strip()
    if re.search(r"\bcodzienn\w*\b|\bco\s+dzie[nń]\b", t, re.I):
        recurrence = "daily"
    elif re.search(r"\bco\s+tydzie[nń]\b|\bco\s+tydzień\b", t, re.I):
        recurrence = "weekly"

    # Usuń prefiks "przypomnij (mi)" / "ustaw przypomnienie"
    t = re.sub(
        r"^(przypomnij\s+(mi\s+)?|ustaw\s+przypomnienie\s*|dodaj\s+przypomnienie\s*)",
        "", t, flags=re.I
    ).strip()

    when: Optional[datetime] = None
    cleaned = t

    # 1. "za N minut/godzin/sekund"
    m = re.search(
        r"\bza\s+(\d+)\s+(minut[eę]?|min\.?|godzin[yę]?|godz\.?|h|sekund[yę]?|sek\.?|s)\b",
        t, re.I
    )
    if m:
        n = int(m.group(1))
        u = m.group(2).lower()
        if "godz" in u or u == "h":
            when = now + timedelta(hours=n)
        elif "min" in u:
            when = now + timedelta(minutes=n)
        else:
            when = now + timedelta(seconds=n)
        cleaned = t[: m.start()] + t[m.end():]

    # 2. "jutro o X:Y" lub "pojutrze o X:Y"
    if when is None:
        for kw, days in [("pojutrze", 2), ("jutro", 1), ("dziś", 0), ("dzisiaj", 0), ("dzis", 0)]:
            m = re.search(rf"\b{kw}\s+o\s+(\d{{1,2}})(?::(\d{{2}}))?", t, re.I)
            if m:
                h, mi = int(m.group(1)), int(m.group(2) or 0)
                base = now + timedelta(days=days)
                when = base.replace(hour=h, minute=mi, second=0, microsecond=0)
                cleaned = t[: m.start()] + t[m.end():]
                break

    # 3. "w <dzień tygodnia> o X:Y"
    if when is None:
        for day_pl, day_num in _WEEKDAYS_PL.items():
            m = re.search(
                rf"\b(?:w\s+)?{re.escape(day_pl)}\s+o\s+(\d{{1,2}})(?::(\d{{2}}))?",
                t, re.I
            )
            if m:
                h, mi = int(m.group(1)), int(m.group(2) or 0)
                days_ahead = (day_num - now.weekday()) % 7 or 7
                base = now + timedelta(days=days_ahead)
                when = base.replace(hour=h, minute=mi, second=0, microsecond=0)
                cleaned = t[: m.start()] + t[m.end():]
                break

    # 4. "N <miesiąc> o X:Y"
    if when is None:
        m = re.search(
            r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_PL.keys()) + r")\s+o\s+(\d{1,2})(?::(\d{2}))?",
            t, re.I
        )
        if m:
            day_n = int(m.group(1))
            month_n = _MONTHS_PL[m.group(2).lower()]
            h, mi = int(m.group(3)), int(m.group(4) or 0)
            year = now.year
            candidate = datetime(year, month_n, day_n, h, mi, 0)
            if candidate < now:
                candidate = datetime(year + 1, month_n, day_n, h, mi, 0)
            when = candidate
            cleaned = t[: m.start()] + t[m.end():]

    # 5. "o X:Y" (samo)
    if when is None:
        m = re.search(r"\bo\s+(\d{1,2})(?::(\d{2}))?\b", t, re.I)
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            when = candidate
            cleaned = t[: m.start()] + t[m.end():]

    # Fallback: za godzinę
    if when is None:
        when = now + timedelta(hours=1)

    # Wyczyść label
    label = re.sub(r"\s+", " ", cleaned).strip(" ,.;:!?")
    # Usuń słowa cykliczności z labela
    label = re.sub(
        r"\bcodzienn(?:ie|y|i)?\b|\bco\s+dzie[nń]\b|\bco\s+tydzień\b|\bco\s+tydzie[nń]\b",
        "", label, flags=re.I
    ).strip()
    label = re.sub(r"\s+", " ", label).strip(" ,.;:!?")
    if not label:
        label = "Przypomnienie"

    return when, label, recurrence


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ReminderScheduler:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS reminders (
        id          TEXT PRIMARY KEY,
        label       TEXT NOT NULL,
        when_dt     TEXT NOT NULL,
        recurrence  TEXT NOT NULL DEFAULT '',
        active      INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_rem_active ON reminders(active);
    """

    def __init__(self, db_path: Path, notify_fn: Optional[Callable[[str], None]] = None):
        self._db = db_path
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self.notify_fn = notify_fn
        self._scheduler = None

        with closing(sqlite3.connect(self._db)) as c:
            c.executescript(self.SCHEMA)
            c.commit()

        if _APSCHEDULER_OK:
            self._scheduler = BackgroundScheduler(
                job_defaults={"misfire_grace_time": 3600},
                timezone="local",
            )
            self._scheduler.start()
            self._restore()
            log.info("ReminderScheduler uruchomiony")
        else:
            log.warning("APScheduler niedostępny — przypomnienia nie będą działać.")

    # ------------------------------------------------------------------
    # Publiczne API
    # ------------------------------------------------------------------

    def add(self, label: str, when_dt: datetime, recurrence: str = "") -> Reminder:
        rid = uuid.uuid4().hex[:10]
        when_str = when_dt.isoformat(timespec="seconds")

        with closing(sqlite3.connect(self._db)) as c:
            c.execute(
                "INSERT INTO reminders(id, label, when_dt, recurrence, active) VALUES(?,?,?,?,1)",
                (rid, label, when_str, recurrence),
            )
            c.commit()

        r = Reminder(id=rid, label=label, when=when_str, recurrence=recurrence, active=1)
        self._schedule_job(r)
        log.info("Dodano przypomnienie '%s' na %s (recurrence=%r)", label, when_str, recurrence)
        return r

    def cancel(self, rid_or_label: str) -> bool:
        with closing(sqlite3.connect(self._db)) as c:
            row = c.execute(
                "SELECT id FROM reminders WHERE (id=? OR label LIKE ?) AND active=1 LIMIT 1",
                (rid_or_label, f"%{rid_or_label}%"),
            ).fetchone()
            if not row:
                return False
            rid = row[0]
            c.execute("UPDATE reminders SET active=0 WHERE id=?", (rid,))
            c.commit()

        if self._scheduler:
            try:
                self._scheduler.remove_job(rid)
            except Exception:
                pass
        return True

    def list_active(self) -> List[Reminder]:
        with closing(sqlite3.connect(self._db)) as c:
            rows = c.execute(
                "SELECT id, label, when_dt, recurrence, active "
                "FROM reminders WHERE active=1 ORDER BY when_dt ASC"
            ).fetchall()
        return [Reminder(id=r[0], label=r[1], when=r[2], recurrence=r[3], active=r[4])
                for r in rows]

    def format_list(self) -> str:
        active = self.list_active()
        if not active:
            return "Brak aktywnych przypomnień."
        linie = ["Aktywne przypomnienia:"]
        for i, r in enumerate(active, 1):
            linie.append(f"  {i}. {r.label} — {r.format_when()}{r.format_recurrence()} (ID: {r.id})")
        return "\n".join(linie)

    def shutdown(self):
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Wewnętrzne
    # ------------------------------------------------------------------

    def _restore(self):
        for r in self.list_active():
            try:
                self._schedule_job(r)
            except Exception as e:
                log.warning("Restore przypomnienia %s: %s", r.id, e)

    def _schedule_job(self, r: Reminder):
        if not self._scheduler:
            return
        when_dt = datetime.fromisoformat(r.when)

        if r.recurrence == "daily":
            trigger = CronTrigger(hour=when_dt.hour, minute=when_dt.minute, second=0,
                                  timezone="local")
        elif r.recurrence == "weekly":
            trigger = CronTrigger(
                day_of_week=when_dt.weekday(),
                hour=when_dt.hour, minute=when_dt.minute, second=0,
                timezone="local",
            )
        else:
            # Jednorazowe — pomiń jeśli w przeszłości (np. po restarcie)
            if when_dt <= datetime.now():
                self._deactivate(r.id)
                return
            trigger = DateTrigger(run_date=when_dt, timezone="local")

        rid = r.id
        label = r.label
        one_shot = not r.recurrence

        def fire():
            log.info("🔔 Przypomnienie: %s", label)
            if self.notify_fn:
                try:
                    self.notify_fn(label)
                except Exception as exc:
                    log.exception("notify_fn: %s", exc)
            if one_shot:
                self._deactivate(rid)

        try:
            self._scheduler.add_job(fire, trigger, id=rid, replace_existing=True)
        except Exception as e:
            log.warning("Nie udało się zaplanować %s: %s", rid, e)

    def _deactivate(self, rid: str):
        with closing(sqlite3.connect(self._db)) as c:
            c.execute("UPDATE reminders SET active=0 WHERE id=?", (rid,))
            c.commit()
