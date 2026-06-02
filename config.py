"""Konfiguracja Jarvisa. Ładowanie z TOML, walidacja, ścieżki domyślne.

Filozofia:
- Brakujący plik konfiguracyjny = używamy defaultów (bez błędu).
- Brakująca sekcja w istniejącym pliku = defaulty tylko dla tej sekcji.
- Zła wartość = wyjątek z czytelnym komunikatem.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# tomllib jest częścią Pythona 3.11+. Dla starszych mamy tomli z requirements.
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found, no-redef]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Brak biblioteki TOML. Zainstaluj 'tomli' albo użyj Pythona 3.11+."
        ) from e


# Domyślna ścieżka do configu — można nadpisać przez --config albo zmienną środowiskową
DEFAULT_CONFIG_PATH = Path.home() / ".jarvis" / "config.toml"


@dataclass
class LLMConfig:
    """Konfiguracja klienta Ollama."""
    host: str = "http://localhost:11434"
    model: str = "llama3.1"
    temperature: float = 0.5
    timeout: float = 120.0


@dataclass
class MemoryConfig:
    """Konfiguracja pamięci wektorowej."""
    dir: str = "~/.jarvis/memory_db"
    collection: str = "jarvis_pamiec"
    archive_collection: str = "jarvis_archive"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    dedup_threshold: float = 0.08
    search_limit: int = 5
    update_threshold: float = 0.35


@dataclass
class SpeechConfig:
    """Konfiguracja rozpoznawania mowy."""
    whisper_model: str = "small"
    language: str = "pl"
    sample_rate: int = 16000
    record_max_seconds: float = 12.0
    silence_seconds: float = 1.5
    silence_threshold: Union[float, str] = "auto"  # "auto" lub float
    calibration_seconds: float = 1.5
    compute_type: str = "int8"


@dataclass
class TTSConfig:
    """Konfiguracja syntezy mowy."""
    rate: int = 175
    volume: float = 1.0
    prefer_voice_contains: List[str] = field(
        default_factory=lambda: ["polish", "polski", "pl-pl", "pl_pl"]
    )
    use_coqui: bool = False
    coqui_model: str = "tts_models/pl/mai_female/vits"


@dataclass
class UIConfig:
    """Konfiguracja interfejsu użytkownika."""
    user_name: str = "Artur"
    default_mode: str = "voice"  # "voice" albo "text"
    history_size: int = 20
    confirm_destructive: bool = True


@dataclass
class LearningConfig:
    """Konfiguracja silnika uczenia się."""
    db_path: str = "~/.jarvis/learning.db"
    enable_patterns: bool = True
    patterns_min_uses: int = 3
    history_keep: int = 500


@dataclass
class LoggingConfig:
    """Konfiguracja logowania."""
    file: str = "~/.jarvis/jarvis.log"
    level: str = "INFO"
    max_mb: int = 5
    backups: int = 3



@dataclass
class WakeWordConfig:
    enabled: bool = False
    model: str = "hey_jarvis"
    threshold: float = 0.5
    device: Optional[int] = None
    chunk_ms: int = 80
    sample_rate: int = 16000


@dataclass
class ESP32DeviceRaw:
    name: str = "device"
    pin: int = 2
    type: str = "relay"
    aliases: List[str] = field(default_factory=list)
    inverted: bool = False


@dataclass
class ESP32Config:
    enabled: bool = False
    host: str = "http://192.168.1.100"
    timeout: float = 3.0
    max_volts: float = 12.0
    mqtt_enabled: bool = False
    mqtt_broker: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_cmd: str = "jarvis/command"
    mqtt_topic_status: str = "jarvis/status"
    devices: List[dict] = field(default_factory=list)


@dataclass
class WeatherConfig:
    enabled: bool = True
    city: str = "Warsaw"


@dataclass
class InventoryConfig2:
    enabled: bool = True
    db_path: str = "~/.jarvis/inventory.db"
    auto_fetch: bool = False


@dataclass
class TelegramConfig:
    enabled: bool = False
    token: str = ""
    chat_id: int = 0


@dataclass
class SchedulerConfig:
    """Konfiguracja przypomnień APScheduler."""
    enabled: bool = True
    db_path: str = "~/.jarvis/scheduler.db"


@dataclass
class CalendarConfig:
    """Konfiguracja kalendarza."""
    enabled: bool = True
    db_path: str = "~/.jarvis/calendar.db"


@dataclass
class ResearchConfig:
    """Konfiguracja codziennego researchu."""
    enabled: bool = True
    db_path: str = "~/.jarvis/research.db"
    default_hour: int = 8
    default_minute: int = 0
    max_results: int = 5


@dataclass
class HistoryConfig:
    """Konfiguracja historii rozmów."""
    enabled: bool = True
    db_path: str = "~/.jarvis/history.db"
    max_entries: int = 1000


@dataclass
class Config:
    """Główna konfiguracja aplikacji. Wszystkie sekcje są opcjonalne."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    esp32: ESP32Config = field(default_factory=ESP32Config)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    inventory: InventoryConfig2 = field(default_factory=InventoryConfig2)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

    # V3 — nowe moduły
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)

    # Ścieżka do pliku konfiguracyjnego (jeśli został wczytany)
    config_path: Optional[Path] = None

    # ----- Loadery i walidacja -----

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Ładuje konfigurację z pliku TOML. Jeśli brak — używa defaultów."""
        path = path or _resolve_config_path()
        if path is None or not path.exists():
            return cls(config_path=None)

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(
                f"Nie udało się wczytać pliku konfiguracyjnego '{path}': {e}"
            ) from e

        return cls._from_dict(data, path)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any], path: Optional[Path] = None) -> "Config":
        """Buduje Config ze słownika (np. z TOMLa)."""
        sekcje = {f.name: f for f in fields(cls) if f.name != "config_path"}
        kwargs: Dict[str, Any] = {}
        for nazwa, pole in sekcje.items():
            klasa = pole.default_factory()  # type: ignore[misc]
            podsekcja = data.get(nazwa, {})
            if not isinstance(podsekcja, dict):
                raise ConfigError(
                    f"Sekcja [{nazwa}] musi być tablicą, a jest {type(podsekcja).__name__}"
                )
            kwargs[nazwa] = _build_section(type(klasa), podsekcja, nazwa)
        kwargs["config_path"] = path
        cfg = cls(**kwargs)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Sprawdza wartości po wczytaniu. Rzuca ConfigError przy błędach."""
        if self.llm.temperature < 0 or self.llm.temperature > 2:
            raise ConfigError("llm.temperature musi być w przedziale [0, 2]")
        if self.llm.timeout <= 0:
            raise ConfigError("llm.timeout musi być dodatni")
        if not (0 <= self.memory.dedup_threshold < self.memory.update_threshold < 2):
            raise ConfigError(
                "memory: oczekiwane 0 <= dedup_threshold < update_threshold < 2"
            )
        if self.memory.search_limit < 1:
            raise ConfigError("memory.search_limit musi być >= 1")
        if self.speech.sample_rate not in (8000, 16000, 22050, 44100, 48000):
            raise ConfigError("speech.sample_rate musi być standardową wartością")
        if isinstance(self.speech.silence_threshold, str) and self.speech.silence_threshold != "auto":
            raise ConfigError("speech.silence_threshold musi być liczbą albo 'auto'")
        if self.ui.default_mode not in ("voice", "text"):
            raise ConfigError("ui.default_mode musi być 'voice' albo 'text'")
        if self.logging.level.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ConfigError(f"logging.level: nieznany poziom '{self.logging.level}'")

    # ----- Helpery ścieżek (rozwijają ~) -----

    def expanded(self, path: str) -> Path:
        """Rozwija ~ i zmienne środowiskowe w ścieżce."""
        return Path(os.path.expandvars(os.path.expanduser(path))).resolve()

    def memory_dir(self) -> Path:
        return self.expanded(self.memory.dir)

    def learning_db(self) -> Path:
        return self.expanded(self.learning.db_path)

    def log_file(self) -> Path:
        return self.expanded(self.logging.file)


class ConfigError(Exception):
    """Błąd konfiguracji — z czytelnym komunikatem dla użytkownika."""


def _resolve_config_path() -> Optional[Path]:
    """Szuka pliku konfiguracyjnego w standardowych lokalizacjach."""
    env = os.environ.get("JARVIS_CONFIG")
    if env:
        return Path(env).expanduser()
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    # Fallback — przykładowy obok skryptu
    here = Path(__file__).resolve().parent.parent
    przyklad = here / "config.example.toml"
    if przyklad.exists():
        return przyklad
    return None


def _build_section(klasa: type, dane: Dict[str, Any], nazwa_sekcji: str) -> Any:
    """Buduje obiekt dataclass z dictu, walidując znane pola."""
    if not is_dataclass(klasa):
        raise ConfigError(f"Niewłaściwa klasa sekcji: {klasa}")
    znane = {f.name for f in fields(klasa)}
    nieznane = set(dane.keys()) - znane
    if nieznane:
        raise ConfigError(
            f"Sekcja [{nazwa_sekcji}] zawiera nieznane pola: {sorted(nieznane)}"
        )
    return klasa(**dane)
