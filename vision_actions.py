"""Vision Agent Actions"""
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("vision_analyze", re.compile(r"^\s*co\s+widzisz\s*$", re.I))

@registry.register("vision_analyze")
class VisionAnalyzeAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if ctx.has("vision"):
            res = ctx.vision.analyze_image("/tmp/screen.png")
            return ActionResult(f"Widzę: {res}")
        return ActionResult("Moduł wizji nie jest dostępny.", success=False)
