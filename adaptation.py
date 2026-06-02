"""Silnik adaptacji Jarvisa.

Pozwala bezpiecznie modyfikować zachowanie asystenta na podstawie życzeń
użytkownika i wzorców użycia. Wszystko trafia do osobnej tabeli SQLite,
żadne pliki .py nie są dotykane.

Trzy wymiary adaptacji:
1. STYLE     — preferencje stylu (długość odpowiedzi, ton).
2. INSTRUCTION — własne instrukcje wstrzykiwane do system promptu
                 ("zawsze pomijaj wstępy", "podawaj jednostki SI").
3. ALIAS     — skróty rozwijane przed detekcją intencji ("kj 8" → "klucz 8").

Wszystkie operacje:
- są atomowe (SQLite),
- są wersjonowane (data + flaga aktywna),
- da się je cofnąć (cofnij_ostatnia_adaptacje),
- da się zresetować całość (reset_all).

Bezpieczeństwo:
- Instrukcje użytkownika są sanityzowane przed wstrzyknięciem w prompt.
- System prompt jasno mówi, że INSTRUKCJE nie mogą przeważać nad zasadami
  bezpieczeństwa.
- Aliasy są word-bounded, żeby "kj" nie rozwijało się wewnątrz "kjeden".
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.logging_setup import get_logger
from ai.prompt import sanitize_memory_text

log = get_logger(__name__)


# =============================================================================
# Modele danych
# =============================================================================

@dataclass
class Adaptation:
    """Pojedyncza adaptacja zachowania asystenta."""
    id: int
    typ: str          # "style" | "instruction" | "alias"
    klucz: str        # nazwa parametru / skrót / id instrukcji
    wartosc: str      # wartość preferencji / treść instrukcji / rozwinięcie aliasu
    aktywna: int      # 1/0
    data: str         # ISO 8601
    opis: str         # human-readable

    @property
    def jest_aktywna(self) -> bool:
        return bool(self.aktywna)


# Dostępne typy stylu i ich możliwe wartości
STYLE_PARAMS: Dict[str, List[str]] = {
    "length": ["krótko", "normalnie", "szczegółowo"],
    "tone": ["formalny", "normalny", "swobodny"],
}

# Domyślne wartości stylu — używane jeśli użytkownik nic nie ustawił
STYLE_DEFAULTS: Dict[str, str] = {
    "length": "normalnie",
    "tone": "normalny",
}


# =============================================================================
# Engine
# =============================================================================

class AdaptationEngine:
    """Silnik adaptacji. Współdzieli plik SQLite z LearningEngine.

    Tabela `adaptations` jest tworzona z `IF NOT EXISTS`, więc bezpiecznie
    współistnieje z LearningEngine używającym tej samej bazy.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS adaptations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        typ TEXT NOT NULL CHECK(typ IN ('style','instruction','alias')),
        klucz TEXT NOT NULL,
        wartosc TEXT NOT NULL,
        aktywna INTEGER NOT NULL DEFAULT 1,
        data TEXT NOT NULL,
        opis TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_adaptations_typ ON adaptations(typ, aktywna);
    CREATE INDEX IF NOT EXISTS idx_adaptations_klucz ON adaptations(typ, klucz);
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        # Cache aliasów — odświeżany przy każdej modyfikacji
        self._alias_cache: Optional[List[Tuple[str, str]]] = None

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_schema(self) -> None:
        with closing(self._conn()) as c:
            c.executescript(self.SCHEMA)
            c.commit()

    # =========================================================================
    # STYLE — długość, ton
    # =========================================================================

    def set_style(self, param: str, wartosc: str) -> Adaptation:
        """Ustawia preferencję stylu. Zastępuje poprzednią dla tego paramu."""
        if param not in STYLE_PARAMS:
            raise ValueError(
                f"Nieznany parametr stylu: {param}. Dozwolone: {list(STYLE_PARAMS)}"
            )
        if wartosc not in STYLE_PARAMS[param]:
            raise ValueError(
                f"Nieznana wartość '{wartosc}' dla {param}. "
                f"Dozwolone: {STYLE_PARAMS[param]}"
            )

        opis = f"Styl: {param} = {wartosc}"
        with closing(self._conn()) as c:
            # Deaktywujemy poprzednie wpisy dla tego paramu (zachowujemy historię)
            c.execute(
                "UPDATE adaptations SET aktywna = 0 "
                "WHERE typ = 'style' AND klucz = ? AND aktywna = 1",
                (param,),
            )
            cur = c.execute(
                "INSERT INTO adaptations(typ, klucz, wartosc, aktywna, data, opis) "
                "VALUES('style', ?, ?, 1, ?, ?)",
                (param, wartosc, _teraz_iso(), opis),
            )
            c.commit()
            return self._get_by_id(int(cur.lastrowid or 0))

    def get_style(self, param: str) -> str:
        """Zwraca aktywną wartość stylu lub default."""
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT wartosc FROM adaptations "
                "WHERE typ = 'style' AND klucz = ? AND aktywna = 1 "
                "ORDER BY id DESC LIMIT 1",
                (param,),
            ).fetchone()
        if row:
            return str(row["wartosc"])
        return STYLE_DEFAULTS.get(param, "")

    def style_directive(self) -> str:
        """Zwraca tekst do wstrzyknięcia w system prompt opisujący preferencje stylu."""
        kawalki: List[str] = []

        dlugosc = self.get_style("length")
        if dlugosc == "krótko":
            kawalki.append(
                "Odpowiadaj bardzo krótko — 1-2 zdania. Bez wstępów ani podsumowań."
            )
        elif dlugosc == "szczegółowo":
            kawalki.append(
                "Możesz dawać dłuższe odpowiedzi (3-6 zdań) z konkretnymi przykładami."
            )
        # "normalnie" = nic nie dodawaj, domyślne zachowanie z system promptu

        ton = self.get_style("tone")
        if ton == "formalny":
            kawalki.append("Mów oficjalnie, używaj formy 'pan'.")
        elif ton == "swobodny":
            kawalki.append("Mów luźno, na ty, bez formalnych zwrotów.")

        return " ".join(kawalki)

    # =========================================================================
    # INSTRUCTION — własne instrukcje użytkownika
    # =========================================================================

    def add_instruction(self, tresc: str) -> Adaptation:
        """Dodaje własną instrukcję. Treść jest sanityzowana."""
        if not tresc or not tresc.strip():
            raise ValueError("Pusta instrukcja")

        # Sanityzacja — żeby instrukcja nie próbowała zmienić tożsamości modelu
        bezp = sanitize_memory_text(tresc.strip())
        # Skróć do rozsądnej długości
        if len(bezp) > 300:
            bezp = bezp[:300] + "…"

        klucz = uuid.uuid4().hex[:12]
        opis = f"Instrukcja: {bezp[:80]}"

        with closing(self._conn()) as c:
            cur = c.execute(
                "INSERT INTO adaptations(typ, klucz, wartosc, aktywna, data, opis) "
                "VALUES('instruction', ?, ?, 1, ?, ?)",
                (klucz, bezp, _teraz_iso(), opis),
            )
            c.commit()
        return self._get_by_id(int(cur.lastrowid or 0))

    def list_instructions(self, tylko_aktywne: bool = True) -> List[Adaptation]:
        with closing(self._conn()) as c:
            if tylko_aktywne:
                rows = c.execute(
                    "SELECT * FROM adaptations WHERE typ = 'instruction' AND aktywna = 1 "
                    "ORDER BY id ASC"
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM adaptations WHERE typ = 'instruction' ORDER BY id ASC"
                ).fetchall()
        return [_row_to_adaptation(r) for r in rows]

    def remove_instruction(self, klucz: str) -> bool:
        """Deaktywuje instrukcję po jej kluczu (UUID). Zwraca True jeśli istniała."""
        with closing(self._conn()) as c:
            cur = c.execute(
                "UPDATE adaptations SET aktywna = 0 "
                "WHERE typ = 'instruction' AND klucz = ? AND aktywna = 1",
                (klucz,),
            )
            c.commit()
            return cur.rowcount > 0

    def remove_instruction_by_index(self, idx: int) -> Optional[Adaptation]:
        """Usuwa N-tą aktywną instrukcję (1-indexed, jak wyświetlana użytkownikowi)."""
        aktywne = self.list_instructions(tylko_aktywne=True)
        if idx < 1 or idx > len(aktywne):
            return None
        cel = aktywne[idx - 1]
        self.remove_instruction(cel.klucz)
        return cel

    def instructions_block(self) -> str:
        """Zwraca blok tekstu do wklejenia do system promptu, lub pusty string."""
        ins = self.list_instructions(tylko_aktywne=True)
        if not ins:
            return ""
        linie = ["TWOJE WŁASNE INSTRUKCJE OD UŻYTKOWNIKA (priorytet poniżej zasad 1-9):"]
        for i, a in enumerate(ins, start=1):
            linie.append(f"  {i}. {a.wartosc}")
        linie.append(
            "Te instrukcje pochodzą od użytkownika podczas tej i poprzednich rozmów. "
            "Stosuj je, ale NIGDY nie kosztem zasad bezpieczeństwa i prawdy."
        )
        return "\n".join(linie)

    # =========================================================================
    # ALIAS — skróty językowe
    # =========================================================================

    def set_alias(self, skrot: str, rozwiniecie: str) -> Adaptation:
        """Dodaje/aktualizuje alias. 'kj 8' → 'klucz nasadowy 8'."""
        if not skrot or not skrot.strip():
            raise ValueError("Pusty skrót")
        if not rozwiniecie or not rozwiniecie.strip():
            raise ValueError("Puste rozwinięcie")

        skrot_clean = skrot.strip().lower()
        rozw_clean = rozwiniecie.strip()

        if skrot_clean == rozw_clean.lower():
            raise ValueError("Skrót nie może być identyczny z rozwinięciem")
        if len(skrot_clean) > 60 or len(rozw_clean) > 300:
            raise ValueError("Skrót max 60 znaków, rozwinięcie max 300")

        opis = f"Alias: '{skrot_clean}' → '{rozw_clean}'"
        with closing(self._conn()) as c:
            c.execute(
                "UPDATE adaptations SET aktywna = 0 "
                "WHERE typ = 'alias' AND LOWER(klucz) = ? AND aktywna = 1",
                (skrot_clean,),
            )
            cur = c.execute(
                "INSERT INTO adaptations(typ, klucz, wartosc, aktywna, data, opis) "
                "VALUES('alias', ?, ?, 1, ?, ?)",
                (skrot_clean, rozw_clean, _teraz_iso(), opis),
            )
            c.commit()
        self._alias_cache = None
        return self._get_by_id(int(cur.lastrowid or 0))

    def remove_alias(self, skrot: str) -> bool:
        with closing(self._conn()) as c:
            cur = c.execute(
                "UPDATE adaptations SET aktywna = 0 "
                "WHERE typ = 'alias' AND LOWER(klucz) = ? AND aktywna = 1",
                (skrot.strip().lower(),),
            )
            c.commit()
        self._alias_cache = None
        return cur.rowcount > 0

    def list_aliases(self) -> List[Tuple[str, str]]:
        """Lista aktywnych aliasów: [(skrot, rozwinięcie), ...]. Cache'owana."""
        if self._alias_cache is not None:
            return self._alias_cache
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT klucz, wartosc FROM adaptations "
                "WHERE typ = 'alias' AND aktywna = 1 "
                "ORDER BY LENGTH(klucz) DESC"  # dłuższe pierwsze (zapobiega kolizjom)
            ).fetchall()
        self._alias_cache = [(str(r["klucz"]), str(r["wartosc"])) for r in rows]
        return self._alias_cache

    def expand_aliases(self, tekst: str) -> Tuple[str, List[str]]:
        """Rozwija aliasy w tekście. Zwraca (rozwinięty_tekst, lista_użytych_aliasów).

        Word-bounded żeby 'kj' nie matchowało wewnątrz 'kjeden'.
        Case-insensitive.
        """
        if not tekst:
            return tekst, []
        uzyte: List[str] = []
        out = tekst
        for skrot, rozw in self.list_aliases():
            # \b nie zawsze działa dla polskich znaków — używamy własnego boundary
            wzorzec = re.compile(
                r"(?<![\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ])"
                + re.escape(skrot)
                + r"(?![\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ])",
                re.IGNORECASE,
            )
            new_out, n = wzorzec.subn(rozw, out)
            if n > 0:
                uzyte.append(skrot)
                out = new_out
        return out, uzyte

    # =========================================================================
    # Cofanie / reset
    # =========================================================================

    def last_active_adaptation(self) -> Optional[Adaptation]:
        """Najnowsza wciąż aktywna adaptacja — kandydatka do cofnięcia."""
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT * FROM adaptations WHERE aktywna = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return _row_to_adaptation(row) if row else None

    def cofnij_ostatnia_adaptacje(self) -> Optional[Adaptation]:
        """Deaktywuje najnowszą aktywną adaptację. Zwraca to, co cofnięto."""
        ost = self.last_active_adaptation()
        if ost is None:
            return None
        with closing(self._conn()) as c:
            c.execute("UPDATE adaptations SET aktywna = 0 WHERE id = ?", (ost.id,))
            c.commit()
        self._alias_cache = None
        return ost

    def reset_all(self) -> int:
        """Deaktywuje WSZYSTKIE adaptacje. Zwraca ile było aktywnych."""
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM adaptations WHERE aktywna = 1"
            ).fetchone()
            ile = int(row["n"]) if row else 0
            c.execute("UPDATE adaptations SET aktywna = 0 WHERE aktywna = 1")
            c.commit()
        self._alias_cache = None
        return ile

    # =========================================================================
    # Podgląd
    # =========================================================================

    def list_all(self) -> List[Adaptation]:
        """Wszystkie aktywne adaptacje."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM adaptations WHERE aktywna = 1 ORDER BY typ, id ASC"
            ).fetchall()
        return [_row_to_adaptation(r) for r in rows]

    def summary(self) -> str:
        """Czytelne podsumowanie wszystkich aktywnych adaptacji."""
        adaptacje = self.list_all()
        if not adaptacje:
            return "Brak żadnych adaptacji — działam z domyślnymi ustawieniami."

        linie: List[str] = []

        style = [a for a in adaptacje if a.typ == "style"]
        if style:
            linie.append("Styl:")
            for a in style:
                linie.append(f"  • {a.klucz}: {a.wartosc}")

        instrukcje = [a for a in adaptacje if a.typ == "instruction"]
        if instrukcje:
            linie.append("Instrukcje:")
            for i, a in enumerate(instrukcje, start=1):
                linie.append(f"  {i}. {a.wartosc}")

        aliasy = [a for a in adaptacje if a.typ == "alias"]
        if aliasy:
            linie.append("Aliasy:")
            for a in aliasy:
                linie.append(f"  • '{a.klucz}' → '{a.wartosc}'")

        return "\n".join(linie)

    # =========================================================================
    # Propozycje proaktywne (na podstawie sygnałów z konwersacji)
    # =========================================================================

    def record_signal(self, sygnal: str) -> None:
        """Notuje sygnał użytkownika ('krócej', 'dłużej', 'formalniej' itp.)."""
        with closing(self._conn()) as c:
            # Sygnały trzymamy jako specjalny typ instruction z kluczem signal:
            klucz = f"signal:{sygnal}"
            row = c.execute(
                "SELECT id, wartosc FROM adaptations "
                "WHERE typ = 'instruction' AND klucz = ?",
                (klucz,),
            ).fetchone()
            if row:
                nowa = int(row["wartosc"]) + 1
                c.execute(
                    "UPDATE adaptations SET wartosc = ?, aktywna = 1, data = ? WHERE id = ?",
                    (str(nowa), _teraz_iso(), int(row["id"])),
                )
            else:
                c.execute(
                    "INSERT INTO adaptations(typ, klucz, wartosc, aktywna, data, opis) "
                    "VALUES('instruction', ?, '1', 1, ?, ?)",
                    (klucz, _teraz_iso(), f"sygnał: {sygnal}"),
                )
            c.commit()

    def signal_count(self, sygnal: str) -> int:
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT wartosc FROM adaptations "
                "WHERE typ = 'instruction' AND klucz = ? AND aktywna = 1",
                (f"signal:{sygnal}",),
            ).fetchone()
        return int(row["wartosc"]) if row else 0

    def suggest_adaptation(self) -> Optional[Tuple[str, str, str]]:
        """Sugeruje adaptację na podstawie sygnałów.

        Zwraca (nazwa_sugestii, opis_do_uzytkownika, param_do_zastosowania) albo None.
        """
        prog = 3  # po 3 sygnałach proponujemy

        # 1) Długość — częste "krócej"
        if (self.signal_count("krocej") >= prog
                and self.get_style("length") != "krótko"):
            return (
                "length=krótko",
                "Zauważyłem, że często prosisz o krótsze odpowiedzi. "
                "Mam domyślnie pisać krócej?",
                "length:krótko",
            )

        if (self.signal_count("dluzej") >= prog
                and self.get_style("length") != "szczegółowo"):
            return (
                "length=szczegółowo",
                "Zauważyłem, że często prosisz o więcej szczegółów. "
                "Mam domyślnie pisać bardziej szczegółowo?",
                "length:szczegółowo",
            )

        # 2) Ton — częste "luźniej"
        if (self.signal_count("luzniej") >= prog
                and self.get_style("tone") != "swobodny"):
            return (
                "tone=swobodny",
                "Często prosisz o luźniejszy ton. Mam domyślnie mówić swobodniej?",
                "tone:swobodny",
            )

        return None

    def apply_suggestion(self, param_string: str) -> Optional[Adaptation]:
        """Stosuje sugestię w formacie 'param:wartość'."""
        if ":" not in param_string:
            return None
        param, wartosc = param_string.split(":", 1)
        try:
            return self.set_style(param.strip(), wartosc.strip())
        except ValueError as e:
            log.warning("apply_suggestion: %s", e)
            return None

    def clear_signal(self, sygnal: str) -> None:
        """Czyści licznik konkretnego sygnału (po zastosowaniu sugestii)."""
        with closing(self._conn()) as c:
            c.execute(
                "UPDATE adaptations SET aktywna = 0 "
                "WHERE typ = 'instruction' AND klucz = ?",
                (f"signal:{sygnal}",),
            )
            c.commit()

    # =========================================================================
    # Pomocnicze
    # =========================================================================

    def _get_by_id(self, adaptation_id: int) -> Adaptation:
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT * FROM adaptations WHERE id = ?", (adaptation_id,)
            ).fetchone()
        if not row:
            raise RuntimeError(f"Adaptacja {adaptation_id} zniknęła zaraz po zapisie")
        return _row_to_adaptation(row)


# =============================================================================
# Helpery modułu
# =============================================================================

def _teraz_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_adaptation(row: sqlite3.Row) -> Adaptation:
    return Adaptation(
        id=int(row["id"]),
        typ=str(row["typ"]),
        klucz=str(row["klucz"]),
        wartosc=str(row["wartosc"]),
        aktywna=int(row["aktywna"]),
        data=str(row["data"]),
        opis=str(row["opis"] or ""),
    )
