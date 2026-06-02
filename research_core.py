"""Codzienny research — śledź temat, codziennie o wybranej godzinie
Jarvis szuka nowych informacji i streszcza je przez Ollama.

Użycie:
  "śledź temat sztuczna inteligencja"
  "codzienny research: Python programowanie o 8:00"
  "moje tematy"
  "zrób research teraz"
  "usuń temat 1"
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from core.logging_setup import get_logger

log = get_logger(__name__)

try:
    from duckduckgo_search import DDGS
    _DDG_OK = True
except ImportError:
    _DDG_OK = False
    log.warning("duckduckgo-search niedostępny — pip install duckduckgo-search")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _APScheduler_OK = True
except ImportError:
    _APScheduler_OK = False


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class ResearchTopic:
    id: int
    topic: str
    hour: int
    minute: int
    last_run: str  # ISO
    active: int

    def format_schedule(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"


@dataclass
class ResearchResult:
    id: int
    topic_id: int
    run_dt: str
    summary: str


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ResearchEngine:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS research_topics (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        topic     TEXT NOT NULL UNIQUE,
        hour      INTEGER NOT NULL DEFAULT 8,
        minute    INTEGER NOT NULL DEFAULT 0,
        last_run  TEXT NOT NULL DEFAULT '',
        active    INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS research_results (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_id  INTEGER NOT NULL,
        run_dt    TEXT NOT NULL,
        summary   TEXT NOT NULL,
        FOREIGN KEY(topic_id) REFERENCES research_topics(id)
    );
    CREATE INDEX IF NOT EXISTS idx_res_topic ON research_results(topic_id, run_dt);
    """

    def __init__(self, db_path: Path, ollama=None,
                 notify_fn: Optional[Callable[[str, str], None]] = None):
        """
        :param ollama: OllamaClient — do streszczania wyników.
        :param notify_fn: fn(topic, summary) — wywoływana po gotowym researchu.
        """
        self._db = db_path
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self.ollama = ollama
        self.notify_fn = notify_fn
        self._scheduler = None

        with closing(sqlite3.connect(self._db)) as c:
            c.executescript(self.SCHEMA)
            c.commit()

        if _APScheduler_OK:
            self._scheduler = BackgroundScheduler(
                job_defaults={"misfire_grace_time": 7200},
                timezone="local",
            )
            self._scheduler.start()
            self._restore()

    # ------------------------------------------------------------------
    # Publiczne API
    # ------------------------------------------------------------------

    def add_topic(self, topic: str, hour: int = 8, minute: int = 0) -> ResearchTopic:
        """Dodaje temat. Jeśli istnieje — aktualizuje godzinę."""
        with closing(sqlite3.connect(self._db)) as c:
            existing = c.execute(
                "SELECT id FROM research_topics WHERE topic=? AND active=1", (topic,)
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE research_topics SET hour=?, minute=? WHERE id=?",
                    (hour, minute, existing[0]),
                )
                c.commit()
                eid = existing[0]
            else:
                cur = c.execute(
                    "INSERT INTO research_topics(topic, hour, minute, last_run, active) "
                    "VALUES(?,?,?,'',1)",
                    (topic, hour, minute),
                )
                c.commit()
                eid = cur.lastrowid

        t = self._get_topic(eid)
        self._schedule_topic(t)
        log.info("Dodano temat research: '%s' codziennie o %02d:%02d", topic, hour, minute)
        return t

    def remove_topic(self, tid_or_name) -> bool:
        with closing(sqlite3.connect(self._db)) as c:
            if isinstance(tid_or_name, int):
                cur = c.execute(
                    "UPDATE research_topics SET active=0 WHERE id=? AND active=1", (tid_or_name,)
                )
            else:
                cur = c.execute(
                    "UPDATE research_topics SET active=0 WHERE topic LIKE ? AND active=1",
                    (f"%{tid_or_name}%",),
                )
            c.commit()
        if cur.rowcount:
            if self._scheduler:
                try:
                    self._scheduler.remove_job(f"research_{tid_or_name}")
                except Exception:
                    pass
        return bool(cur.rowcount)

    def list_topics(self) -> List[ResearchTopic]:
        with closing(sqlite3.connect(self._db)) as c:
            rows = c.execute(
                "SELECT id, topic, hour, minute, last_run, active "
                "FROM research_topics WHERE active=1 ORDER BY id"
            ).fetchall()
        return [ResearchTopic(*r) for r in rows]

    def format_topics(self) -> str:
        topics = self.list_topics()
        if not topics:
            return "Brak śledzonych tematów."
        linie = ["Śledzone tematy:"]
        for t in topics:
            last = t.last_run[:10] if t.last_run else "nigdy"
            linie.append(f"  {t.id}. [{t.format_schedule()}] {t.topic} (ostatni: {last})")
        return "\n".join(linie)

    def run_now(self, topic: str) -> str:
        """Natychmiastowo robi research na podany temat. Zwraca streszczenie."""
        log.info("Research now: '%s'", topic)
        raw = self._fetch_web(topic)
        if not raw:
            return f"Nie znalazłem nic nowego o '{topic}'."
        summary = self._summarize(topic, raw)
        self._save_result(topic, summary)
        return summary

    def latest_result(self, topic: str) -> Optional[str]:
        with closing(sqlite3.connect(self._db)) as c:
            row = c.execute(
                "SELECT summary FROM research_results r "
                "JOIN research_topics t ON r.topic_id=t.id "
                "WHERE t.topic LIKE ? ORDER BY r.run_dt DESC LIMIT 1",
                (f"%{topic}%",),
            ).fetchone()
        return row[0] if row else None

    def shutdown(self):
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Wewnętrzne
    # ------------------------------------------------------------------

    def _restore(self):
        for t in self.list_topics():
            try:
                self._schedule_topic(t)
            except Exception as e:
                log.warning("Restore research %s: %s", t.topic, e)

    def _schedule_topic(self, t: ResearchTopic):
        if not self._scheduler:
            return
        job_id = f"research_{t.id}"
        topic_snap = t.topic
        topic_id = t.id

        def fire():
            try:
                raw = self._fetch_web(topic_snap)
                if raw:
                    summary = self._summarize(topic_snap, raw)
                    self._save_result_by_id(topic_id, summary)
                    self._update_last_run(topic_id)
                    if self.notify_fn:
                        self.notify_fn(topic_snap, summary)
            except Exception as exc:
                log.exception("Research '%s': %s", topic_snap, exc)

        trigger = CronTrigger(hour=t.hour, minute=t.minute, timezone="local")
        try:
            self._scheduler.add_job(fire, trigger, id=job_id, replace_existing=True)
        except Exception as e:
            log.warning("Schedule research %s: %s", t.topic, e)

    def _fetch_web(self, topic: str, max_results: int = 5) -> str:
        if not _DDG_OK:
            return ""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=max_results))
            if not results:
                return ""
            snippets = [f"• {r.get('title','')}: {r.get('body','')}" for r in results]
            return "\n".join(snippets[:5])
        except Exception as e:
            log.warning("DuckDuckGo search '%s': %s", topic, e)
            return ""

    def _summarize(self, topic: str, raw: str) -> str:
        if self.ollama is None or not self.ollama.is_running():
            # Fallback — zwróć surowe snippety skrócone
            lines = raw.split("\n")[:3]
            return f"[{topic}]\n" + "\n".join(lines)
        try:
            from ai.ollama_client import ChatMessage
            prompt = (
                f"Poniżej są wyniki wyszukiwania na temat: '{topic}'.\n"
                f"Napisz po polsku krótkie streszczenie (3-5 zdań) najważniejszych nowych informacji.\n"
                f"Tylko fakty, bez wstępów, bez 'oto streszczenie'.\n\n"
                f"{raw}"
            )
            msgs = [
                ChatMessage("system", "Jesteś pomocnym asystentem. Streszczasz po polsku."),
                ChatMessage("user", prompt),
            ]
            return self.ollama.chat(msgs)
        except Exception as e:
            log.warning("Summarize '%s': %s", topic, e)
            return raw[:500]

    def _save_result(self, topic: str, summary: str):
        with closing(sqlite3.connect(self._db)) as c:
            row = c.execute(
                "SELECT id FROM research_topics WHERE topic=? AND active=1", (topic,)
            ).fetchone()
            if row:
                self._save_result_by_id(row[0], summary)
                self._update_last_run(row[0])

    def _save_result_by_id(self, topic_id: int, summary: str):
        now = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(self._db)) as c:
            c.execute(
                "INSERT INTO research_results(topic_id, run_dt, summary) VALUES(?,?,?)",
                (topic_id, now, summary),
            )
            c.commit()

    def _update_last_run(self, topic_id: int):
        now = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(self._db)) as c:
            c.execute("UPDATE research_topics SET last_run=? WHERE id=?", (now, topic_id))
            c.commit()

    def _get_topic(self, eid: int) -> ResearchTopic:
        with closing(sqlite3.connect(self._db)) as c:
            row = c.execute(
                "SELECT id, topic, hour, minute, last_run, active FROM research_topics WHERE id=?",
                (eid,),
            ).fetchone()
        return ResearchTopic(*row)
