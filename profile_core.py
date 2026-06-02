"""UserProfile — profil użytkownika dla Jarvisa V2."""

from __future__ import annotations
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Dict, List, Optional
import json

from core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class ProfileConfig:
    db_path: str = "~/.jarvis/profile.db"


class UserProfile:
    """Zarządza profilem użytkownika (preferencje, styl konwersacji, zainteresowania)."""

    def __init__(self, config: ProfileConfig):
        import os
        self.db_path = os.path.expanduser(config.db_path)
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
                CREATE TABLE IF NOT EXISTS profile (
                    klucz TEXT PRIMARY KEY,
                    wartosc TEXT NOT NULL,
                    typ TEXT NOT NULL,
                    aktualizacja TEXT NOT NULL
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    klucz TEXT NOT NULL,
                    stara_wartosc TEXT,
                    nowa_wartosc TEXT,
                    typ TEXT,
                    czas TEXT NOT NULL
                )
            ''')
            c.commit()

    def _teraz_iso(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

    def set_value(self, klucz: str, wartosc: str, typ: str = "preference") -> None:
        """Zapisuje wartość w profilu (np. preferencję, styl rozmowy, zainteresowanie)."""
        stara = self.get_value(klucz)
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO profile(klucz, wartosc, typ, aktualizacja) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(klucz) DO UPDATE SET wartosc=excluded.wartosc, typ=excluded.typ, aktualizacja=excluded.aktualizacja",
                (klucz, wartosc, typ, self._teraz_iso()),
            )
            c.execute(
                "INSERT INTO history(klucz, stara_wartosc, nowa_wartosc, typ, czas) VALUES(?, ?, ?, ?, ?)",
                (klucz, stara, wartosc, typ, self._teraz_iso())
            )
            c.commit()
            log.info(f"Profil_update: {klucz} = {wartosc} ({typ})")

    def get_value(self, klucz: str) -> Optional[str]:
        with closing(self._conn()) as c:
            row = c.execute("SELECT wartosc FROM profile WHERE klucz = ?", (klucz,)).fetchone()
            return row["wartosc"] if row else None

    def get_all_by_type(self, typ: str) -> Dict[str, str]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT klucz, wartosc FROM profile WHERE typ = ? ORDER BY klucz", (typ,)).fetchall()
        return {r["klucz"]: r["wartosc"] for r in rows}

    def get_interests(self) -> List[str]:
        interests_json = self.get_value("interests")
        if not interests_json:
            return []
        try:
            return json.loads(interests_json)
        except Exception:
            return [interests_json]

    def add_interest(self, interest: str) -> None:
        interests = self.get_interests()
        if interest not in interests:
            interests.append(interest)
            self.set_value("interests", json.dumps(interests), typ="zainteresowania")

    def remove_interest(self, interest: str) -> None:
        interests = self.get_interests()
        if interest in interests:
            interests.remove(interest)
            self.set_value("interests", json.dumps(interests), typ="zainteresowania")

    def get_conversation_style(self) -> Optional[str]:
        return self.get_value("Style")

    def set_conversation_style(self, style: str) -> None:
        self.set_value("Style", style, typ="styl")

    def get_profile_summary(self) -> str:
        """Pobiera zbiorcze podsumowanie dla LLM-a (personalizacja)."""
        lines = []
        style = self.get_conversation_style()
        if style:
            lines.append(f"Zalecany styl konwersacji: {style}")
            
        interests = self.get_interests()
        if interests:
            lines.append(f"Zainteresowania użytkownika: {', '.join(interests)}")
            
        prefs = self.get_all_by_type("preference")
        if prefs:
            lines.append("Własne preferencje (UserProfile):")
            for k, v in prefs.items():
                lines.append(f" - {k}: {v}")
                
        return "\n".join(lines)
