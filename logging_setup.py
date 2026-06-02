"""Konfiguracja logowania."""
from __future__ import annotations
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Any

_INITIALIZED = False
_ROOT = "jarvis"


def setup_logging(config: Any, debug: bool = False, log_path: Optional[Path] = None) -> logging.Logger:
    global _INITIALIZED
    logger = logging.getLogger(_ROOT)
    level_str = "DEBUG" if debug else getattr(config, "level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    logger.setLevel(level)

    if _INITIALIZED:
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_path is None and config is not None:
        try:
            raw = getattr(config, "file", "~/.jarvis/jarvis.log")
            log_path = Path(raw).expanduser()
        except Exception:
            pass

    if log_path:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            max_mb = getattr(config, "max_mb", 5)
            backups = getattr(config, "backups", 3)
            fh = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=max_mb * 1024 * 1024,
                backupCount=backups, encoding="utf-8"
            )
            fh.setLevel(level)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError as e:
            sys.stderr.write(f"[!] Nie mozna otworzyc logu: {e}\n")

    for noisy in ("chromadb", "sentence_transformers", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _INITIALIZED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    for prefix in ("jarvis_app.", "core.", "ai.", "memory.", "voice.", "actions.", "integrations.", "web."):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return logging.getLogger(f"{_ROOT}.{name}")
