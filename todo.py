"""TODO actions — plugin."""
from core.registry import registry
from actions.base import BaseAction, ActionResult


@registry.register("todo_add")
class TodoAddAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("todo_tool"):
            return ActionResult("Lista zadań niedostępna.", success=False)
        text = intent.tresc.strip()
        if not text:
            return ActionResult("Co mam dodać do listy?", success=False)
        priority = int(intent.argument or "2")
        item = ctx.todo_tool.add(text, priority=priority)
        icons = {3:"🔴",2:"🟡",1:"⚪"}
        return ActionResult(f"Dodano {icons.get(priority,'⚪')} '{text}' do listy.", data={"id": item.id})


@registry.register("todo_list")
class TodoListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("todo_tool"):
            return ActionResult("Lista zadań niedostępna.", success=False)
        return ActionResult(ctx.todo_tool.format_list())


@registry.register("todo_done")
class TodoDoneAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("todo_tool"):
            return ActionResult("Lista zadań niedostępna.", success=False)
        try:
            item_id = int(intent.argument)
        except (ValueError, TypeError):
            return ActionResult("Podaj numer zadania.", success=False)
        ok = ctx.todo_tool.done(item_id)
        return ActionResult(f"✅ Zadanie #{item_id} ukończone." if ok else f"Nie znalazłem zadania #{item_id}.")


@registry.register("todo_clear")
class TodoClearAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("todo_tool"):
            return ActionResult("Lista zadań niedostępna.", success=False)
        n = ctx.todo_tool.clear_done()
        return ActionResult(f"Usunąłem {n} ukończonych zadań.")
