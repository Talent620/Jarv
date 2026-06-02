"""Klient HTTP do lokalnej instancji Ollama.

Cele:
- Czytelne komunikaty błędów (timeout vs brak Ollama vs brak modelu).
- Retry tylko przy błędach przejściowych (sieć), nie przy 4xx/5xx.
- Brak zewnętrznych zależności poza `requests`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from core.config import LLMConfig
from core.logging_setup import get_logger

log = get_logger(__name__)


class OllamaError(Exception):
    """Bazowy wyjątek dla problemów z Ollama."""


class OllamaUnavailable(OllamaError):
    """Ollama nie odpowiada pod skonfigurowanym adresem."""


class OllamaModelMissing(OllamaError):
    """Skonfigurowany model nie jest pobrany lokalnie."""


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class OllamaClient:
    """Cienki klient HTTP nad API Ollama."""

    def __init__(self, config: LLMConfig, session: Optional[requests.Session] = None):
        self.config = config
        self._host = config.host.rstrip("/")
        self._session = session or requests.Session()

    # ----- Status -----

    def is_running(self, timeout: float = 2.0) -> bool:
        """Szybki ping — czy Ollama w ogóle działa."""
        try:
            r = self._session.get(f"{self._host}/api/tags", timeout=timeout)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[str]:
        """Lista zainstalowanych modeli."""
        try:
            r = self._session.get(f"{self._host}/api/tags", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except requests.RequestException as e:
            log.warning("Nie udało się pobrać listy modeli z Ollama: %s", e)
            return []

    def has_model(self, model: Optional[str] = None) -> bool:
        """Sprawdza, czy model jest dostępny lokalnie (akceptuje warianty z/bez tagu)."""
        target = (model or self.config.model).lower()
        models = [m.lower() for m in self.list_models()]
        if not models:
            return False
        if target in models:
            return True
        # Ollama lubi przyklejać ':latest'
        if any(m.split(":")[0] == target.split(":")[0] for m in models):
            return True
        return False

    # ----- Generacja -----

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Wieloturowa rozmowa. Zwraca treść odpowiedzi modelu.

        Rzuca OllamaError przy trwałych problemach. Próbuje 2x przy błędach sieciowych.
        """
        if not messages:
            raise ValueError("Lista messages nie może być pusta")

        payload = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.config.temperature,
            },
        }
        data = self._post_with_retry("/api/chat", payload, timeout=timeout)
        msg = (data or {}).get("message") or {}
        return (msg.get("content") or "").strip()

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Pojedyncze wywołanie (bez historii). Tańsze dla klasyfikacji/JSON."""
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else 0.2,
            },
        }
        data = self._post_with_retry("/api/generate", payload, timeout=timeout)
        return (data or {}).get("response", "").strip()

    # ----- Wewnętrzne -----

    def _post_with_retry(
        self,
        endpoint: str,
        payload: Dict,
        timeout: Optional[float] = None,
        max_retries: int = 1,
    ) -> Dict:
        """POST z prostym backoffem przy błędach sieciowych."""
        url = f"{self._host}{endpoint}"
        czas = timeout if timeout is not None else self.config.timeout
        ostatni_blad: Optional[Exception] = None

        for proba in range(max_retries + 1):
            try:
                r = self._session.post(url, json=payload, timeout=czas)
            except requests.Timeout as e:
                ostatni_blad = e
                log.warning("Timeout Ollama (próba %d/%d)", proba + 1, max_retries + 1)
                if proba < max_retries:
                    time.sleep(0.5 * (proba + 1))
                    continue
                raise OllamaError(f"Ollama nie odpowiedziała w czasie {czas}s") from e
            except requests.ConnectionError as e:
                # Ollama prawdopodobnie nie działa — nie ma sensu retry
                raise OllamaUnavailable(
                    f"Brak połączenia z Ollama pod {self._host}. Uruchom 'ollama serve'."
                ) from e
            except requests.RequestException as e:
                ostatni_blad = e
                log.warning("Błąd zapytania do Ollama (próba %d): %s", proba + 1, e)
                if proba < max_retries:
                    time.sleep(0.5 * (proba + 1))
                    continue
                raise OllamaError(f"Błąd zapytania do Ollama: {e}") from e

            if r.status_code == 404:
                # Najczęściej: brak modelu
                raise OllamaModelMissing(
                    f"Model '{self.config.model}' nie jest dostępny. "
                    f"Pobierz: ollama pull {self.config.model}"
                )
            if not r.ok:
                tekst = (r.text or "")[:200]
                raise OllamaError(f"Ollama HTTP {r.status_code}: {tekst}")

            try:
                return r.json()
            except ValueError as e:
                raise OllamaError(f"Niepoprawny JSON od Ollama: {e}") from e

        # Teoretycznie nieosiągalne
        raise OllamaError(f"Nieoczekiwany błąd Ollama: {ostatni_blad}")
