"""Lista zadań (TODO) dla Jarvisa v3.

SQLite backend, zero deps. Głosowe zarządzanie.

Komendy:
  "Dodaj do listy: zamówić filtry Mann"
  "Dodaj ważne: zadzwonić do klienta Kowalski"
  "Co mam do zrobienia?"
  "Pokaż listę zadań"
  "Odznacz numer 3"
  "Usuń zadanie 2"
  "Wyczyść ukończone"
"""
from __future__ import annotations

import datetime
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from core.logging_setup import get_logger

log = get_logger(__name__)

PRIORITIES = {"ważne": 3, "wysokie": 3, "pilne": 3,
              "normalne": 2, "zwykłe": 2,
              "niskie": 1, "kiedyś": 1}


@dataclass
class TodoItem:
    id: int
    text: str
    priority: int          # 1=niski, 2=normalny, 3=wysoki
    done: bool
    created_at: str
    done_at: Optional[str]
    due_date: Optional[str]

    def format(self, show_id: bool = True) -> str:
        status = "✅" if self.done else {3: "🔴", 2: "🟡", 1: "⚪"}.get(self.priority, "⚪")
        num = f"[{self.id}] " if show_id else ""
        due = f"  📅 {self.due_date}" if self.due_date and not self.done else ""
        return f"{num}{status} {self.text}{due}"


@dataclass
class TodoConfig:
    db_path: str = "~/.jarvis/learning.db"


class TodoTool:
    def __init__(self, cfg: TodoConfig):
        db_path = Path(os.path.expanduser(cfg.db_path))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    text       TEXT    NOT NULL,
                    priority   INTEGER NOT NULL DEFAULT 2,
                    done       INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT    NOT NULL,
                    done_at    TEXT,
                    due_date   TEXT
                )""")
            c.commit()

    def add(self, text: str, priority: int = 2, due_date: Optional[str] = None) -> TodoItem:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self._db) as c:
            cur = c.execute(
                "INSERT INTO todos(text,priority,done,created_at,due_date) VALUES(?,?,0,?,?)",
                (text.strip(), priority, now, due_date),
            )
            row_id = cur.lastrowid
            c.commit()
        log.info("Dodano zadanie #%d: %s", row_id, text)
        return TodoItem(id=row_id, text=text, priority=priority,
                        done=False, created_at=now, done_at=None, due_date=due_date)

    def done(self, item_id: int) -> bool:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self._db) as c:
            n = c.execute("UPDATE todos SET done=1, done_at=? WHERE id=? AND done=0",
                          (now, item_id)).rowcount
            c.commit()
        return n > 0

    def delete(self, item_id: int) -> bool:
        with sqlite3.connect(self._db) as c:
            n = c.execute("DELETE FROM todos WHERE id=?", (item_id,)).rowcount
            c.commit()
        return n > 0

    def clear_done(self) -> int:
        with sqlite3.connect(self._db) as c:
            n = c.execute("DELETE FROM todos WHERE done=1").rowcount
            c.commit()
        return n

    def list_active(self) -> List[TodoItem]:
        return self._query("SELECT * FROM todos WHERE done=0 ORDER BY priority DESC, id ASC")

    def list_all(self) -> List[TodoItem]:
        return self._query("SELECT * FROM todos ORDER BY done ASC, priority DESC, id ASC")

    def _query(self, sql: str) -> List[TodoItem]:
        with sqlite3.connect(self._db) as c:
            rows = c.execute(sql).fetchall()
        return [TodoItem(id=r[0], text=r[1], priority=r[2], done=bool(r[3]),
                         created_at=r[4], done_at=r[5], due_date=r[6]) for r in rows]

    def format_list(self, show_done: bool = False) -> str:
        items = self.list_all() if show_done else self.list_active()
        if not items:
            return "Lista zadań jest pusta. 🎉"
        high   = [i for i in items if i.priority == 3 and not i.done]
        normal = [i for i in items if i.priority == 2 and not i.done]
        low    = [i for i in items if i.priority == 1 and not i.done]
        done   = [i for i in items if i.done]

        lines = [f"Lista zadań ({len(items)} aktywnych):"]
        if high:
            lines.append("🔴 Ważne:")
            lines.extend(f"  {i.format()}" for i in high)
        if normal:
            lines.append("🟡 Normalne:")
            lines.extend(f"  {i.format()}" for i in normal)
        if low:
            lines.append("⚪ Niskie:")
            lines.extend(f"  {i.format()}" for i in low)
        if show_done and done:
            lines.append(f"✅ Ukończone ({len(done)}):")
            lines.extend(f"  {i.format()}" for i in done[:5])
        return "\n".join(lines)

    def stats(self) -> str:
        all_items = self.list_all()
        total = len(all_items)
        done  = sum(1 for i in all_items if i.done)
        high  = sum(1 for i in all_items if i.priority == 3 and not i.done)
        return (f"📋 Zadania: {total - done} aktywnych / {done} ukończonych"
                + (f" | 🔴 {high} pilnych" if high else ""))
