"""HA Actions"""
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("ha_toggle", re.compile(r"^\s*(w[łl][ąa]cz|wy[łl][ąa]cz)\s+[śs]wiat[łl]o\s*$", re.I))

@registry.register("ha_toggle")
class HAToggleAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("ha"):
            return ActionResult("HA niedostępny.", success=False)
        
        on = "wł" in intent.surowy_tekst.lower()
        if on:
            ctx.ha.turn_on("light.main")
            return ActionResult("Zrobiłem to.")
        else:
            ctx.ha.turn_off("light.main")
            return ActionResult("Wyłączone.")
