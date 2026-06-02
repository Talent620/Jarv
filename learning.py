"""Silnik uczenia się Jarvisa.

Trzyma w lokalnym SQLite:
- history: log wszystkich destruktywnych akcji (save/update/delete) — do undo i analizy.
- uses: statystyki użycia konkretnych wpisów (które wpisy są najczęściej wyszukiwane).
- preferences: explicit preferencje użytkownika (klucz -> wartość).
- counters: liczniki ogólne (np. ile zapytań trafiło w daną kategorię).

Wszystko współpracuje z MemoryStore przez referencję (DI).

Bezpieczeństwo:
- Każda akcja destruktywna ma wpis w history z dokładnym snapshotem.
- "cofnij" zawsze pyta o potwierdzenie (na zewnątrz, w assistant.py).
- Historia ma górny limit (history_keep z configu) — starsze są kasowane.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import LearningConfig
from core.logging_setup import get_logger
from memory.store import MemoryEntry, MemoryStore, MemoryStoreError

log = get_logger(__name__)


@dataclass
class HistoryRecord:
    """Pojedynczy rekord historii — wystarczy do cofnięcia."""
    id: int
    czas: str
    akcja: str           # save / update / delete
    wpis_id: str
    stara_tresc: str     # przed zmianą (pusty dla save)
    nowa_tresc: str      # po zmianie (pusty dla delete)
    kategoria: str
    cofniete: int        # 0/1


@dataclass
class UndoResult:
    """Wynik operacji cofnięcia."""
    sukces: bool
    opis: str
    przywrocony: Optional[MemoryEntry] = None


class LearningEngine:
    """Lokalny silnik uczenia się oparty o SQLite."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        czas TEXT NOT NULL,
        akcja TEXT NOT NULL CHECK(akcja IN ('save','update','delete')),
        wpis_id TEXT NOT NULL,
        stara_tresc TEXT NOT NULL DEFAULT '',
        nowa_tresc TEXT NOT NULL DEFAULT '',
        kategoria TEXT NOT NULL DEFAULT 'inne',
        cofniete INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_history_czas ON history(czas DESC);
    CREATE INDEX IF NOT EXISTS idx_history_wpis ON history(wpis_id);

    CREATE TABLE IF NOT EXISTS uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        czas TEXT NOT NULL,
        wpis_id TEXT NOT NULL,
        typ TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_uses_wpis ON uses(wpis_id);

    CREATE TABLE IF NOT EXISTS preferences (
        klucz TEXT PRIMARY KEY,
        wartosc TEXT NOT NULL,
        aktualizacja TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS counters (
        klucz TEXT PRIMARY KEY,
        wartosc INTEGER NOT NULL DEFAULT 0,
        aktualizacja TEXT NOT NULL
    );
    """

    def __init__(self, config: LearningConfig, db_path_override: Optional[Path] = None):
        self.config = config
        if db_path_override is not None:
            self._db_path = db_path_override
        else:
            # from core.config import Config  # późny import, żeby uniknąć cykli
            self._db_path = Path(config.db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with closing(self._conn()) as c:
            c.executescript(self.SCHEMA)
            c.commit()

    # =========================================================================
    # Rejestrowanie zdarzeń (wywoływane z assistant.py po operacji na pamięci)
    # =========================================================================

    def record_save(self, wpis: MemoryEntry) -> None:
        self._add_history("save", wpis.id, "", wpis.tresc, wpis.kategoria)
        self._inc_counter(f"kat:{wpis.kategoria}")
        self._inc_counter("akcja:save")
        self._prune_history()

    def record_update(self, stara: MemoryEntry, nowa: MemoryEntry) -> None:
        self._add_history("update", nowa.id, stara.tresc, nowa.tresc, nowa.kategoria)
        self._inc_counter(f"kat:{nowa.kategoria}")
        self._inc_counter("akcja:update")
        # Wpis często aktualizowany — zaznaczamy
        self._inc_counter(f"updates:{nowa.id}")
        self._prune_history()

    def record_delete(self, wpis: MemoryEntry) -> None:
        self._add_history("delete", wpis.id, wpis.tresc, "", wpis.kategoria)
        self._inc_counter("akcja:delete")
        self._prune_history()

    def record_search_hit(self, wpis_id: str) -> None:
        """Notuje, że dany wpis został trafiony przez wyszukiwanie."""
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO uses(czas, wpis_id, typ) VALUES(?, ?, ?)",
                (_teraz_iso(), wpis_id, "search_hit"),
            )
            c.commit()

    # =========================================================================
    # Preferencje
    # =========================================================================

    def _get_profile(self):
        # Spóźniony import dla uzyskania globalnego kontekstu (można ulepszyć DI)
        import sys
        if "jarvis" in sys.modules:
            pass
        return None

    def set_preference(self, klucz: str, wartosc: str, ctx=None) -> None:
        if ctx and hasattr(ctx, "user_profile") and ctx.user_profile:
            ctx.user_profile.set_value(klucz, wartosc)
            
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO preferences(klucz, wartosc, aktualizacja) VALUES(?, ?, ?) "
                "ON CONFLICT(klucz) DO UPDATE SET wartosc=excluded.wartosc, aktualizacja=excluded.aktualizacja",
                (klucz, wartosc, _teraz_iso()),
            )
            c.commit()

    def get_preference(self, klucz: str, ctx=None) -> Optional[str]:
        if ctx and hasattr(ctx, "user_profile") and ctx.user_profile:
            val = ctx.user_profile.get_value(klucz)
            if val: return val
            
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT wartosc FROM preferences WHERE klucz = ?", (klucz,)
            ).fetchone()
            return row["wartosc"] if row else None

    def all_preferences(self) -> Dict[str, str]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT klucz, wartosc FROM preferences ORDER BY klucz").fetchall()
        return {r["klucz"]: r["wartosc"] for r in rows}

    # =========================================================================
    # Statystyki / wzorce
    # =========================================================================

    def top_kategorie(self, n: int = 5) -> List[Tuple[str, int]]:
        """Zwraca top N kategorii po liczbie zapisów."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT klucz, wartosc FROM counters "
                "WHERE klucz LIKE 'kat:%' "
                "ORDER BY wartosc DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [(r["klucz"][4:], r["wartosc"]) for r in rows]

    def licznik(self, klucz: str) -> int:
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT wartosc FROM counters WHERE klucz = ?", (klucz,)
            ).fetchone()
            return int(row["wartosc"]) if row else 0

    def updates_for(self, wpis_id: str) -> int:
        return self.licznik(f"updates:{wpis_id}")

    def most_used_entries(self, limit: int = 5) -> List[Tuple[str, int]]:
        """Lista (wpis_id, count) — najczęściej trafiane wpisy."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT wpis_id, COUNT(*) AS n FROM uses "
                "GROUP BY wpis_id ORDER BY n DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(r["wpis_id"], int(r["n"])) for r in rows]

    def build_user_profile(self, memory: MemoryStore) -> str:
        """Buduje krótki profil użytkownika do wstrzyknięcia w system prompt.

        Zawiera: top kategorie, ostatnie preferencje, częsty kontekst (np. warsztat).
        Nigdy nie zawiera surowej treści wpisów — tylko meta-podsumowanie.
        """
        if not self.config.enable_patterns:
            return ""

        czesci: List[str] = []

        top = self.top_kategorie(5)
        if top:
            min_uses = self.config.patterns_min_uses
            top_filtered = [(k, v) for k, v in top if v >= min_uses]
            if top_filtered:
                czesci.append(
                    "Najczęstsze obszary zainteresowań: "
                    + ", ".join(f"{k} ({v})" for k, v in top_filtered) + "."
                )

        prefs = self.all_preferences()
        if prefs:
            # Tylko klucze, nie wartości (wartości mogą być długie)
            wybrane = list(prefs.items())[:5]
            tekst = "; ".join(f"{k}: {v}" for k, v in wybrane)
            czesci.append(f"Preferencje: {tekst}.")

        return " ".join(czesci) if czesci else ""

    # =========================================================================
    # Historia i cofanie
    # =========================================================================

    def last_history(self, limit: int = 10) -> List[HistoryRecord]:
        """Najnowsze rekordy historii (niezależnie czy cofnięte)."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_history(r) for r in rows]

    def last_undoable(self) -> Optional[HistoryRecord]:
        """Najnowsza niecofnięta akcja."""
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT * FROM history WHERE cofniete = 0 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return _row_to_history(row) if row else None

    def cofnij_ostatnia(self, memory: MemoryStore) -> UndoResult:
        """Cofa ostatnią niecofniętą akcję, korzystając z MemoryStore."""
        rec = self.last_undoable()
        if rec is None:
            return UndoResult(False, "Nie mam żadnej akcji do cofnięcia.")

        try:
            if rec.akcja == "save":
                # Cofnięcie save = usunięcie wpisu (idzie do archiwum)
                usuniety = memory.delete(rec.wpis_id)
                if usuniety is None:
                    return UndoResult(False, "Wpis już nie istnieje — nie ma czego cofać.")
                self._mark_undone(rec.id)
                return UndoResult(True, f"Cofnąłem zapis: \"{rec.nowa_tresc[:80]}\"")

            elif rec.akcja == "update":
                # Cofnięcie update = przywrócenie starej treści
                aktualny = memory.get(rec.wpis_id)
                if aktualny is None:
                    # Wpis usunięty po update — przywracamy z archiwum
                    arch_id = memory.find_archive_entry(rec.wpis_id)
                    if arch_id is None:
                        return UndoResult(False, "Nie znalazłem archiwalnej wersji.")
                    przywrocony = memory.restore_from_archive(arch_id)
                    if przywrocony is None:
                        return UndoResult(False, "Przywracanie z archiwum nie powiodło się.")
                    self._mark_undone(rec.id)
                    return UndoResult(True, "Przywróciłem wpis z archiwum.", przywrocony)
                # Aktualizujemy do starej treści. To stworzy nowy wpis archiwalny —
                # więc historia zachowuje pełną prawdę.
                przywrocony = memory.update(rec.wpis_id, rec.stara_tresc)
                self._mark_undone(rec.id)
                return UndoResult(True,
                                  f"Przywróciłem poprzednią treść wpisu \"{rec.nowa_tresc[:60]}\".",
                                  przywrocony)

            elif rec.akcja == "delete":
                arch_id = memory.find_archive_entry(rec.wpis_id)
                if arch_id is None:
                    return UndoResult(False, "Nie znalazłem zarchiwizowanej wersji wpisu.")
                przywrocony = memory.restore_from_archive(arch_id)
                if przywrocony is None:
                    return UndoResult(False, "Nie udało się odtworzyć wpisu z archiwum.")
                self._mark_undone(rec.id)
                return UndoResult(True, f"Przywróciłem usunięty wpis: \"{przywrocony.tresc[:80]}\".",
                                  przywrocony)

            return UndoResult(False, f"Nieznana akcja do cofnięcia: {rec.akcja}")

        except MemoryStoreError as e:
            log.exception("Błąd przy cofaniu: %s", e)
            return UndoResult(False, f"Błąd pamięci: {e}")
        except Exception as e:
            log.exception("Nieoczekiwany błąd przy cofaniu: %s", e)
            return UndoResult(False, f"Coś poszło nie tak: {e}")

    # =========================================================================
    # Wewnętrzne
    # =========================================================================

    def _add_history(
        self, akcja: str, wpis_id: str, stara: str, nowa: str, kategoria: str,
    ) -> int:
        with closing(self._conn()) as c:
            cur = c.execute(
                "INSERT INTO history(czas, akcja, wpis_id, stara_tresc, nowa_tresc, kategoria) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (_teraz_iso(), akcja, wpis_id, stara, nowa, kategoria),
            )
            c.commit()
            return int(cur.lastrowid or 0)

    def _mark_undone(self, history_id: int) -> None:
        with closing(self._conn()) as c:
            c.execute("UPDATE history SET cofniete = 1 WHERE id = ?", (history_id,))
            c.commit()

    def _inc_counter(self, klucz: str, o: int = 1) -> None:
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO counters(klucz, wartosc, aktualizacja) VALUES(?, ?, ?) "
                "ON CONFLICT(klucz) DO UPDATE SET wartosc=wartosc+excluded.wartosc, "
                "aktualizacja=excluded.aktualizacja",
                (klucz, o, _teraz_iso()),
            )
            c.commit()

    def _prune_history(self) -> None:
        """Usuwa najstarsze wpisy historii powyżej limitu."""
        limit = self.config.history_keep
        if limit <= 0:
            return
        with closing(self._conn()) as c:
            row = c.execute("SELECT COUNT(*) AS n FROM history").fetchone()
            count = int(row["n"]) if row else 0
            if count <= limit:
                return
            do_usuniecia = count - limit
            c.execute(
                "DELETE FROM history WHERE id IN ("
                "  SELECT id FROM history ORDER BY id ASC LIMIT ?"
                ")",
                (do_usuniecia,),
            )
            c.commit()


# ----- helpery modułu -----

def _teraz_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_history(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        id=int(row["id"]),
        czas=str(row["czas"]),
        akcja=str(row["akcja"]),
        wpis_id=str(row["wpis_id"]),
        stara_tresc=str(row["stara_tresc"] or ""),
        nowa_tresc=str(row["nowa_tresc"] or ""),
        kategoria=str(row["kategoria"] or "inne"),
        cofniete=int(row["cofniete"] or 0),
    )
