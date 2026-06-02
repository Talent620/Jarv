"""OCR Actions"""
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("ocr_scan", re.compile(r"^\s*skanuj\s+ekran\s*$", re.I))

@registry.register("ocr_scan")
class OcrScanAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("ocr"):
            return ActionResult("Moduł OCR nie jest aktywny.", success=False)
        tresc = ctx.ocr.scan_screenshot()
        return ActionResult(f"Rozpoznano tekst: {tresc}")
