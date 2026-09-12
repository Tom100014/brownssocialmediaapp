"""
tools_manager.py - Registry der 12 deterministischen Standard-Werkzeuge.

STATUS: Gerüst (Schritt 2 der Implementierung). Definiert bereits das
Anthropic-Tool-Schema-Format und den Dispatch-Mechanismus, den
brain_router.py als `tool_executor` injiziert bekommt. Die konkreten
Werkzeug-Implementierungen (Kalender, Tasks/Notizen, Leads, Bild-Analyse,
Wetter/System) folgen im nächsten Schritt.

Design-Prinzip: Zustände werden NIE vom LLM geraten. Jedes Tool führt eine
echte Abfrage (SQLite, Dateisystem, Subprocess, externe API) aus und gibt
strukturierte, überprüfbare Daten zurück.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger("jarvis.tools_manager")

ToolFunction = Callable[..., Awaitable[dict[str, Any]]]


class ToolNotFoundError(Exception):
    pass


class ToolRegistry:
    """Hält Anthropic-Tool-Schemas und die zugehörigen ausführbaren Funktionen."""

    def __init__(self) -> None:
        self._schemas: list[dict[str, Any]] = []
        self._handlers: dict[str, ToolFunction] = {}

    def register(self, schema: dict[str, Any], handler: ToolFunction) -> None:
        name = schema["name"]
        if name in self._handlers:
            raise ValueError(f"Tool '{name}' ist bereits registriert.")
        self._schemas.append(schema)
        self._handlers[name] = handler
        logger.debug("Tool registriert: %s", name)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return list(self._schemas)

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            raise ToolNotFoundError(f"Unbekanntes Tool: {name}")
        return await handler(**arguments)


registry = ToolRegistry()

# Die 12 geplanten Tools (Platzhalter-Liste für die kommende Implementierung):
#   1. calendar_list_events
#   2. calendar_create_event
#   3. calendar_reschedule_event
#   4. tasks_create
#   5. tasks_list
#   6. tasks_complete
#   7. notes_write (Markdown)
#   8. leads_capture
#   9. contacts_upsert
#   10. analyze_image (multimodal, Claude/Gemini)
#   11. weather_current
#   12. system_check_service (echte Subprocess-/systemctl-Abfrage, keine Halluzination)
