"""Web Agent Actions"""
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("web_search", re.compile(r"^\s*wyszukaj\s+w\s+internecie\s+(.+)$", re.I))

@registry.register("web_search")
class WebSearchAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("web"):
            return ActionResult("Brak agenta webowego.", success=False)
        m = re.match(r"^\s*wyszukaj\s+w\s+internecie\s+(.+)$", intent.surowy_tekst, re.I)
        q = m.group(1).strip() if m else ""
        res = ctx.web.fetch_page(f"https://search.com?q={q}")
        return ActionResult(f"Znalazłem internetowe wyniki dla: {q}")
