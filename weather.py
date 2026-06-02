"""Weather integration — wttr.in (offline-friendly)."""
from __future__ import annotations
from core.logging_setup import get_logger
from core.registry import registry
from actions.base import BaseAction, ActionResult

log = get_logger(__name__)


class WeatherTool:
    def __init__(self, city: str = "Warsaw"):
        self.city = city

    def get_now(self) -> str:
        try:
            import requests
            r = requests.get(
                f"https://wttr.in/{self.city}?format=3",
                timeout=5, headers={"User-Agent": "Jarvis/2.0"}
            )
            if r.ok:
                return r.text.strip()
            return f"Błąd pogody: HTTP {r.status_code}"
        except Exception as e:
            return f"Brak danych pogodowych: {e}"

    def get_week(self) -> str:
        try:
            import requests
            r = requests.get(
                f"https://wttr.in/{self.city}?format=2",
                timeout=5, headers={"User-Agent": "Jarvis/2.0"}
            )
            if r.ok:
                return r.text.strip()
            return f"Błąd pogody: HTTP {r.status_code}"
        except Exception as e:
            return f"Brak prognozy: {e}"


@registry.register("weather")
class WeatherAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        city = getattr(ctx.config, "weather", None)
        city = getattr(city, "city", "Warsaw") if city else "Warsaw"
        tool = WeatherTool(city)
        return ActionResult(tool.get_now())


@registry.register("weather_week")
class WeatherWeekAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        city = getattr(ctx.config, "weather", None)
        city = getattr(city, "city", "Warsaw") if city else "Warsaw"
        tool = WeatherTool(city)
        return ActionResult(tool.get_week())
