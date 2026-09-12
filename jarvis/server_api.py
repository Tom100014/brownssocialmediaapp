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

from fastapi import Body, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from config import settings
from connectors_manager import (
    ConnectorNotFoundError,
    ConnectorValidationError,
    connectors_manager,
    list_schemas,
)

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


# --- Connector-Verwaltung -----------------------------------------------
#
# Hier werden ALLE externen Anbindungen (LLM-Provider, Voice-APIs, Kalender,
# Mail, Musik, Wetter, generische Webhooks, ...) zentral gespeichert und
# konfiguriert. Secrets liegen verschlüsselt in SQLite (siehe storage.py) und
# werden über die API niemals im Klartext zurückgegeben.


class ConnectorUpsertRequest(BaseModel):
    connector_type: str = Field(..., description="z. B. 'anthropic', 'google_calendar', 'weather'")
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ConnectorResponse(BaseModel):
    name: str
    connector_type: str
    credentials: dict[str, Any]
    config: dict[str, Any]
    enabled: bool
    created_at: str
    updated_at: str


@app.get("/connectors/schemas", dependencies=[Depends(require_auth)])
async def get_connector_schemas() -> list[dict[str, Any]]:
    """Liefert alle bekannten Connector-Typen inkl. benötigter Felder - z. B.
    damit eine Admin-UI dynamisch ein Formular pro Connector rendern kann."""
    return list_schemas()


@app.get("/connectors", response_model=list[ConnectorResponse], dependencies=[Depends(require_auth)])
async def list_connectors() -> list[dict[str, Any]]:
    return [record.redacted() for record in connectors_manager.list_connectors()]


@app.get("/connectors/{name}", response_model=ConnectorResponse, dependencies=[Depends(require_auth)])
async def get_connector(name: str) -> dict[str, Any]:
    record = connectors_manager.get_connector(name)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{name}' nicht gefunden.")
    return record.redacted()


@app.put("/connectors/{name}", response_model=ConnectorResponse, dependencies=[Depends(require_auth)])
async def upsert_connector(name: str, request: ConnectorUpsertRequest) -> dict[str, Any]:
    """Legt einen Connector an oder aktualisiert ihn (voller Ersatz der Credentials).
    Damit lässt sich z. B. der Anthropic-Key rotieren, ohne den Server neu zu starten."""
    try:
        record = connectors_manager.upsert_connector(
            name=name,
            connector_type=request.connector_type,
            credentials=request.credentials,
            config=request.config,
            enabled=request.enabled,
        )
    except ConnectorValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return record.redacted()


@app.delete("/connectors/{name}", dependencies=[Depends(require_auth)])
async def delete_connector(name: str) -> dict[str, str]:
    try:
        connectors_manager.delete_connector(name)
    except ConnectorNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"status": "deleted"}


@app.post("/connectors/{name}/enable", dependencies=[Depends(require_auth)])
async def set_connector_enabled(name: str, enabled: bool = Body(..., embed=True)) -> dict[str, Any]:
    record = connectors_manager.get_connector(name)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{name}' nicht gefunden.")
    updated = connectors_manager.upsert_connector(
        name=name,
        connector_type=record.connector_type,
        credentials=record.credentials,
        config=record.config,
        enabled=enabled,
    )
    return updated.redacted()


@app.post("/connectors/{name}/test", dependencies=[Depends(require_auth)])
async def test_connector(name: str) -> dict[str, Any]:
    """Führt einen minimalen Live-Check gegen den externen Dienst aus, um
    Credentials zu verifizieren, ohne dass man erst eine echte Anfrage über
    /chat schicken muss."""
    record = connectors_manager.get_connector(name)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connector '{name}' nicht gefunden.")

    if record.connector_type == "anthropic":
        import anthropic

        try:
            client = anthropic.AsyncAnthropic(api_key=record.credentials.get("api_key", ""))
            await client.messages.create(
                model=settings.claude_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    if record.connector_type == "google_gemini":
        import google.generativeai as genai

        try:
            genai.configure(api_key=record.credentials.get("api_key", ""))
            model = genai.GenerativeModel(settings.gemini_model)
            await model.generate_content_async("ping")
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    return {"status": "not_implemented", "detail": f"Kein Live-Test für Typ '{record.connector_type}' verfügbar."}


# --- Allgemeine Einstellungen --------------------------------------------


@app.get("/settings", dependencies=[Depends(require_auth)])
async def get_settings_endpoint() -> dict[str, Any]:
    return connectors_manager.get_all_settings()


@app.put("/settings", dependencies=[Depends(require_auth)])
async def update_settings_endpoint(values: dict[str, Any]) -> dict[str, Any]:
    return connectors_manager.update_settings(values)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
