"""
server_api.py - FastAPI-Backend für den zentralen Jarvis-Server.

Endpunkte:
    POST /chat      - Text/Voice-Eingabe, liefert Jarvis-Antwort (brain_router + tools_manager)
    POST /webhook   - externe Trigger (z. B. Cron, IFTTT, Kalender-Push)
    POST /context   - Cron-Aktualisierung der gepufferten Kontextdatei
    GET  /commands  - Polling-Endpunkt für local_client.py
    POST /commands/{id}/ack - Bestätigung einer ausgeführten Aktion
    /connectors, /settings - Verwaltung aller externen Anbindungen & Laufzeit-Settings
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from brain_router import BrainRouter, BrainRouterError
from config import CONTEXT_DIR, settings
from connectors_manager import (
    ConnectorNotFoundError,
    ConnectorValidationError,
    connectors_manager,
    list_schemas,
)
from tools_manager import ToolExecutionError, registry as tool_registry

logger = logging.getLogger("jarvis.server_api")

app = FastAPI(title="Jarvis Assistant API", version="0.1.0")

_brain_router = BrainRouter(
    tool_schemas=tool_registry.schemas,
    tool_executor=tool_registry.execute,
)

# In-memory Konversationsverlauf je Session. Geht bei Server-Neustart verloren -
# unkritisch, da jede Anfrage ohnehin den frischen Kontext aus /context lädt.
_conversation_history: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY_TURNS = 20


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
    session_id = request.session_id or str(uuid.uuid4())
    history = _conversation_history.get(session_id, [])

    try:
        response = await _brain_router.route(request.message, conversation_history=history)
    except BrainRouterError as exc:
        logger.warning("Chat-Anfrage fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": response.text})
    _conversation_history[session_id] = history[-_MAX_HISTORY_TURNS * 2 :]

    return ChatResponse(reply=response.text, model_used=response.model_used.value, session_id=session_id)


@app.post("/context", dependencies=[Depends(require_auth)])
async def update_context(request: ContextUpdateRequest) -> dict[str, str]:
    """Schreibt den (typischerweise per Cron zusammengestellten) Kontext-Payload
    nach context/live_context.json, den brain_router.ContextLoader vor jedem
    LLM-Aufruf einliest."""
    payload = dict(request.payload)
    payload["last_updated"] = datetime.now(timezone.utc).isoformat()

    context_path = CONTEXT_DIR / "live_context.json"
    try:
        context_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kontext konnte nicht geschrieben werden: {exc}"
        ) from exc

    return {"status": "updated", "last_updated": payload["last_updated"]}


class WebhookPayload(BaseModel):
    """Zwei unterstützte Formen:
    1. {"tool": "weather_current", "arguments": {...}} - führt ein Tool direkt aus.
    2. {"action_id": "close_browser_tabs", "parameters": {...}} - reiht einen
       Trigger für local_client.py in die Befehls-Queue ein.
    """

    tool: Optional[str] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    action_id: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


@app.post("/webhook", dependencies=[Depends(require_auth)])
async def webhook(payload: WebhookPayload) -> dict[str, Any]:
    if payload.tool:
        try:
            result = await tool_registry.execute(payload.tool, payload.arguments)
        except ToolExecutionError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"status": "executed", "tool": payload.tool, "result": result}

    if payload.action_id:
        command_uuid = enqueue_command(payload.action_id, payload.parameters)
        return {"status": "queued", "command_id": command_uuid}

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Webhook-Payload benötigt entweder 'tool' oder 'action_id'.",
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


@app.get("/tools", dependencies=[Depends(require_auth)])
async def list_tools() -> list[dict[str, Any]]:
    """Zeigt alle registrierten Tool-Schemas (Anthropic-Format) - nützlich zum
    Debuggen und für eine spätere Admin-Übersicht."""
    return tool_registry.schemas


_ADMIN_HTML_PATH = Path(__file__).resolve().parent / "static" / "admin.html"


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_ui() -> str:
    """Statische Connector-Verwaltungsoberfläche: pro Connector Felder,
    'Verbinden'/'Aktualisieren', 'Testen', 'Aktivieren/Deaktivieren' und
    'Trennen'. Die Seite selbst ist ungeschützt (reines HTML/JS), jeder
    API-Aufruf darin erfordert aber weiterhin das API_AUTH_TOKEN, das man im
    Browser einträgt und das lokal (localStorage) gespeichert wird."""
    return _ADMIN_HTML_PATH.read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
