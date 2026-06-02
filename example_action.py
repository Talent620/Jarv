"""Przykład własnej akcji — skopiuj i dostosuj.

Krok 1: Skopiuj plik jako actions/moja_akcja.py
Krok 2: Zmień wzorzec regex i logikę run()
Krok 3: Gotowe — ładowany automatycznie przy starcie Jarvisa

NIE musisz edytować assistant.py, intent.py ani żadnego innego pliku.
"""
import re
from core.registry import registry
from ai.intent import IntentDetector
from actions.base import BaseAction, ActionResult

# ─── Krok 1: wzorzec regex ────────────────────────────────────────────────────
# "elektronika" to zwykły string — nie musi być w IntentType enum
_INTENT_NAME = "elektronika"
_RX = re.compile(r"\b(oblicz|przelicz)\s+(opór|rezystancję|omy?)\b", re.I)

# Rejestracja wzorca — bez edycji intent.py
# IntentDetector.register_pattern() przyjmuje (string_lub_IntentType, pattern)
IntentDetector.register_pattern(_INTENT_NAME, _RX)


# ─── Krok 2: klasa akcji ─────────────────────────────────────────────────────
@registry.register(_INTENT_NAME)
class ElektronikaAction(BaseAction):
    """Przelicznik Ohma.

    Komendy:
      "oblicz opór mam 5V i 20mA"
      "oblicz rezystancję 100 i 220 omów"
    """

    def run(self, intent, ctx) -> ActionResult:
        t = intent.surowy_tekst.lower()

        # R = U/I
        u = self._val(t, r"(\d+(?:[.,]\d+)?)\s*v\b")
        i = self._val(t, r"(\d+(?:[.,]\d+)?)\s*m?a\b")
        if u and i:
            i_a = i / 1000 if "ma" in t else i
            if i_a == 0:
                return ActionResult("Natężenie nie może być zerem.")
            return ActionResult(
                f"R = {u/i_a:.1f} Ω | P = {u*i_a*1000:.0f} mW"
            )

        # Szeregowe/równoległe
        vals = [float(x.replace(",", "."))
                for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*[oó]", t)]
        if len(vals) >= 2:
            sz = sum(vals)
            rp = 1 / sum(1/v for v in vals if v > 0)
            return ActionResult(
                f"Szeregowo: {sz:.1f} Ω | Równolegle: {rp:.2f} Ω"
            )

        return ActionResult("Podaj np. '5V i 20mA' albo '100 i 220 omów'.")

    def _val(self, text, pattern):
        m = re.search(pattern, text)
        return float(m.group(1).replace(",", ".")) if m else None
