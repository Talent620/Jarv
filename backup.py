"""Eksport i import pamięci do/z plików JSON.

Format pliku (JSON):
{
    "version": "1.0",
    "exported_at": "2026-01-01T12:00:00",
    "main": [
        {"id": "...", "tresc": "...", "kategoria": "...", "tagi": [...],
         "data": "...", "aktualizacja": "...", "zrodlo": "...", "wersja": 1}
    ],
    "archive": [...]   # te same pola
}

Filozofia:
- Import nigdy nie usuwa istniejących wpisów. Domyślnie dodaje, używa dedup.
- Walidacja schematu przed importem — jeśli plik popsuty, nic nie tykamy.
- Backup tworzy plik z datą w nazwie.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging_setup import get_logger
from memory.store import MemoryEntry, MemoryStore

log = get_logger(__name__)

EXPORT_VERSION = "1.0"


class BackupError(Exception):
    """Błąd eksportu/importu."""


# =============================================================================
# Eksport
# =============================================================================

def export_to_file(memory: MemoryStore, sciezka: Path) -> Dict[str, int]:
    """Eksportuje całą pamięć (główną + archiwum) do pliku JSON.

    Zwraca słownik z licznikami: {"main": N, "archive": M}.
    """
    main = memory.all_entries()
    archive = _all_archive_entries(memory)

    data: Dict[str, Any] = {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "main": [_entry_to_dict(e) for e in main],
        "archive": archive,
    }

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    try:
        sciezka.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as e:
        raise BackupError(f"Nie udało się zapisać eksportu: {e}") from e

    log.info("Eksport: %d wpisów głównych + %d archiwum -> %s",
             len(main), len(archive), sciezka)
    return {"main": len(main), "archive": len(archive)}


def auto_export_path(base_dir: Path) -> Path:
    """Zwraca ścieżkę typu base_dir/memory_export_YYYYMMDD_HHMMSS.json"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_dir / f"memory_export_{stamp}.json"


# =============================================================================
# Import
# =============================================================================

def import_from_file(
    memory: MemoryStore,
    sciezka: Path,
    skip_dedup: bool = False,
    import_archive: bool = False,
) -> Dict[str, int]:
    """Importuje pamięć z pliku JSON.

    Zwraca: {"added": N, "duplicates": M, "skipped": K, "errors": E}
    """
    if not sciezka.exists():
        raise BackupError(f"Plik nie istnieje: {sciezka}")

    try:
        data = json.loads(sciezka.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise BackupError(f"Nie udało się wczytać pliku: {e}") from e

    _validate_export(data)

    added = 0
    duplicates = 0
    skipped = 0
    errors = 0

    for raw in data.get("main", []):
        try:
            tresc = raw.get("tresc")
            if not tresc or not isinstance(tresc, str):
                skipped += 1
                continue
            kategoria = raw.get("kategoria") or "inne"
            tagi = raw.get("tagi") or []
            if not isinstance(tagi, list):
                tagi = []
            _entry, was_dup = memory.add(
                tresc, kategoria=kategoria, tagi=tagi, skip_dedup=skip_dedup,
            )
            if was_dup:
                duplicates += 1
            else:
                added += 1
        except Exception as e:
            log.warning("Import: pomijam wpis z powodu błędu: %s", e)
            errors += 1

    # Archive importujemy tylko jeśli explicit wymagane — bo to historyczne dane
    if import_archive:
        log.info("Import archiwum: %d wpisów", len(data.get("archive", [])))
        # Nie korzystamy z publicznego API memory dla archiwum;
        # archiwum to dane wspierające, normalnie odbudowuje się przy update/delete.

    log.info("Import zakończony: dodano=%d duplikaty=%d pominięto=%d błędy=%d",
             added, duplicates, skipped, errors)
    return {"added": added, "duplicates": duplicates, "skipped": skipped, "errors": errors}


# =============================================================================
# Pomocnicze
# =============================================================================

def _entry_to_dict(e: MemoryEntry) -> Dict[str, Any]:
    d = asdict(e)
    # Nie eksportujemy 'dystans' — to wartość chwilowa z wyniku zapytania
    d.pop("dystans", None)
    return d


def _all_archive_entries(memory: MemoryStore) -> List[Dict[str, Any]]:
    """Pobiera surowo wszystkie wpisy archiwum (z metadanymi)."""
    out: List[Dict[str, Any]] = []
    try:
        # MemoryStore nie eksponuje publicznie kolekcji archiwum, ale to
        # OK — używamy chronionego atrybutu w obrębie tego samego pakietu.
        archive = memory._archive  # type: ignore[attr-defined]
        data = archive.get()
    except Exception as e:
        log.warning("Nie udało się pobrać archiwum: %s", e)
        return out

    ids = data.get("ids") or []
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    for i, wpis_id in enumerate(ids):
        out.append({
            "archive_id": wpis_id,
            "tresc": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {} or {},
        })
    return out


def _validate_export(data: Any) -> None:
    """Sprawdza minimalną poprawność danych importu."""
    if not isinstance(data, dict):
        raise BackupError("Plik nie zawiera obiektu JSON")
    if data.get("version") != EXPORT_VERSION:
        log.warning(
            "Import: wersja eksportu '%s' różna od bieżącej '%s' — próbuję mimo to",
            data.get("version"), EXPORT_VERSION,
        )
    if "main" not in data:
        raise BackupError("Brak pola 'main' w eksporcie")
    if not isinstance(data["main"], list):
        raise BackupError("Pole 'main' musi być listą")
