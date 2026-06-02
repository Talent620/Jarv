"""ActionRegistry — system pluginów."""
from __future__ import annotations
from typing import Dict, List, Optional, Type


class ActionRegistry:
    def __init__(self):
        self._map: Dict[str, Type] = {}

    def register(self, *intent_names: str):
        def decorator(cls):
            for name in intent_names:
                self._map[name] = cls
            return cls
        return decorator

    def get(self, intent_name: str) -> Optional[Type]:
        return self._map.get(intent_name)

    def list_actions(self) -> Dict[str, str]:
        return {k: v.__name__ for k, v in self._map.items()}


registry = ActionRegistry()
