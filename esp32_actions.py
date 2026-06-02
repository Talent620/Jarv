"""ESP32 actions — plugin."""
from core.registry import registry
from actions.base import BaseAction, ActionResult


@registry.register("esp32_on", "esp32_off", "esp32_set", "esp32_status", "esp32_list")
class ESP32Action(BaseAction):

    def can_handle(self, intent, ctx) -> bool:
        return ctx.has("esp32") and ctx.esp32.cfg.enabled

    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("esp32"):
            return ActionResult(
                "Moduł ESP32 nie jest skonfigurowany.\n"
                "Ustaw [esp32] enabled=true w config.toml i podaj host ESP32.",
                success=False
            )
        text = ctx.esp32.handle_intent(intent)
        return ActionResult(text)
