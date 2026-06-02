"""Deep Research - agregator wiedzy za pomoca search api"""
from typing import List, Dict

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

from core.logging_setup import get_logger
log = get_logger(__name__)

class DeepResearch:
    def __init__(self, config=None):
        self.config = config or {}
        self.max_results = self.config.get("max_sources", 5)
        
    def research(self, topic: str) -> str:
        log.info(f"Deep Research analizuje: {topic} (max_results={self.max_results})")
        if not DDGS:
            return f"Błąd: moduł duckduckgo-search nie jest zainstalowany. Zestawienie dla {topic} niemożliwe."
            
        try:
            results = []
            with DDGS() as ddgs:
                found = list(ddgs.text(topic, max_results=self.max_results))
                for item in found:
                    results.append(f"[{item.get('title', 'Brak tytulu')}]({item.get('href', '#')})\n{item.get('body', '')}\n")
            
            if not results:
                return f"Nie znaleziono wyników dla tematu: {topic}"
                
            report = f"## Raport Deep Research dla: {topic}\n\n"
            report += "\n---\n".join(results)
            return report
        except Exception as e:
            log.error(f"Błąd Deep Research: {e}")
            return f"Wystąpił błąd podczas agregacji wiedzy: {e}"
