"""Historia rozmów — zapis i odczyt z SQLite.

Każda para (pytanie → odpowiedź) jest zapisywana automatycznie.
Komendy:
  "historia" / "historia rozmów" — ostatnie 10 wymian
  "historia 20"                  — ostatnie N wymian
  "wyczyść historię"             — kasuje wszystko
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from actions.base import ActionResult, BaseAction
from core.logging_setup import get_logger
from core.registry import registry

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Silnik historii
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    id: int
    dt: str
    user_msg: str
    assistant_msg: str


class HistoryStore:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS history (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        dt             TEXT NOT NULL,
        user_msg       TEXT NOT NULL,
        assistant_msg  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_hist_dt ON history(dt);
    """

    def __init__(self, db_path: Path, max_entries: int = 1000):
        self._db = db_path
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._max = max_entries
        with closing(sqlite3.connect(self._db)) as c:
            c.executescript(self.SCHEMA)
            c.commit()

    def save(self, user_msg: str, assistant_msg: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(self._db)) as c:
            c.execute(
                "INSERT INTO history(dt, user_msg, assistant_msg) VALUES(?,?,?)",
                (now, user_msg[:2000], assistant_msg[:4000]),
            )
            # Przytnij do max_entries
            c.execute(
                "DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                (self._max,),
            )
            c.commit()

    def last(self, n: int = 10) -> List[HistoryEntry]:
        with closing(sqlite3.connect(self._db)) as c:
            rows = c.execute(
                "SELECT id, dt, user_msg, assistant_msg FROM history "
                "ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [HistoryEntry(id=r[0], dt=r[1], user_msg=r[2], assistant_msg=r[3])
                for r in reversed(rows)]

    def clear(self) -> int:
        with closing(sqlite3.connect(self._db)) as c:
            cur = c.execute("DELETE FROM history")
            c.commit()
        return cur.rowcount

    def format(self, entries: List[HistoryEntry]) -> str:
        if not entries:
            return "Historia rozmów jest pusta."
        linie = [f"Historia rozmów ({len(entries)} wpisów):"]
        for e in entries:
            ts = e.dt[:16].replace("T", " ")
            u = e.user_msg[:80] + ("…" if len(e.user_msg) > 80 else "")
            a = e.assistant_msg[:120] + ("…" if len(e.assistant_msg) > 120 else "")
            linie.append(f"\n  [{ts}]")
            linie.append(f"  Ty:     {u}")
            linie.append(f"  Jarvis: {a}")
        return "\n".join(linie)


# ---------------------------------------------------------------------------
# Akcje
# ---------------------------------------------------------------------------

@registry.register("history_show")
class HistoryShowAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("history_store"):
            return ActionResult("Historia niedostępna.", success=False)

        import re
        m = re.search(r"\b(\d+)\b", intent.surowy_tekst)
        n = int(m.group(1)) if m else 10
        n = min(max(n, 1), 50)

        entries = ctx.history_store.last(n)
        return ActionResult(ctx.history_store.format(entries), speak=False)


@registry.register("history_clear")
class HistoryClearAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("history_store"):
            return ActionResult("Historia niedostępna.", success=False)
        n = ctx.history_store.clear()
        return ActionResult(f"Historia wyczyszczona ({n} wpisów).")
