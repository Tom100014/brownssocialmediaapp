"""
server_api.py - FastAPI-Backend für den zentralen Jarvis-Server.

STATUS: Gerüst (Schritt 2 der Implementierung). Definiert die geplanten
Endpunkte und die Befehls-Queue für den lokalen Client. Volle Anbindung an
brain_router.py / tools_manager.py / audio_pipeline.py folgt im nächsten
Schritt.

Endpunkte (geplant):
    POST /chat      - Text/Voice-Eingabe, liefert Jarvis-Antwort
    POST /webhook   - externe Trigger (z. B. Cron, IFTTT, Kalender-Push)
    POST /context   - Cron-Aktualisierung der gepufferten Kontextdatei
    GET  /commands  - Polling-Endpunkt für local_client.py
    POST /commands/{id}/ack - Bestätigung einer ausgeführten Aktion
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from config import settings

logger = logging.getLogger("jarvis.server_api")

app = FastAPI(title="Jarvis Assistant API", version="0.1.0")


def require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    expected = f"Bearer {settings.api_auth_token.get_secret_value()}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges oder fehlendes Token.")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    model_used: str
    session_id: str


class ContextUpdateRequest(BaseModel):
    payload: dict[str, Any]


class PendingCommand(BaseModel):
    action_id: str
    parameters: dict[str, Any] = {}
    status: Literal["pending", "acknowledged"] = "pending"


# In-memory Befehls-Queue für den lokalen Client. Bei Bedarf durch SQLite
# ersetzbar, sobald Persistenz über Server-Neustarts nötig ist.
_command_queue: dict[str, PendingCommand] = {}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_auth)])
async def chat(request: ChatRequest) -> ChatResponse:
    """TODO (nächster Schritt): Anbindung an brain_router.BrainRouter.route()."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chat-Endpunkt wird im nächsten Implementierungsschritt an brain_router angebunden.",
    )


@app.post("/context", dependencies=[Depends(require_auth)])
async def update_context(request: ContextUpdateRequest) -> dict[str, str]:
    """TODO (nächster Schritt): Schreibt request.payload nach context/live_context.json."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Context-Update folgt im nächsten Implementierungsschritt.",
    )


@app.post("/webhook", dependencies=[Depends(require_auth)])
async def webhook(payload: dict[str, Any]) -> dict[str, str]:
    """TODO (nächster Schritt): Externe Trigger auf Tools/Router mappen."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Webhook-Verarbeitung folgt im nächsten Implementierungsschritt.",
    )


@app.get("/commands", dependencies=[Depends(require_auth)])
async def get_pending_commands() -> list[PendingCommand]:
    """Wird von local_client.py alle 2-5s gepollt."""
    return [cmd for cmd in _command_queue.values() if cmd.status == "pending"]


@app.post("/commands/{action_uuid}/ack", dependencies=[Depends(require_auth)])
async def acknowledge_command(action_uuid: str) -> dict[str, str]:
    cmd = _command_queue.get(action_uuid)
    if cmd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Befehl nicht gefunden.")
    cmd.status = "acknowledged"
    return {"status": "acknowledged"}


def enqueue_command(action_id: str, parameters: dict[str, Any]) -> str:
    """Interne Hilfsfunktion (für tools_manager.py), um dem Laptop einen Trigger
    zu senden. Der Server schickt niemals rohen Code, nur action_id + Parameter."""
    command_uuid = str(uuid.uuid4())
    _command_queue[command_uuid] = PendingCommand(action_id=action_id, parameters=parameters)
    return command_uuid


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
