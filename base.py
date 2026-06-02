"""Interfejs każdej akcji."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ActionResult:
    text: str
    success: bool = True
    data: Optional[Any] = None
    speak: bool = True


class BaseAction(ABC):
    @abstractmethod
    def run(self, intent, ctx) -> ActionResult:
        ...

    def can_handle(self, intent, ctx) -> bool:
        return True
