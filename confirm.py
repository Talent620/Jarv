"""Potwierdzenia operacji destruktywnych (update, delete, undo, import).

Wzorzec:
    if confirm.ask("Czy na pewno chcesz usunąć?"):
        ...

Wszystkie potwierdzenia idą przez ten sam interfejs — jeśli kiedyś będzie GUI albo bot,
podmieniamy tylko jedną klasę. Headless tryb (np. testy) → auto-no.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional


class Confirmer:
    """Pyta użytkownika o potwierdzenie tak/nie."""

    TAK_FORMS = {"t", "tak", "y", "yes", "ok", "1", "tak.", "tak!", "potwierdzam"}
    NIE_FORMS = {"n", "nie", "no", "0", "anuluj", "nie.", "stop"}

    def __init__(
        self,
        enabled: bool = True,
        prompt_fn: Optional[Callable[[str], str]] = None,
        output_fn: Optional[Callable[[str], None]] = None,
    ):
        """
        :param enabled: jeśli False, potwierdzenia są wyłączone (zwraca True bez pytania).
                        UWAGA: bywa źle ustawione przez użytkownika — domyślnie True.
        :param prompt_fn: funkcja czytająca odpowiedź (input() domyślnie).
        :param output_fn: funkcja pisząca pytanie (print() domyślnie).
        """
        self.enabled = enabled
        self._prompt = prompt_fn or _safe_input
        self._output = output_fn or _safe_print

    def ask(self, pytanie: str, default_no: bool = True) -> bool:
        """Zwraca True jeśli użytkownik potwierdził, False w przeciwnym razie.

        Przy `enabled=False` zawsze True (potwierdzenia wyłączone w configu).
        Przy `default_no=True` (rekomendowane dla destruktywnych) — puste/EOF = False.
        """
        if not self.enabled:
            return True

        suffix = " (tak/nie)" if default_no else " (TAK/nie)"
        self._output(f"{pytanie}{suffix}")
        try:
            odp = self._prompt("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        if not odp:
            return not default_no
        if odp in self.TAK_FORMS:
            return True
        if odp in self.NIE_FORMS:
            return False
        # Niejednoznaczna odpowiedź — bezpieczniej zwrócić False
        self._output("Nie rozumiem odpowiedzi — uznaję za 'nie'.")
        return False


# ----- Pomocnicze -----

def _safe_input(prompt: str) -> str:
    """input() z obsługą braku tty."""
    if not sys.stdin or not sys.stdin.isatty():
        raise EOFError
    return input(prompt)


def _safe_print(msg: str) -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
