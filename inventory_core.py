"""System spisu warsztatowego dla Jarvisa v4.

Śledzi: części, samochody, narzędzia, płyny, materiały.
Auto-pobiera opis i cenę z internetu (DuckDuckGo).

Schema SQLite:
  inventory — główna tabela przedmiotów
  inventory_locations — lokalizacje (regały, szafy, auta)
  inventory_history — log zmian

Komendy głosowe:
  "Dodaj do spisu: filtr oleju Mann W712/93, półka A3, 3 sztuki"
  "Gdzie jest klucz 17mm?"
  "Ile mam filtrów oleju?"
  "Pokaż co jest na półce A3"
  "Szukaj ceny: klocki hamulcowe ATE Golf 4"
  "Pokaż spis samochodów"
  "Dodaj samochód: VW Golf 4 1.9 TDI, 2001, garaż"
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.logging_setup import get_logger
except ImportError:
    import logging
    def get_logger(n): return logging.getLogger(n)

log = get_logger(__name__)

# ── Kategorie ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "samochod":    ("🚗", "Samochody"),
    "silnik":      ("🔧", "Części silnikowe"),
    "elektryka":   ("⚡", "Elektryka / elektronika"),
    "zawieszenie": ("🛞", "Zawieszenie / hamulce"),
    "opony":       ("🛞", "Opony / koła"),
    "plyny":       ("🛢", "Płyny / smary"),
    "nadwozie":    ("🚘", "Nadwozie / karoseria"),
    "narzedziа":   ("🔨", "Narzędzia"),
    "materialy":   ("📦", "Materiały eksploatacyjne"),
    "inne":        ("🏷",  "Inne"),
}

UNITS = ["szt", "l", "ml", "kg", "g", "m", "komplet", "para", "op.", "rolka"]


# ── Struktury danych ─────────────────────────────────────────────────────────

@dataclass
class InventoryItem:
    id:            int
    name:          str
    category:      str        = "inne"
    quantity:      float      = 1.0
    unit:          str        = "szt"
    location:      str        = ""     # "Półka A3", "Garaż", "Bagażnik Golf4"
    description:   str        = ""
    price_pln:     Optional[float] = None
    barcode:       str        = ""
    vin:           str        = ""     # dla samochodów
    make:          str        = ""     # VW, Audi, …
    model:         str        = ""     # Golf, A4, …
    year:          Optional[int] = None
    notes:         str        = ""
    auto_fetched:  bool       = False
    created_at:    str        = ""
    updated_at:    str        = ""

    def cat_icon(self) -> str:
        return CATEGORIES.get(self.category, ("🏷", ""))[0]

    def format_short(self) -> str:
        qty = f"{self.quantity:.0f} {self.unit}" if self.quantity == int(self.quantity) \
              else f"{self.quantity} {self.unit}"
        price = f"  ~{self.price_pln:.0f} zł" if self.price_pln else ""
        loc = f"  📍{self.location}" if self.location else ""
        return f"{self.cat_icon()} [{self.id}] {self.name} — {qty}{loc}{price}"


@dataclass
class InventoryConfig:
    db_path:           str = "~/.jarvis/inventory.db"
    auto_fetch:        bool = True
    fetch_delay_s:     float = 0.5     # opóźnienie między zapytaniami
    max_price_results: int = 8


@dataclass
class FetchResult:
    name:        str
    description: str = ""
    price_pln:   Optional[float] = None
    price_min:   Optional[float] = None
    price_max:   Optional[float] = None
    source:      str = ""
    confidence:  float = 0.0           # 0.0–1.0


# ── Baza danych ──────────────────────────────────────────────────────────────

class InventoryDB:
    def __init__(self, db_path: str):
        self._db = str(Path(os.path.expanduser(db_path)))
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT    NOT NULL,
                    category     TEXT    NOT NULL DEFAULT 'inne',
                    quantity     REAL    NOT NULL DEFAULT 1.0,
                    unit         TEXT    NOT NULL DEFAULT 'szt',
                    location     TEXT    NOT NULL DEFAULT '',
                    description  TEXT    NOT NULL DEFAULT '',
                    price_pln    REAL,
                    barcode      TEXT    NOT NULL DEFAULT '',
                    vin          TEXT    NOT NULL DEFAULT '',
                    make         TEXT    NOT NULL DEFAULT '',
                    model        TEXT    NOT NULL DEFAULT '',
                    year         INTEGER,
                    notes        TEXT    NOT NULL DEFAULT '',
                    auto_fetched INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT    NOT NULL,
                    updated_at   TEXT    NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS inventory_fts
                    USING fts5(name, description, location, make, model,
                               content='inventory', content_rowid='id');

                CREATE TABLE IF NOT EXISTS inventory_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id    INTEGER NOT NULL,
                    action     TEXT    NOT NULL,
                    detail     TEXT    NOT NULL DEFAULT '',
                    ts         TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_inv_cat  ON inventory(category);
                CREATE INDEX IF NOT EXISTS idx_inv_loc  ON inventory(location);
                CREATE INDEX IF NOT EXISTS idx_inv_name ON inventory(name);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add(self, item: InventoryItem) -> int:
        now = _now()
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO inventory
                    (name,category,quantity,unit,location,description,
                     price_pln,barcode,vin,make,model,year,notes,
                     auto_fetched,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item.name, item.category, item.quantity, item.unit,
                 item.location, item.description, item.price_pln,
                 item.barcode, item.vin, item.make, item.model,
                 item.year, item.notes, int(item.auto_fetched), now, now))
            row_id = cur.lastrowid
            # FTS index
            c.execute("INSERT INTO inventory_fts(rowid,name,description,location,make,model)"
                      " VALUES (?,?,?,?,?,?)",
                      (row_id, item.name, item.description,
                       item.location, item.make, item.model))
            self._log(c, row_id, "add", item.name)
            c.commit()
        return row_id

    def update(self, item_id: int, **fields) -> bool:
        if not fields:
            return False
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [item_id]
        with self._conn() as c:
            n = c.execute(f"UPDATE inventory SET {cols} WHERE id=?", vals).rowcount
            if n:
                # Rebuild FTS
                row = c.execute("SELECT name,description,location,make,model FROM inventory WHERE id=?",
                                (item_id,)).fetchone()
                if row:
                    c.execute("DELETE FROM inventory_fts WHERE rowid=?", (item_id,))
                    c.execute("INSERT INTO inventory_fts(rowid,name,description,location,make,model)"
                              " VALUES(?,?,?,?,?,?)",
                              (item_id, row[0], row[1], row[2], row[3], row[4]))
                self._log(c, item_id, "update", str(fields))
            c.commit()
        return n > 0

    def delete(self, item_id: int) -> bool:
        with self._conn() as c:
            n = c.execute("DELETE FROM inventory WHERE id=?", (item_id,)).rowcount
            c.execute("DELETE FROM inventory_fts WHERE rowid=?", (item_id,))
            if n:
                self._log(c, item_id, "delete", "")
            c.commit()
        return n > 0

    def get(self, item_id: int) -> Optional[InventoryItem]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
        return _row_to_item(row) if row else None

    # ── Wyszukiwanie ─────────────────────────────────────────────────────────

    def search(self, query: str = "", category: str = "",
               location: str = "", limit: int = 50) -> List[InventoryItem]:
        with self._conn() as c:
            if query:
                # FTS5 wyszukiwanie pełnotekstowe
                rows = c.execute("""
                    SELECT i.* FROM inventory i
                    JOIN inventory_fts f ON i.id = f.rowid
                    WHERE inventory_fts MATCH ?
                    ORDER BY rank LIMIT ?""",
                    (f'"{query}"*', limit)).fetchall()
                # Fallback LIKE jeśli FTS nic nie zwróci
                if not rows:
                    rows = c.execute("""
                        SELECT * FROM inventory
                        WHERE name LIKE ? OR location LIKE ? OR description LIKE ?
                        ORDER BY name LIMIT ?""",
                        (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
            elif category:
                rows = c.execute(
                    "SELECT * FROM inventory WHERE category=? ORDER BY name LIMIT ?",
                    (category, limit)).fetchall()
            elif location:
                rows = c.execute(
                    "SELECT * FROM inventory WHERE location LIKE ? ORDER BY name LIMIT ?",
                    (f"%{location}%", limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM inventory ORDER BY updated_at DESC LIMIT ?",
                    (limit,)).fetchall()
        return [_row_to_item(r) for r in rows if r]

    def find_location(self, name: str) -> List[Tuple[str, str, float]]:
        """Zwraca [(lokalizacja, id, ilość)] dla pasujących nazw."""
        results = self.search(name, limit=10)
        return [(r.location or "—", str(r.id), r.quantity) for r in results]

    def get_all(self, limit: int = 200) -> List[InventoryItem]:
        return self.search(limit=limit)

    def stats(self) -> Dict[str, Any]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
            cats  = c.execute(
                "SELECT category, COUNT(*) as n FROM inventory GROUP BY category"
            ).fetchall()
            value = c.execute(
                "SELECT SUM(price_pln*quantity) FROM inventory WHERE price_pln IS NOT NULL"
            ).fetchone()[0] or 0.0
            locs  = c.execute(
                "SELECT COUNT(DISTINCT location) FROM inventory WHERE location != ''"
            ).fetchone()[0]
        return {
            "total":      total,
            "categories": {r[0]: r[1] for r in cats},
            "total_value":round(value, 2),
            "locations":  locs,
        }

    # ── Historia ─────────────────────────────────────────────────────────────

    def _log(self, conn, item_id: int, action: str, detail: str) -> None:
        conn.execute(
            "INSERT INTO inventory_history(item_id,action,detail,ts) VALUES(?,?,?,?)",
            (item_id, action, detail[:200], _now()),
        )

    # ── Eksport ──────────────────────────────────────────────────────────────

    def export_csv(self) -> str:
        """Zwraca CSV wszystkich pozycji."""
        import csv, io
        items = self.get_all(limit=10000)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ID","Nazwa","Kategoria","Ilość","Jednostka","Lokalizacja",
                    "Opis","Cena PLN","Marka","Model","Rok","Uwagi","Dodano"])
        for i in items:
            w.writerow([i.id, i.name, i.category, i.quantity, i.unit,
                        i.location, i.description[:100], i.price_pln or "",
                        i.make, i.model, i.year or "", i.notes, i.created_at[:10]])
        return buf.getvalue()


# ── Auto-fetch ceny i opisu ──────────────────────────────────────────────────

class PriceFetcher:
    """Pobiera opis i cenę z DuckDuckGo."""

    _PRICE_RE = re.compile(
        r"(\d[\d\s]*[,.]?\d*)\s*(?:zł|PLN|zl|pln)\b", re.I
    )
    _PRICE_EUR = re.compile(r"(\d[\d\s]*[,.]?\d*)\s*(?:EUR|€)\b", re.I)

    def __init__(self):
        try:
            from duckduckgo_search import DDGS
            self._DDGS = DDGS
            self._ok = True
        except ImportError:
            self._ok = False
            log.warning("duckduckgo-search niedostępny: pip install duckduckgo-search")

    def fetch(self, name: str, category: str = "") -> FetchResult:
        if not self._ok:
            return FetchResult(name=name)

        # Buduj zapytanie kontekstowe
        cat_hint = {"samochod": "samochód ogłoszenie",
                    "silnik":   "część samochodowa sklep",
                    "elektryka":"auto elektryka sklep",
                    "narzedziа":"narzędzia sklep",
                    "opony":    "opona sklep cena"}.get(category, "sklep cena")
        query = f"{name} {cat_hint} cena zł"

        try:
            with self._DDGS() as ddg:
                results = ddg.text(query, region="pl-pl", max_results=8) or []
        except Exception as e:
            log.debug("DDG fetch błąd: %s", e)
            return FetchResult(name=name)

        prices_pln = []
        description = ""

        for r in results:
            body = r.get("body", "") + " " + r.get("title", "")
            # Szukaj cen w PLN
            for m in self._PRICE_RE.finditer(body):
                raw = m.group(1).replace(" ", "").replace(",", ".")
                try:
                    val = float(raw)
                    if 0.5 < val < 500_000:   # sensowny zakres
                        prices_pln.append(val)
                except ValueError:
                    pass
            # Opis z pierwszego wyniki
            if not description and r.get("body"):
                description = r["body"][:400].strip()

        if not prices_pln:
            return FetchResult(name=name, description=description, confidence=0.3)

        # Usuń outliers (top/bottom 10%)
        prices_pln.sort()
        clip = max(1, len(prices_pln) // 10)
        trimmed = prices_pln[clip:-clip] if len(prices_pln) > 4 else prices_pln

        avg   = sum(trimmed) / len(trimmed)
        pmin  = min(prices_pln)
        pmax  = max(prices_pln)

        conf = min(0.9, 0.4 + len(prices_pln) * 0.05)

        return FetchResult(
            name=name,
            description=description,
            price_pln=round(avg, 2),
            price_min=round(pmin, 2),
            price_max=round(pmax, 2),
            confidence=conf,
        )


# ── Główna klasa narzędzia ───────────────────────────────────────────────────

class InventoryTool:
    def __init__(self, cfg: InventoryConfig):
        self.cfg     = cfg
        self.db      = InventoryDB(cfg.db_path)
        self.fetcher = PriceFetcher()

    # ── Dodaj pozycję ────────────────────────────────────────────────────────

    def add_item(
        self,
        name:     str,
        category: str   = "inne",
        quantity: float = 1.0,
        unit:     str   = "szt",
        location: str   = "",
        auto_fetch: bool = True,
        extra:    dict  = None,
    ) -> Tuple[InventoryItem, Optional[FetchResult]]:
        """
        Dodaje pozycję.
        Jeśli auto_fetch=True, automatycznie pobiera opis i cenę.
        Zwraca (item, fetch_result_or_None).
        """
        extra = extra or {}
        fetch_res = None

        if auto_fetch and self.cfg.auto_fetch:
            fetch_res = self.fetcher.fetch(name, category)
            if fetch_res.description and not extra.get("description"):
                extra["description"] = fetch_res.description
            if fetch_res.price_pln and not extra.get("price_pln"):
                extra["price_pln"] = fetch_res.price_pln

        item = InventoryItem(
            id=0, name=name, category=category,
            quantity=quantity, unit=unit, location=location,
            auto_fetched=bool(fetch_res and fetch_res.price_pln),
            **{k: v for k, v in extra.items()
               if k in InventoryItem.__dataclass_fields__},
        )
        item.id = self.db.add(item)
        log.info("Dodano do spisu: %s [id=%d]", name, item.id)
        return item, fetch_res

    # ── Szukaj ──────────────────────────────────────────────────────────────

    def find(self, query: str) -> List[InventoryItem]:
        return self.db.search(query=query)

    def where_is(self, name: str) -> str:
        results = self.db.find_location(name)
        if not results:
            return f"Nie znalazłem \"{name}\" w spisie."
        lines = [f"Znalazłem \"{name}\":"]
        for loc, rid, qty in results[:5]:
            q = f"{qty:.0f}" if qty == int(qty) else str(qty)
            lines.append(f"  📍 {loc}  ({q} szt, id #{rid})")
        return "\n".join(lines)

    def how_many(self, name: str) -> str:
        items = self.db.search(query=name, limit=5)
        if not items:
            return f"Nie mam \"{name}\" w spisie."
        lines = []
        for it in items:
            q = f"{it.quantity:.0f}" if it.quantity == int(it.quantity) else str(it.quantity)
            loc = f" (📍{it.location})" if it.location else ""
            lines.append(f"  {it.name}: {q} {it.unit}{loc}")
        return "Stan magazynowy:\n" + "\n".join(lines)

    def get_by_location(self, location: str) -> str:
        items = self.db.search(location=location, limit=20)
        if not items:
            return f"Nic nie znalazłem w lokalizacji: {location}"
        lines = [f"Co jest w: {location} ({len(items)} pozycji)"]
        for it in items:
            q = f"{it.quantity:.0f}" if it.quantity == int(it.quantity) else str(it.quantity)
            lines.append(f"  {it.cat_icon()} {it.name} — {q} {it.unit}")
        return "\n".join(lines)

    def fetch_price(self, name: str, item_id: Optional[int] = None) -> str:
        res = self.fetcher.fetch(name)
        if not res.price_pln:
            return f"Nie znalazłem ceny dla: {name}"
        lines = [
            f"💰 Szacunkowa cena: {res.price_pln:.0f} zł",
            f"  Zakres: {res.price_min:.0f}–{res.price_max:.0f} zł"
            if res.price_min else "",
            f"  Pewność: {int(res.confidence*100)}%",
        ]
        if res.description:
            lines.append(f"\n📋 {res.description[:200]}")
        if item_id:
            self.db.update(item_id,
                           price_pln=res.price_pln,
                           description=res.description or "",
                           auto_fetched=1)
            lines.append(f"\n✅ Zaktualizowano pozycję #{item_id}")
        return "\n".join(l for l in lines if l)

    def format_stats(self) -> str:
        s = self.db.stats()
        val = f"{s['total_value']:.0f} zł" if s['total_value'] else "brak danych"
        cats_str = ""
        for cat, n in sorted(s["categories"].items(), key=lambda x: -x[1])[:5]:
            icon = CATEGORIES.get(cat, ("🏷", cat))[0]
            cats_str += f"\n  {icon} {CATEGORIES.get(cat,(icon,cat))[1]}: {n}"
        return (
            f"📦 Spis warsztatowy:\n"
            f"  Łącznie: {s['total']} pozycji\n"
            f"  Lokalizacje: {s['locations']}\n"
            f"  Szac. wartość: {val}"
            + cats_str
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _row_to_item(row) -> InventoryItem:
    d = dict(row)
    return InventoryItem(
        id=d["id"], name=d["name"], category=d["category"],
        quantity=d["quantity"], unit=d["unit"],
        location=d.get("location",""), description=d.get("description",""),
        price_pln=d.get("price_pln"), barcode=d.get("barcode",""),
        vin=d.get("vin",""), make=d.get("make",""), model=d.get("model",""),
        year=d.get("year"), notes=d.get("notes",""),
        auto_fetched=bool(d.get("auto_fetched",0)),
        created_at=d.get("created_at",""), updated_at=d.get("updated_at",""),
    )


# ── Parser komendy głosowej ───────────────────────────────────────────────────

def parse_add_command(text: str) -> dict:
    """
    Parsuje: "filtr oleju Mann W712/93, półka A3, 3 sztuki"
    Zwraca: {name, location, quantity, unit, category, ...}
    """
    t = text.strip()

    # Ilość
    qty = 1.0
    unit = "szt"
    qty_m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(szt(?:uk)?i?|litr[ów]?|l\b|kg|g\b|kompl[et]+|par[ę]?|op\.?|m\b)",
        t, re.I
    )
    if qty_m:
        qty = float(qty_m.group(1).replace(",", "."))
        unit_raw = qty_m.group(2).lower().strip(".")
        unit = {"sztuk": "szt", "sztuki": "szt", "sztuke": "szt",
                "litrow": "l", "litry": "l", "litra": "l", "litr": "l",
                "kilogram": "kg", "kilogramy": "kg",
                "komplet": "komplet", "komplety": "komplet",
                "par": "para", "parę": "para"}.get(unit_raw, unit_raw[:4])
        t = t[:qty_m.start()].strip(" ,") + t[qty_m.end():].strip(" ,")

    # Lokalizacja — szukaj "półka X", "szafa X", "regał X", "garaż", "bagażnik"
    location = ""
    loc_m = re.search(
        r"\b(półk[a-ząę]?\s*\w+|regał\s*\w*|szaf[a-ząę]?\s*\w*|"
        r"garaż\w*|magazyn\w*|bagażnik|warsztat|pomieszczenie\s*\w*|"
        r"skrzynka\s*\w*|drawer\s*\w*)\b",
        t, re.I
    )
    if loc_m:
        location = loc_m.group(0).strip()
        t = t[:loc_m.start()].strip(" ,") + t[loc_m.end():].strip(" ,")

    # Kategoria auto-detect
    cat = _detect_category(t)

    # Reszta to nazwa
    name = re.sub(r"\s{2,}", " ", t).strip(" ,;:")

    return {
        "name":     name or "Nowa pozycja",
        "location": location,
        "quantity": qty,
        "unit":     unit,
        "category": cat,
    }


def _detect_category(text: str) -> str:
    t = text.lower()
    rules = [
        (["samochód","auto","pojazd","car","van","vw","audi","bmw","opel",
          "ford","toyota","skoda","škoda","fiat","renault","peugeot"], "samochod"),
        (["silnik","tłok","wałek","rozrząd","pasek","łańcuch","wtryskiwacz",
          "alternator","rozrusznik","olej","filtr oleju","świeca"], "silnik"),
        (["akumulator","alternator","stacyjka","bezpiecznik","przewód","sensor",
          "czujnik","sterownik","ecu","lambda","abs"], "elektryka"),
        (["klocki","tarcza","hamulec","amortyzator","sprężyna","łożysk",
          "wahacz","drążek","tie rod","cv joint","przegub"], "zawieszenie"),
        (["opona","koło","felga","obręcz","valve","wentyl"], "opony"),
        (["olej","płyn","chłodnica","coolant","brake fluid","hamulcowy",
          "wspomaganie","skrzynia biegów","transmission"], "plyny"),
        (["klucz","nasadka","wkrętak","śrubokręt","momentowy","podnośnik",
          "narzędzie","lewarek","klucz dynamo"], "narzedziа"),
        (["farba","taśma","uszczeln","szpachlówka","papier ścierny",
          "czyściwo","szmata"], "materialy"),
    ]
    for keywords, cat in rules:
        if any(kw in t for kw in keywords):
            return cat
    return "inne"
