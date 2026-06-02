"""Project Memory Actions — integracja komend NLP dla projektów."""

from __future__ import annotations
import re
from core.registry import registry
from actions.base import BaseAction, ActionResult
from ai.intent import IntentDetector

IntentDetector.register_pattern("project_create", re.compile(r"^\s*utw[óo]rz\s+projekt\s+(.+)$", re.I))
IntentDetector.register_pattern("project_set", re.compile(r"^\s*ustaw\s+projekt\s+(.+)$", re.I))
IntentDetector.register_pattern("project_note", re.compile(r"^\s*zapisz\s+w\s+projekcie\s+(.+)$", re.I))
IntentDetector.register_pattern("project_list", re.compile(r"^\s*(poka[żz]\s+|lista\s+)?projekt[oó]w\s*$", re.I))
IntentDetector.register_pattern("project_task", re.compile(r"^\s*zadanie\s+w\s+projekcie\s+(.+)$", re.I))

@registry.register("project_create")
class ProjectCreateAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        # np. utwórz projekt Alpha opis ...
        m = re.match(r"^\s*utw[óo]rz\s+projekt\s+(.+)$", intent.surowy_tekst, re.I)
        if not m:
            return ActionResult("Jak nazywa się projekt?", success=False)
            
        parts = m.group(1).split(maxsplit=1)
        name = parts[0]
        desc = parts[1] if len(parts) > 1 else "Brak opisu"
        
        project_id = ctx.project_memory.create_project(name, desc)
        if not project_id:
            return ActionResult(f"Projekt '{name}' już istnieje.", success=False)
            
        ctx.project_memory.set_active_project(name)
        return ActionResult(f"Utworzono projekt '{name}' i ustawiono go jako aktywny.")

@registry.register("project_set")
class ProjectSetAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        m = re.match(r"^\s*ustaw\s+projekt\s+(.+)$", intent.surowy_tekst, re.I)
        name = m.group(1).strip() if m else ""
        if not name:
            return ActionResult("Który projekt mam aktywować?", success=False)
            
        if ctx.project_memory.set_active_project(name):
            return ActionResult(f"Projekt '{name}' jest teraz aktywny.")
        return ActionResult(f"Nie znaleziono projektu o nazwie '{name}'.", success=False)

@registry.register("project_note")
class ProjectNoteAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.project_memory.active_project_id:
            return ActionResult("Żaden projekt nie jest aktywny. Użyj: ustaw projekt X", success=False)
            
        m = re.match(r"^\s*zapisz\s+w\s+projekcie\s+(.+)$", intent.surowy_tekst, re.I)
        tresc = m.group(1).strip() if m else ""
        if not tresc:
            return ActionResult("Brak treści notatki.", success=False)
            
        ctx.project_memory.add_note(tresc)
        return ActionResult("Zapisano notatkę w aktywnym projekcie.")
        
@registry.register("project_task")
class ProjectTaskAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.project_memory.active_project_id:
            return ActionResult("Żaden projekt nie jest aktywny. Użyj: ustaw projekt X", success=False)
            
        m = re.match(r"^\s*zadanie\s+w\s+projekcie\s+(.+)$", intent.surowy_tekst, re.I)
        tresc = m.group(1).strip() if m else ""
        if not tresc:
            return ActionResult("Brak treści zadania.", success=False)
            
        ctx.project_memory.add_task(tresc)
        return ActionResult("Zapisano zadanie w aktywnym projekcie.")

@registry.register("project_list")
class ProjectListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        projects = ctx.project_memory.list_projects()
        if not projects:
            return ActionResult("Brak projektów.")
            
        lines = ["Lista projektów:"]
        for p in projects:
            aktywny = " (Aktywny)" if p.id == ctx.project_memory.active_project_id else ""
            lines.append(f" - {p.name}: {p.description}{aktywny}")
            
        return ActionResult("\n".join(lines))
