"""Project Memory — zarządzanie projektami i kontekstem w aplikacji."""

from __future__ import annotations
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Dict, List, Optional
import json

from core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class ProjectConfig:
    db_path: str = "~/.jarvis/projects.db"


@dataclass
class ProjectEntry:
    id: int
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str

@dataclass
class ProjectTask:
    id: int
    project_id: int
    content: str
    status: str
    created_at: str

@dataclass
class ProjectNote:
    id: int
    project_id: int
    content: str
    created_at: str


class ProjectMemory:
    """Zarządza projektami w izolowanych kontekstach (pod RAG i Memory)."""

    def __init__(self, config: ProjectConfig):
        import os
        self.db_path = os.path.expanduser(config.db_path)
        self.active_project_id: Optional[int] = None
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with closing(self._conn()) as c:
            c.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS project_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS project_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS project_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            ''')
            c.commit()

    def _teraz_iso(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

    def create_project(self, name: str, description: str) -> Optional[int]:
        try:
            with closing(self._conn()) as c:
                c.execute(
                    "INSERT INTO projects(name, description, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
                    (name, description, self._teraz_iso(), self._teraz_iso())
                )
                c.commit()
                log.info(f"Utworzono projekt: {name}")
                return c.lastrowid
        except sqlite3.IntegrityError:
            log.warning(f"Projekt o nazwie '{name}' już istnieje.")
            return None

    def get_project_by_name(self, name: str) -> Optional[ProjectEntry]:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
            if row:
                return ProjectEntry(**dict(row))
            return None
            
    def get_project_by_id(self, p_id: int) -> Optional[ProjectEntry]:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM projects WHERE id = ?", (p_id,)).fetchone()
            if row:
                return ProjectEntry(**dict(row))
            return None

    def list_projects(self) -> List[ProjectEntry]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            return [ProjectEntry(**dict(r)) for r in rows]

    def set_active_project(self, name: str) -> bool:
        project = self.get_project_by_name(name)
        if project:
            self.active_project_id = project.id
            log.info(f"Aktywny projekt ustawiony na: {name}")
            return True
        return False

    def get_active_project(self) -> Optional[ProjectEntry]:
        if not self.active_project_id:
            return None
        return self.get_project_by_id(self.active_project_id)
        
    def get_active_context(self) -> str:
        active = self.get_active_project()
        if not active:
            return ""
        
        lines = [f"AKTYWNY PROJEKT: {active.name}"]
        lines.append(f"Opis: {active.description}")
        
        # Pokaż notatki
        notes = self.get_notes(active.id)
        if notes:
            lines.append("Notatki z projektu:")
            for n in notes[-5:]: # Ostatnie 5 notatek
                lines.append(f" - {n.content}")
                
        # Pokaż taski
        tasks = self.get_tasks(active.id)
        if tasks:
            lines.append("Zadania w projekcie:")
            for t in tasks[-5:]:
                lines.append(f" - [{t.status}] {t.content}")
                
        return "\n".join(lines)

    def add_note(self, content: str, project_id: Optional[int] = None) -> Optional[int]:
        p_id = project_id or self.active_project_id
        if not p_id:
            return None
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO project_notes(project_id, content, created_at) VALUES (?, ?, ?)",
                (p_id, content, self._teraz_iso())
            )
            c.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (self._teraz_iso(), p_id))
            c.commit()
            return c.lastrowid
            
    def get_notes(self, project_id: int) -> List[ProjectNote]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM project_notes WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            return [ProjectNote(**dict(r)) for r in rows]

    def add_task(self, content: str, project_id: Optional[int] = None) -> Optional[int]:
        p_id = project_id or self.active_project_id
        if not p_id:
            return None
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO project_tasks(project_id, content, status, created_at) VALUES (?, ?, 'pending', ?)",
                (p_id, content, self._teraz_iso())
            )
            c.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (self._teraz_iso(), p_id))
            c.commit()
            return c.lastrowid
            
    def get_tasks(self, project_id: int) -> List[ProjectTask]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM project_tasks WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            return [ProjectTask(**dict(r)) for r in rows]
