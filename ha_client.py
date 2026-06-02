"""Home Assistant Client"""
from core.logging_setup import get_logger

log = get_logger(__name__)

class HAClient:
    def turn_on(self, entity_id: str):
        log.info(f"HA: włączanie {entity_id}")
        
    def turn_off(self, entity_id: str):
        log.info(f"HA: wyłączanie {entity_id}")
