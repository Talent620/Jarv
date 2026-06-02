"""Timer actions — plugin."""
from core.registry import registry
from core.events import E
from actions.base import BaseAction, ActionResult
from actions.timer_core import TimerManager, parse_duration_seconds, parse_timer_label


@registry.register("timer_set")
class TimerSetAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("timer_manager"):
            return ActionResult("Manager timerów niedostępny.", success=False)
        duration = parse_duration_seconds(intent.surowy_tekst)
        if not duration or duration <= 0:
            return ActionResult("Nie zrozumiałem czasu. Np. 'timer na 30 minut'.", success=False)
        label = parse_timer_label(intent.surowy_tekst)
        def _notify(title, body="", source="timer"):
            ctx.bus.emit(E.SYSTEM_ALERT, title=title, body=body, source=source)
            ctx.bus.emit(E.SPEAK, text=f"Timer {label} minął!")
        ctx.timer_manager.notify_fn = _notify
        entry = ctx.timer_manager.add(label=label, duration_s=duration)
        return ActionResult(f"Timer '{entry.label}' — {entry.format_remaining()}.",
                            data={"id": entry.id, "label": entry.label})


@registry.register("timer_list")
class TimerListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("timer_manager"):
            return ActionResult("Brak manager timerów.", success=False)
        return ActionResult(ctx.timer_manager.format_list())


@registry.register("timer_cancel")
class TimerCancelAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("timer_manager"):
            return ActionResult("Brak manager timerów.", success=False)
        label = intent.argument or intent.tresc
        ok = ctx.timer_manager.cancel(label)
        return ActionResult(f"Timer '{label}' anulowany." if ok else f"Nie znalazłem timera: '{label}'.")


@registry.register("stopwatch_start")
class SwStartAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(ctx.timer_manager.stopwatch_start() if ctx.has("timer_manager") else "Brak stopera.")

@registry.register("stopwatch_stop")
class SwStopAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(ctx.timer_manager.stopwatch_stop() if ctx.has("timer_manager") else "Brak stopera.")

@registry.register("stopwatch_reset")
class SwResetAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(ctx.timer_manager.stopwatch_reset() if ctx.has("timer_manager") else "Brak stopera.")

@registry.register("stopwatch_read")
class SwReadAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(ctx.timer_manager.stopwatch_read() if ctx.has("timer_manager") else "Brak stopera.")
