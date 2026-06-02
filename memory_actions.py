"""Memory actions — zapis/szukanie/update/delete/undo."""
from __future__ import annotations
from core.registry import registry
from actions.base import BaseAction, ActionResult


@registry.register("save")
class SaveAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        tresc = intent.tresc.strip()
        if not tresc:
            return ActionResult("Co mam zapamiętać?", success=False)
        entry, was_dup = ctx.memory.add(tresc, tagi=intent.tagi)
        if was_dup:
            return ActionResult(f"Już to wiem: \"{tresc[:80]}\".")
        ctx.learning.record_save(entry)
        return ActionResult(f"Zapamiętałem: \"{tresc[:80]}\".", data={"id": entry.id})


@registry.register("search")
class SearchAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        q = intent.tresc.strip()
        if not q:
            return ActionResult("Czego szukasz?", success=False)
        wyniki = ctx.memory.search(q, limit=3)
        if not wyniki:
            return ActionResult(f"Nic nie znalazłem o \"{q}\".")
        for w in wyniki:
            ctx.learning.record_search_hit(w.id)
        linie = []
        for i, w in enumerate(wyniki, 1):
            kat = f"[{w.kategoria}]" if w.kategoria else ""
            linie.append(f"{i}. {kat} {w.tresc[:120]}")
        return ActionResult("\n".join(linie))


@registry.register("update")
class UpdateAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not intent.stara:
            return ActionResult("Czego szukam do zmiany?", success=False)
        wyniki = ctx.memory.search(intent.stara, limit=1)
        if not wyniki:
            return ActionResult(f"Nie znalazłem wpisu o \"{intent.stara}\".", success=False)
        stary = wyniki[0]
        nowy_tekst = intent.nowa or intent.tresc
        if not nowy_tekst:
            return ActionResult("Jaka nowa treść?", success=False)
        nowy = ctx.memory.update(stary.id, nowy_tekst)
        if nowy:
            ctx.learning.record_update(stary, nowy)
            return ActionResult(f"Zaktualizowałem wpis.")
        return ActionResult("Nie udało się zaktualizować.", success=False)


@registry.register("delete")
class DeleteAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        q = intent.tresc.strip()
        if not q:
            return ActionResult("Czego szukam do usunięcia?", success=False)
        wyniki = ctx.memory.search(q, limit=1)
        if not wyniki:
            return ActionResult(f"Nie znalazłem wpisu o \"{q}\".")
        cel = wyniki[0]
        if ctx.config.ui.confirm_destructive:
            from core.confirm import Confirmer
            c = Confirmer()
            if not c.ask(f"Usunąć: \"{cel.tresc[:80]}\"?"):
                return ActionResult("Anulowano.")
        usuniety = ctx.memory.delete(cel.id)
        if usuniety:
            ctx.learning.record_delete(usuniety)
            return ActionResult(f"Usunąłem: \"{cel.tresc[:80]}\".")
        return ActionResult("Nie udało się usunąć.", success=False)


@registry.register("undo")
class UndoAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        rec = ctx.learning.last_undoable()
        if not rec:
            return ActionResult("Nie mam nic do cofnięcia.")
        if ctx.config.ui.confirm_destructive:
            from core.confirm import Confirmer
            c = Confirmer()
            if not c.ask(f"Cofnąć akcję '{rec.akcja}' na \"{(rec.nowa_tresc or rec.stara_tresc)[:60]}\"?"):
                return ActionResult("Anulowano.")
        result = ctx.learning.cofnij_ostatnia(ctx.memory)
        return ActionResult(result.opis, success=result.sukces)


@registry.register("summary")
class SummaryAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        ile = ctx.memory.count()
        arch = ctx.memory.archive_count()
        top = ctx.learning.top_kategorie(5)
        linie = [f"Pamięć: {ile} wpisów (archiwum: {arch})"]
        if top:
            linie.append("Top kategorie: " + ", ".join(f"{k}({v})" for k, v in top))
        return ActionResult("\n".join(linie))


@registry.register("historia")
class HistoriaAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        recs = ctx.learning.last_history(limit=8)
        if not recs:
            return ActionResult("Historia jest pusta.")
        linie = ["Ostatnie akcje:"]
        for r in recs:
            tresc = (r.nowa_tresc or r.stara_tresc)[:60]
            cofn = " [cofnięte]" if r.cofniete else ""
            linie.append(f"  {r.czas[:16]} {r.akcja}: \"{tresc}\"{cofn}")
        return ActionResult("\n".join(linie))


@registry.register("preferencje")
class PreferencjeAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        prefs = ctx.learning.all_preferences()
        if not prefs:
            return ActionResult("Brak zapisanych preferencji.")
        linie = ["Preferencje:"] + [f"  {k}: {v}" for k, v in prefs.items()]
        return ActionResult("\n".join(linie))


@registry.register("eksport")
class EksportAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        from ai.backup import export_to_file, auto_export_path
        from pathlib import Path
        base = Path(intent.argument or "~/.jarvis").expanduser()
        path = auto_export_path(base)
        r = export_to_file(ctx.memory, path)
        return ActionResult(f"Eksport: {path} ({r['main']} wpisów).")


@registry.register("help")
class HelpAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(
            "Komendy:\n"
            "  zapamiętaj <tekst>      — zapisz do pamięci\n"
            "  gdzie jest / szukaj     — szukaj w pamięci\n"
            "  zmień <stare> na <nowe> — aktualizuj wpis\n"
            "  zapomnij o <tekst>      — usuń wpis\n"
            "  cofnij                  — cofnij ostatnią akcję\n"
            "  timer na X minut        — ustaw timer\n"
            "  dodaj zadanie <tekst>   — dodaj do TODO\n"
            "  stan systemu            — CPU/RAM/dysk\n"
            "  włącz przekaźnik 1      — steruj ESP32\n"
            "  moje zadania / timery   — podgląd\n"
            "  eksport                 — backup pamięci\n"
            "  koniec                  — zakończ"
        )
