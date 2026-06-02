"""Pamięć długoterminowa Jarvisa oparta o ChromaDB.

Funkcje:
- Zapis z auto-deduplikacją po podobieństwie semantycznym.
- Wyszukiwanie z filtrowaniem po kategorii i progiem jakości.
- Aktualizacja z wersjonowaniem (stara wersja idzie do osobnej kolekcji "archive").
- Usuwanie z możliwością przywrócenia (delete też trafia do archive).
- Eksport/import całej pamięci do/z JSON.

Filozofia: pamięć jest źródłem prawdy. Cofnięcie zmiany ZAWSZE jest możliwe,
dopóki wpis nie zostanie ręcznie wyczyszczony z archive.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from core.config import MemoryConfig
from core.logging_setup import get_logger

log = get_logger(__name__)

# Domyślny embedder — opcjonalny, MemoryStore akceptuje też custom (do testów)
try:
    import chromadb
    # chromadb >= 1.0 przeniosło typy do chromadb.api.types
    try:
        from chromadb.api.types import EmbeddingFunction, Documents, Embeddings  # type: ignore[attr-defined]
    except ImportError:
        from chromadb import EmbeddingFunction, Documents, Embeddings  # type: ignore[attr-defined]
    CHROMADB_AVAILABLE = True
except ImportError:  # pragma: no cover
    CHROMADB_AVAILABLE = False


# =============================================================================
# Embedding function — wielojęzyczna, działająca po polsku
# =============================================================================

class PolishMultilingualEmbedding:
    """Embeddings przez sentence-transformers. Lazy loading.

    Implementuje protokół chromadb.EmbeddingFunction:
        __call__(input: Documents) -> Embeddings
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self._model_name = model_name
        self._model: Optional[Any] = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "Brak biblioteki 'sentence-transformers'. "
                    "Zainstaluj: pip install sentence-transformers"
                ) from e
            log.info("Ładuję model embeddingów: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def __call__(self, input: Any) -> List[List[float]]:
        teksty = list(input)
        if not teksty:
            return []
        model = self._ensure_model()
        wektory = model.encode(teksty, convert_to_numpy=True, show_progress_bar=False)
        return wektory.tolist()

    def name(self) -> str:
        return f"polish_multilingual:{self._model_name}"


# =============================================================================
# Model wpisu
# =============================================================================

@dataclass
class MemoryEntry:
    """Pojedynczy wpis w pamięci."""
    id: str
    tresc: str
    kategoria: str = "inne"
    tagi: List[str] = field(default_factory=list)
    data: str = ""              # ISO 8601, czas utworzenia
    aktualizacja: str = ""      # ISO 8601, czas ostatniej zmiany
    zrodlo: str = "uzytkownik"
    wersja: int = 1             # nr wersji wpisu
    dystans: Optional[float] = None  # ustawiane tylko przy wynikach wyszukiwania

    def to_chroma_metadata(self) -> Dict[str, Any]:
        """ChromaDB wymaga scalar values w metadata."""
        return {
            "kategoria": self.kategoria,
            "tagi": ",".join(self.tagi),
            "data": self.data,
            "aktualizacja": self.aktualizacja,
            "zrodlo": self.zrodlo,
            "wersja": self.wersja,
        }

    @classmethod
    def from_chroma(
        cls,
        wpis_id: str,
        tresc: str,
        metadata: Dict[str, Any],
        dystans: Optional[float] = None,
    ) -> "MemoryEntry":
        tagi_str = metadata.get("tagi", "") or ""
        tagi = [t.strip() for t in tagi_str.split(",") if t.strip()] if isinstance(tagi_str, str) else []
        return cls(
            id=wpis_id,
            tresc=tresc,
            kategoria=str(metadata.get("kategoria", "inne") or "inne"),
            tagi=tagi,
            data=str(metadata.get("data", "") or ""),
            aktualizacja=str(metadata.get("aktualizacja", "") or ""),
            zrodlo=str(metadata.get("zrodlo", "uzytkownik") or "uzytkownik"),
            wersja=int(metadata.get("wersja", 1) or 1),
            dystans=dystans,
        )


# =============================================================================
# Heurystyka kategoryzacji
# =============================================================================

_KATEGORIE_REGULY: List[Tuple[str, List[str]]] = [
    ("narzedzia",   ["klucz", "śrubokręt", "srubokret", "wiertarka", "młotek", "mlotek",
                     "imadło", "imadlo", "szczypce", "miernik", "lutownica", "imbus",
                     "torx", "piła", "pila", "wkrętarka", "wkretarka", "nasadk"]),
    ("czesci",      ["śruba", "sruba", "nakrętka", "nakretka", "podkładka", "podkladka",
                     "łożysko", "lozysko", "uszczelka", "filtr", "pasek", "kabel",
                     "przewód", "przewod", "bezpiecznik", "kondensator", "rezystor",
                     "dioda", "tranzystor", "wkład", "wklad"]),
    ("urzadzenia",  ["udoo", "raspberry", "router", "kamera", "drukarka", "komputer",
                     "laptop", "telefon", "ładowarka", "ladowarka", "switch", "monitor"]),
    ("projekty",    ["projekt", "magazynauto", "nvr", "skrypt", "instalator", "kod",
                     "aplikacja", "pwa", "warsztat"]),
    ("przypomnienia",["przypomnij", "pamiętaj na", "pamietaj na", "nie zapomnij",
                      "termin", "deadline", "do piątku", "do piatku"]),
    ("preferencje", ["wolę", "wole", "lubię", "lubie", "nie lubię", "nie lubie",
                     "preferuję", "preferuje", "zwykle używam", "zwykle uzywam"]),
    ("problemy",    ["nie działa", "nie dziala", "problem", "błąd", "blad", "awaria",
                     "psuje się", "psuje sie", "nie odpala", "wywala", "uszkodzon"]),
    ("rozwiazania", ["naprawiłem", "naprawilem", "rozwiązanie", "rozwiazanie",
                     "pomogło", "pomoglo", "wystarczy", "trzeba"]),
    ("miejsca",     ["leży", "lezy", "schowałem", "schowalem", "trzymam w",
                     "w szufladzie", "w skrzynce", "w szafie", "w garażu", "w garazu",
                     "pod stołem", "pod stolem", "na półce", "na polce"]),
    ("kontakty",    ["telefon do", "numer do", "mail do", "kontakt do", "adres do"]),
]


def auto_kategoria(tresc: str) -> str:
    """Prosta heurystyka kategoryzacji po słowach kluczowych. Pierwsze trafienie wygrywa."""
    t = (tresc or "").lower()
    for kat, slowa in _KATEGORIE_REGULY:
        if any(s in t for s in slowa):
            return kat
    return "inne"


# =============================================================================
# MemoryStore
# =============================================================================

class MemoryStoreError(Exception):
    """Błąd pamięci."""


class MemoryStore:
    """Fasada nad ChromaDB z pełnym CRUD, dedup, wersjami i archiwum."""

    def __init__(
        self,
        config: MemoryConfig,
        embedding_fn: Optional[Callable[[Any], List[List[float]]]] = None,
        persist_dir_override: Optional[Path] = None,
    ):
        if not CHROMADB_AVAILABLE:
            raise MemoryStoreError(
                "ChromaDB nie jest zainstalowane. Uruchom: pip install chromadb"
            )
        self.config = config
        self._embedding_fn = embedding_fn or PolishMultilingualEmbedding(config.embedding_model)

        persist_dir = persist_dir_override or Path(
            os.path.expandvars(os.path.expanduser(config.dir))
        )
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._persist_dir = persist_dir

        log.info("Inicjalizuję pamięć w: %s", persist_dir)
        self._client = chromadb.PersistentClient(path=str(persist_dir))

        # Główna kolekcja — bieżąca wiedza
        self._main = self._client.get_or_create_collection(
            name=config.collection,
            embedding_function=self._embedding_fn,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        # Archiwum — stare wersje, usunięte wpisy. Embedding ten sam, żeby
        # móc szukać też w archiwum (do undo).
        self._archive = self._client.get_or_create_collection(
            name=config.archive_collection,
            embedding_function=self._embedding_fn,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )

    # ----- Operacje podstawowe -----

    def add(
        self,
        tresc: str,
        kategoria: Optional[str] = None,
        tagi: Optional[List[str]] = None,
        skip_dedup: bool = False,
    ) -> Tuple[MemoryEntry, bool]:
        """Zapisuje wpis. Zwraca (wpis, was_duplicate).

        Jeśli treść jest praktycznie taka sama jak istniejący wpis (poniżej
        dedup_threshold), aktualizujemy tylko datę i zwracamy was_duplicate=True.
        """
        if not tresc or not tresc.strip():
            raise ValueError("Treść do zapisu nie może być pusta")

        tresc_clean = tresc.strip()

        if not skip_dedup:
            duplikat = self._znajdz_duplikat(tresc_clean)
            if duplikat is not None:
                duplikat.aktualizacja = _teraz_iso()
                self._main.update(
                    ids=[duplikat.id],
                    documents=[duplikat.tresc],
                    metadatas=[duplikat.to_chroma_metadata()],
                )
                log.info("Wykryto duplikat (id=%s), odświeżam datę", duplikat.id)
                return duplikat, True

        wpis = MemoryEntry(
            id=str(uuid.uuid4()),
            tresc=tresc_clean,
            kategoria=(kategoria or auto_kategoria(tresc_clean)).lower(),
            tagi=tagi or [],
            data=_teraz_iso(),
            aktualizacja=_teraz_iso(),
            zrodlo="uzytkownik",
            wersja=1,
        )
        self._main.add(
            ids=[wpis.id],
            documents=[wpis.tresc],
            metadatas=[wpis.to_chroma_metadata()],
        )
        log.info("Zapisano wpis id=%s kategoria=%s", wpis.id, wpis.kategoria)
        return wpis, False

    def search(
        self,
        zapytanie: str,
        limit: Optional[int] = None,
        kategoria: Optional[str] = None,
        max_distance: Optional[float] = None,
    ) -> List[MemoryEntry]:
        """Szuka semantycznie. Filtruje po kategorii i progu dystansu."""
        if not zapytanie or not zapytanie.strip():
            return []

        n = limit or self.config.search_limit
        where: Optional[Dict[str, Any]] = None
        if kategoria:
            where = {"kategoria": kategoria.lower()}

        try:
            res = self._main.query(
                query_texts=[zapytanie.strip()],
                n_results=max(1, min(n, 20)),
                where=where,
            )
        except Exception as e:
            log.exception("Błąd zapytania do pamięci: %s", e)
            return []

        wyniki = _parsuj_query_result(res)
        if max_distance is not None:
            wyniki = [w for w in wyniki if w.dystans is None or w.dystans <= max_distance]
        return wyniki

    def get(self, wpis_id: str) -> Optional[MemoryEntry]:
        """Pobiera konkretny wpis po ID."""
        try:
            res = self._main.get(ids=[wpis_id])
        except Exception as e:
            log.exception("Błąd get(%s): %s", wpis_id, e)
            return None
        ids = res.get("ids") or []
        if not ids:
            return None
        return MemoryEntry.from_chroma(
            ids[0],
            (res.get("documents") or [""])[0],
            (res.get("metadatas") or [{}])[0] or {},
        )

    def update(self, wpis_id: str, nowa_tresc: str) -> Optional[MemoryEntry]:
        """Aktualizuje wpis. Stara wersja idzie do archiwum. Zwraca nową wersję."""
        if not nowa_tresc or not nowa_tresc.strip():
            raise ValueError("Nowa treść nie może być pusta")

        stary = self.get(wpis_id)
        if stary is None:
            log.warning("update: wpis %s nie istnieje", wpis_id)
            return None

        # 1. Zapisujemy starą wersję do archiwum (z tym samym ID? nie — nowe ID
        #    w archive, w metadanych referencja do oryginalnego ID)
        self._do_archiwum(stary, powod="update")

        # 2. Aktualizujemy główny wpis
        stary.tresc = nowa_tresc.strip()
        stary.kategoria = auto_kategoria(stary.tresc) or stary.kategoria
        stary.aktualizacja = _teraz_iso()
        stary.wersja += 1
        self._main.update(
            ids=[stary.id],
            documents=[stary.tresc],
            metadatas=[stary.to_chroma_metadata()],
        )
        log.info("Zaktualizowano wpis id=%s do wersji %d", stary.id, stary.wersja)
        return stary

    def delete(self, wpis_id: str) -> Optional[MemoryEntry]:
        """Usuwa wpis (z zachowaniem w archiwum). Zwraca usunięty wpis lub None."""
        stary = self.get(wpis_id)
        if stary is None:
            return None
        self._do_archiwum(stary, powod="delete")
        try:
            self._main.delete(ids=[wpis_id])
        except Exception as e:
            log.exception("Błąd przy delete(%s): %s", wpis_id, e)
            return None
        log.info("Usunięto wpis id=%s (do archiwum)", wpis_id)
        return stary

    def restore_from_archive(self, archive_id: str) -> Optional[MemoryEntry]:
        """Przywraca wpis z archiwum do głównej kolekcji."""
        try:
            res = self._archive.get(ids=[archive_id])
        except Exception:
            return None
        ids = res.get("ids") or []
        if not ids:
            return None
        meta = (res.get("metadatas") or [{}])[0] or {}
        doc = (res.get("documents") or [""])[0]
        oryginalny_id = str(meta.get("oryginalny_id", ids[0]))

        # Sprawdź czy oryginalny istnieje
        istnieje = self.get(oryginalny_id)
        if istnieje is not None:
            # Najpierw zarchiwizuj obecną wersję, potem nadpisz
            self._do_archiwum(istnieje, powod="restore_overwrite")
            istnieje.tresc = doc
            istnieje.kategoria = str(meta.get("kategoria") or istnieje.kategoria)
            istnieje.aktualizacja = _teraz_iso()
            istnieje.wersja += 1
            self._main.update(
                ids=[istnieje.id],
                documents=[istnieje.tresc],
                metadatas=[istnieje.to_chroma_metadata()],
            )
            self._archive.delete(ids=[archive_id])
            return istnieje

        # Wpis usunięty — odtwarzamy z oryginalnym ID
        entry = MemoryEntry(
            id=oryginalny_id,
            tresc=doc,
            kategoria=str(meta.get("kategoria", "inne") or "inne"),
            tagi=[t for t in (meta.get("tagi") or "").split(",") if t],
            data=str(meta.get("data") or _teraz_iso()),
            aktualizacja=_teraz_iso(),
            wersja=int(meta.get("wersja", 1) or 1) + 1,
        )
        self._main.add(
            ids=[entry.id],
            documents=[entry.tresc],
            metadatas=[entry.to_chroma_metadata()],
        )
        self._archive.delete(ids=[archive_id])
        return entry

    def find_archive_entry(self, original_id: str) -> Optional[str]:
        """Znajduje najnowszy wpis w archiwum dla danego original_id."""
        try:
            res = self._archive.get(where={"oryginalny_id": original_id})
        except Exception:
            return None
        ids = res.get("ids") or []
        if not ids:
            return None
        metas = res.get("metadatas") or []
        # Wybierz najnowszy po polu zarchiwizowany_o
        kandydaci = sorted(
            zip(ids, metas),
            key=lambda x: (x[1] or {}).get("zarchiwizowany_o", ""),
            reverse=True,
        )
        return kandydaci[0][0] if kandydaci else None

    # ----- Statystyki, iteracja, czyszczenie -----

    def count(self) -> int:
        """Liczba wpisów w pamięci głównej."""
        try:
            return self._main.count()
        except Exception:
            return 0

    def archive_count(self) -> int:
        try:
            return self._archive.count()
        except Exception:
            return 0

    def stats_by_category(self) -> Dict[str, int]:
        """Liczba wpisów per kategoria."""
        liczniki: Dict[str, int] = {}
        try:
            data = self._main.get()
            for m in data.get("metadatas") or []:
                kat = (m or {}).get("kategoria", "inne") or "inne"
                liczniki[kat] = liczniki.get(kat, 0) + 1
        except Exception as e:
            log.warning("Błąd stats_by_category: %s", e)
        return liczniki

    def all_entries(self) -> List[MemoryEntry]:
        """Wszystkie wpisy z głównej kolekcji (uwaga: ładuje wszystko do pamięci)."""
        try:
            data = self._main.get()
        except Exception as e:
            log.exception("Błąd all_entries: %s", e)
            return []
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        wyniki: List[MemoryEntry] = []
        for i, wpis_id in enumerate(ids):
            wyniki.append(MemoryEntry.from_chroma(
                wpis_id, docs[i] if i < len(docs) else "",
                metas[i] if i < len(metas) else {} or {},
            ))
        return wyniki

    def wipe(self) -> None:
        """Czyści całą pamięć (główna + archiwum). Tylko do testów albo reset."""
        try:
            self._client.delete_collection(self.config.collection)
            self._client.delete_collection(self.config.archive_collection)
        except Exception as e:
            log.warning("wipe: %s", e)
        # Odtwórz kolekcje, żeby store był dalej używalny
        self._main = self._client.get_or_create_collection(
            name=self.config.collection,
            embedding_function=self._embedding_fn,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        self._archive = self._client.get_or_create_collection(
            name=self.config.archive_collection,
            embedding_function=self._embedding_fn,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )

    # ----- Helpery -----

    def _znajdz_duplikat(self, tresc: str) -> Optional[MemoryEntry]:
        wyniki = self.search(tresc, limit=1, max_distance=self.config.dedup_threshold)
        return wyniki[0] if wyniki else None

    def _do_archiwum(self, wpis: MemoryEntry, powod: str) -> str:
        """Zapisuje kopię wpisu do archiwum. Zwraca ID wpisu archiwalnego."""
        arch_id = str(uuid.uuid4())
        meta = wpis.to_chroma_metadata()
        meta.update({
            "oryginalny_id": wpis.id,
            "zarchiwizowany_o": _teraz_iso(),
            "powod": powod,
        })
        try:
            self._archive.add(ids=[arch_id], documents=[wpis.tresc], metadatas=[meta])
        except Exception as e:
            log.exception("Nie udało się zarchiwizować wpisu %s: %s", wpis.id, e)
            raise MemoryStoreError(f"Archiwizacja nie powiodła się: {e}") from e
        return arch_id


# =============================================================================
# Helpery modułu
# =============================================================================

def _teraz_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parsuj_query_result(res: Dict[str, Any]) -> List[MemoryEntry]:
    """Parsuje wynik collection.query() do listy MemoryEntry."""
    if not res:
        return []
    ids_list = res.get("ids") or [[]]
    docs_list = res.get("documents") or [[]]
    metas_list = res.get("metadatas") or [[]]
    dist_list = res.get("distances") or [[]]

    ids = ids_list[0] if ids_list else []
    docs = docs_list[0] if docs_list else []
    metas = metas_list[0] if metas_list else []
    dists = dist_list[0] if dist_list else []

    wyniki: List[MemoryEntry] = []
    for i, wpis_id in enumerate(ids):
        wyniki.append(MemoryEntry.from_chroma(
            wpis_id,
            docs[i] if i < len(docs) else "",
            metas[i] if i < len(metas) else {} or {},
            dystans=float(dists[i]) if i < len(dists) and dists[i] is not None else None,
        ))
    return wyniki
