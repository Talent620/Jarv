"""Akcje codziennego researchu — plugin."""
from __future__ import annotations

import re

from actions.base import ActionResult, BaseAction
from core.registry import registry


def _parse_topic_and_time(tekst: str):
    """Wyciąga (topic, hour, minute) z tekstu."""
    t = tekst.strip()
    # Usuń prefiks
    t = re.sub(
        r"^(śledź\s+temat\s*|dodaj\s+temat\s+(badań\s*)?[:\s]*|"
        r"codzienn[yi]\s+research\s*[:\s]*|śledź\s*[:\s]*)",
        "", t, flags=re.I,
    ).strip()

    hour, minute = 8, 0
    m = re.search(r"\bo\s+(\d{1,2})(?::(\d{2}))?\b", t, re.I)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        t = (t[: m.start()] + t[m.end():]).strip(" ,.;:!?")

    topic = re.sub(r"\s+", " ", t).strip()
    return topic, hour, minute


@registry.register("research_set")
class ResearchSetAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("research"):
            return ActionResult("Moduł research niedostępny.", success=False)

        topic, hour, minute = _parse_topic_and_time(intent.surowy_tekst)
        if not topic:
            return ActionResult(
                "Podaj temat, np. 'śledź temat sztuczna inteligencja o 8:00'.",
                success=False,
            )

        t = ctx.research.add_topic(topic=topic, hour=hour, minute=minute)
        return ActionResult(
            f"📰 Temat '{t.topic}' dodany — codzienny research o {t.format_schedule()}.",
            data={"id": t.id, "topic": t.topic},
        )


@registry.register("research_list")
class ResearchListAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("research"):
            return ActionResult("Moduł research niedostępny.", success=False)
        return ActionResult(ctx.research.format_topics())


@registry.register("research_now")
class ResearchNowAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("research"):
            return ActionResult("Moduł research niedostępny.", success=False)

        # Szukaj tematu w tekście, albo weź pierwszy z listy
        t = re.sub(r"^(zrób|uruchom|research)\s+(research\s+)?(teraz\s+)?(na\s+temat\s+)?",
                   "", intent.surowy_tekst, flags=re.I).strip()

        if not t or len(t) < 3:
            topics = ctx.research.list_topics()
            if not topics:
                return ActionResult("Brak śledzonych tematów. Dodaj: 'śledź temat <nazwa>'.", success=False)
            t = topics[0].topic

        result = ctx.research.run_now(t)
        return ActionResult(f"🔍 Research '{t}':\n{result}", speak=False)


@registry.register("research_cancel")
class ResearchCancelAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("research"):
            return ActionResult("Moduł research niedostępny.", success=False)

        # Spróbuj po numerze
        m = re.search(r"\b(\d+)\b", intent.surowy_tekst)
        if m:
            topics = ctx.research.list_topics()
            idx = int(m.group(1))
            if 1 <= idx <= len(topics):
                tid = topics[idx - 1].id
                ctx.research.remove_topic(tid)
                return ActionResult(f"Usunięto temat '{topics[idx-1].topic}'.")

        t = re.sub(r"(usuń\s+temat|usuń\s+research|przestań\s+śledzić)\s*", "",
                   intent.surowy_tekst, flags=re.I).strip()
        if ctx.research.remove_topic(t):
            return ActionResult(f"Usunięto temat '{t}'.")
        return ActionResult(f"Nie znalazłem tematu '{t}'.", success=False)


@registry.register("research_latest")
class ResearchLatestAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if not ctx.has("research"):
            return ActionResult("Moduł research niedostępny.", success=False)

        t = re.sub(r"(ostatni\s+research|pokaż\s+research|wyniki\s+research)\s*(dla\s+|na\s+temat\s+)?",
                   "", intent.surowy_tekst, flags=re.I).strip()
        if not t or len(t) < 2:
            topics = ctx.research.list_topics()
            if topics:
                t = topics[0].topic
            else:
                return ActionResult("Brak śledzonych tematów.", success=False)

        summary = ctx.research.latest_result(t)
        if summary:
            return ActionResult(f"Ostatni research '{t}':\n{summary}", speak=False)
        return ActionResult(f"Brak wyników dla '{t}'.", success=False)
