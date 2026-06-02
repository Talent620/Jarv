"""Home Assistant Core (Premium) - Integracja z HA API"""
import os
import requests
from typing import Dict, Any, Optional

from core.logging_setup import get_logger
log = get_logger(__name__)

class HACore:
    def __init__(self, config=None):
        self.config = config or {}
        # Zwykle zalezności pochodzą z self.config (np dict z config.toml)
        # Oczekujemy, że klucz będzie przekazywany ze zmiennych środowiskowych lub conf
        self.url = self.config.get("url", os.environ.get("HA_URL", "http://homeassistant.local:8123"))
        self.token = self.config.get("token", os.environ.get("HA_TOKEN", ""))
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
    def _call_service(self, domain: str, service: str, entity_id: str) -> bool:
        if not self.token:
            log.warning("Brak tokena HA. Operacja anulowana.")
            return False
            
        endpoint = f"{self.url}/api/services/{domain}/{service}"
        payload = {"entity_id": entity_id}
        try:
            resp = requests.post(endpoint, headers=self.headers, json=payload, timeout=5)
            resp.raise_for_status()
            log.info(f"HA sukces: {domain}.{service} na {entity_id}")
            return True
        except Exception as e:
            log.error(f"Błąd komunikacji z HA: {e}")
            return False

    def toggle(self, entity_id: str) -> bool:
        """Przełącza stan wybranej encji."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return self._call_service(domain, "toggle", entity_id)
        
    def turn_on(self, entity_id: str) -> bool:
        """Włącza encję."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return self._call_service(domain, "turn_on", entity_id)

    def turn_off(self, entity_id: str) -> bool:
        """Wyłącza encję."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return self._call_service(domain, "turn_off", entity_id)
        
    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Pobiera aktualny stan encji."""
        if not self.token:
            return None
        endpoint = f"{self.url}/api/states/{entity_id}"
        try:
            resp = requests.get(endpoint, headers=self.headers, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error(f"Błąd pobierania stanu {entity_id} z HA: {e}")
            return None
