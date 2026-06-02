"""Windows Agent Actions"""
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("win_open", re.compile(r"^\s*otw[óo]rz\s+(.+)$", re.I))
IntentDetector.register_pattern("win_close", re.compile(r"^\s*zamknij\s+(.+)$", re.I))

@registry.register("win_open")
class WinOpenAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        m = re.match(r"^\s*otw[óo]rz\s+(.+)$", intent.surowy_tekst, re.I)
        app = m.group(1).strip() if m else ""
        if ctx.has("windows") and ctx.windows.launch_app(app):
            return ActionResult(f"Otwieram program: {app}")
        return ActionResult("Nie udało się otworzyć programu.", success=False)
        
@registry.register("win_close")
class WinCloseAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        m = re.match(r"^\s*zamknij\s+(.+)$", intent.surowy_tekst, re.I)
        app = m.group(1).strip() if m else ""
        if ctx.has("windows") and ctx.windows.close_app(app):
            return ActionResult(f"Zamknąłem program: {app}")
        return ActionResult("Nie udało się zamknąć programu.", success=False)
