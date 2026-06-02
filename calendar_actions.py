"""Akcje kalendarza — plugin."""
from __future__ import annotations

import re

from actions.base import ActionResult, BaseAction
from actions.calendar_core import parse_event_datetime
from core.registry import registry


@registry.register("calendar_add")
class CalendarAddAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("calendar"):
            return ActionResult("Kalendarz niedostępny.", success=False)

        tekst = intent.surowy_tekst
        when_dt, title = parse_event_datetime(tekst)

        if when_dt is None:
            return ActionResult(
                "Nie zrozumiałem daty. Przykład: 'dodaj do kalendarza dentys­ta jutro o 10:30'.",
                success=False,
            )
        if not title:
            title = "Wydarzenie"

        ev = ctx.calendar.add(title=title, start_dt=when_dt)
        return ActionResult(
            f"📅 Dodano: '{ev.title}' — {ev.format_start()}.",
            data={"id": ev.id, "title": ev.title, "start": ev.start_dt},
        )


@registry.register("calendar_today")
class CalendarTodayAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("calendar"):
            return ActionResult("Kalendarz niedostępny.", success=False)
        events = ctx.calendar.today()
        return ActionResult(ctx.calendar.format_list(events, "Dzisiaj w kalendarzu"))


@registry.register("calendar_list")
class CalendarListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("calendar"):
            return ActionResult("Kalendarz niedostępny.", success=False)
        events = ctx.calendar.upcoming(days=14)
        return ActionResult(ctx.calendar.format_list(events, "Nadchodzące wydarzenia (14 dni)"))


@registry.register("calendar_next")
class CalendarNextAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("calendar"):
            return ActionResult("Kalendarz niedostępny.", success=False)
        ev = ctx.calendar.next()
        if ev:
            return ActionResult(f"Następne: {ev.format_start()} — {ev.title}.")
        return ActionResult("Brak nadchodzących wydarzeń.")


@registry.register("calendar_remove")
class CalendarRemoveAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("calendar"):
            return ActionResult("Kalendarz niedostępny.", success=False)
        m = re.search(r"\b(\d+)\b", intent.surowy_tekst)
        if not m:
            return ActionResult("Podaj numer lub ID wydarzenia do usunięcia.", success=False)
        eid = int(m.group(1))
        ok = ctx.calendar.remove(eid)
        return ActionResult(
            f"Wydarzenie #{eid} usunięte." if ok else f"Nie znalazłem wydarzenia #{eid}.",
            success=ok,
        )
