"""Akcje przypomnień — APScheduler plugin."""
from __future__ import annotations

import re

from actions.base import ActionResult, BaseAction
from actions.scheduler_core import parse_reminder
from core.registry import registry


@registry.register("reminder_set")
class ReminderSetAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("scheduler"):
            return ActionResult("Scheduler niedostępny.", success=False)

        tekst = intent.surowy_tekst
        try:
            when_dt, label, recurrence = parse_reminder(tekst)
        except Exception as e:
            return ActionResult(f"Nie zrozumiałem kiedy. Przykład: 'przypomnij jutro o 15:30 leki'. ({e})",
                                success=False)

        r = ctx.scheduler.add(label=label, when_dt=when_dt, recurrence=recurrence)

        rec_info = {"daily": " (codziennie)", "weekly": " (co tydzień)"}.get(recurrence, "")
        return ActionResult(
            f"✅ Przypomnienie '{r.label}' ustawione na {r.format_when()}{rec_info}.",
            data={"id": r.id, "label": r.label, "when": r.when},
        )


@registry.register("reminder_list")
class ReminderListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("scheduler"):
            return ActionResult("Scheduler niedostępny.", success=False)
        return ActionResult(ctx.scheduler.format_list())


@registry.register("reminder_cancel")
class ReminderCancelAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("scheduler"):
            return ActionResult("Scheduler niedostępny.", success=False)

        query = intent.argument or intent.tresc
        # Spróbuj wyłuskać numer z listy: "anuluj przypomnienie 2"
        m = re.search(r"\b(\d+)\b", query)
        if m:
            idx = int(m.group(1))
            active = ctx.scheduler.list_active()
            if 1 <= idx <= len(active):
                query = active[idx - 1].id

        ok = ctx.scheduler.cancel(query)
        if ok:
            return ActionResult(f"🗑️ Przypomnienie '{query}' anulowane.")
        return ActionResult(f"Nie znalazłem przypomnienia: '{query}'.", success=False)
