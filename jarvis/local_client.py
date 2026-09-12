"""
local_client.py - Schlanker Polling-Daemon für den Laptop/Mac.

STATUS: Gerüst (Schritt 2 der Implementierung). Fragt periodisch
`GET /commands` auf server_api.py ab und führt vordefinierte, lokale
Aktionen anhand einer `action_id` aus (niemals rohen, vom Server
gesendeten Code - reine Trigger + Parameter).

Die konkreten Aktionen (Tabs schließen, Browser öffnen, Programme steuern)
folgen im nächsten Implementierungsschritt.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import httpx

from config import settings

logger = logging.getLogger("jarvis.local_client")

ActionHandler = Callable[[dict[str, Any]], Awaitable[None]]

# Registry lokaler Aktionen. Wird im nächsten Schritt mit echten
# Python-/AppleScript-Handlern befüllt (z. B. "close_browser_tabs",
# "open_url", "launch_app").
ACTION_HANDLERS: dict[str, ActionHandler] = {}


class LocalClientDaemon:
    def __init__(self) -> None:
        self._base_url = settings.server_base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.api_auth_token.get_secret_value()}"}
        self._poll_interval = settings.local_client_poll_interval_seconds

    async def run_forever(self) -> None:
        logger.info("Jarvis local_client gestartet, Polling-Intervall: %.1fs", self._poll_interval)
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=10.0) as client:
            while True:
                try:
                    await self._poll_once(client)
                except httpx.HTTPError as exc:
                    logger.warning("Server nicht erreichbar: %s", exc)
                except Exception:
                    logger.exception("Unerwarteter Fehler im Polling-Loop")
                await asyncio.sleep(self._poll_interval)

    async def _poll_once(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/commands")
        response.raise_for_status()
        commands = response.json()

        for command in commands:
            action_id = command.get("action_id")
            handler = ACTION_HANDLERS.get(action_id)
            if handler is None:
                logger.warning("Unbekannte action_id vom Server empfangen: %s", action_id)
                continue
            try:
                await handler(command.get("parameters", {}))
            except Exception:
                logger.exception("Ausführung von action_id '%s' fehlgeschlagen", action_id)


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    asyncio.run(LocalClientDaemon().run_forever())
