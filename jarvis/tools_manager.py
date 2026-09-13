"""
tools_manager.py - Die deterministischen Standard-Werkzeuge von Jarvis
(12 Kern-Tools + Langzeit-Gedächtnis).

Grundsatz: Zustände werden NIE vom LLM geraten. Jedes Tool führt eine echte
Abfrage aus (SQLite, Dateisystem, Subprocess, externe API) und gibt
strukturierte, überprüfbare Daten zurück. brain_router.py ruft diese
Funktionen ausschließlich über `registry.execute(name, arguments)` auf,
nachdem Claude Sonnet einen `tool_use`-Block erzeugt hat.

Kalender/Tasks/Leads/Kontakte werden lokal in SQLite gehalten (siehe
storage.py). Ein echter Google-Calendar-Sync kann später ergänzt werden,
sobald der "google_calendar"-Connector OAuth-Tokens enthält - die Tool-
Signaturen bleiben dabei stabil.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

from config import DATA_DIR
from connectors_manager import connectors_manager
from storage import get_connection

logger = logging.getLogger("jarvis.tools_manager")

NOTES_DIR = DATA_DIR / "notes"

ToolFunction = Callable[..., Awaitable[dict[str, Any]]]


class ToolNotFoundError(Exception):
    pass


class ToolExecutionError(Exception):
    """Ein Tool konnte seine Aufgabe nicht ausführen (z. B. externe API down)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def tool(schema: dict[str, Any]) -> Callable[[ToolFunction], ToolFunction]:
    """Decorator, der eine Funktion direkt mit ihrem Anthropic-Tool-Schema registriert."""

    def decorator(func: ToolFunction) -> ToolFunction:
        registry.register(schema, func)
        return func

    return decorator


# =========================================================================
# 1-3. Kalender
# =========================================================================


@tool(
    {
        "name": "calendar_list_events",
        "description": "Listet anstehende Termine ab einem Zeitpunkt (oder alle, falls nicht angegeben).",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_iso": {
                    "type": "string",
                    "description": "ISO-8601-Zeitpunkt, ab dem Termine zurückgegeben werden. Optional.",
                },
                "limit": {"type": "integer", "description": "Maximale Anzahl Termine.", "default": 20},
            },
        },
    }
)
async def calendar_list_events(from_iso: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    conn = get_connection()
    if from_iso:
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE start_time >= ? ORDER BY start_time LIMIT ?",
            (from_iso, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM calendar_events ORDER BY start_time LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


@tool(
    {
        "name": "calendar_create_event",
        "description": "Legt einen neuen Termin an.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {"type": "string", "description": "ISO-8601-Startzeit"},
                "end_time": {"type": "string", "description": "ISO-8601-Endzeit, optional"},
                "location": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["title", "start_time"],
        },
    }
)
async def calendar_create_event(
    title: str,
    start_time: str,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    now = _now_iso()
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO calendar_events (title, start_time, end_time, location, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (title, start_time, end_time, location, notes, now, now),
    )
    conn.commit()
    return {"event_id": cursor.lastrowid, "status": "created"}


@tool(
    {
        "name": "calendar_reschedule_event",
        "description": "Verschiebt einen bestehenden Termin auf eine neue Start-/Endzeit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "new_start_time": {"type": "string", "description": "ISO-8601-Startzeit"},
                "new_end_time": {"type": "string"},
            },
            "required": ["event_id", "new_start_time"],
        },
    }
)
async def calendar_reschedule_event(
    event_id: int, new_start_time: str, new_end_time: Optional[str] = None
) -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE calendar_events SET start_time = ?, end_time = COALESCE(?, end_time), updated_at = ? WHERE id = ?",
        (new_start_time, new_end_time, _now_iso(), event_id),
    )
    conn.commit()
    if cursor.rowcount == 0:
        raise ToolExecutionError(f"Termin mit ID {event_id} existiert nicht.")
    return {"event_id": event_id, "status": "rescheduled", "new_start_time": new_start_time}


# =========================================================================
# 4-6. Tasks
# =========================================================================


@tool(
    {
        "name": "tasks_create",
        "description": "Legt eine neue Aufgabe an.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due_date": {"type": "string", "description": "ISO-8601-Datum, optional"},
            },
            "required": ["title"],
        },
    }
)
async def tasks_create(title: str, due_date: Optional[str] = None) -> dict[str, Any]:
    now = _now_iso()
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO tasks (title, due_date, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, due_date, now, now),
    )
    conn.commit()
    return {"task_id": cursor.lastrowid, "status": "created"}


@tool(
    {
        "name": "tasks_list",
        "description": "Listet Aufgaben, optional gefiltert nach Erledigungsstatus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "only_open": {"type": "boolean", "default": True},
            },
        },
    }
)
async def tasks_list(only_open: bool = True) -> dict[str, Any]:
    conn = get_connection()
    if only_open:
        rows = conn.execute("SELECT * FROM tasks WHERE done = 0 ORDER BY due_date IS NULL, due_date").fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY due_date IS NULL, due_date").fetchall()
    return {"tasks": [dict(row) for row in rows]}


@tool(
    {
        "name": "tasks_complete",
        "description": "Markiert eine Aufgabe als erledigt.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    }
)
async def tasks_complete(task_id: int) -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE tasks SET done = 1, updated_at = ? WHERE id = ?", (_now_iso(), task_id)
    )
    conn.commit()
    if cursor.rowcount == 0:
        raise ToolExecutionError(f"Aufgabe mit ID {task_id} existiert nicht.")
    return {"task_id": task_id, "status": "completed"}


# =========================================================================
# 7. Notizen (Markdown)
# =========================================================================


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "notiz"


@tool(
    {
        "name": "notes_write",
        "description": "Schreibt eine Notiz als Markdown-Datei ab (überschreibt bei gleichem Titel).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["title", "content"],
        },
    }
)
async def notes_write(title: str, content: str) -> dict[str, Any]:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{_slugify(title)}.md"
    path = NOTES_DIR / filename
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return {"filename": filename, "path": str(path), "status": "written"}


# =========================================================================
# 8-9. Leads & Kontakte
# =========================================================================


@tool(
    {
        "name": "leads_capture",
        "description": "Erfasst einen neuen Lead (potenziellen Kunden/Kontakt).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "source": {"type": "string", "description": "z. B. 'Messe', 'Website', 'Empfehlung'"},
                "contact_info": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    }
)
async def leads_capture(
    name: str,
    source: Optional[str] = None,
    contact_info: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO leads (name, source, contact_info, notes, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, source, contact_info, notes, _now_iso()),
    )
    conn.commit()
    return {"lead_id": cursor.lastrowid, "status": "captured"}


@tool(
    {
        "name": "contacts_upsert",
        "description": "Legt einen Kontakt an oder aktualisiert ihn anhand des Namens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    }
)
async def contacts_upsert(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    now = _now_iso()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO contacts (name, email, phone, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            email=COALESCE(excluded.email, contacts.email),
            phone=COALESCE(excluded.phone, contacts.phone),
            notes=COALESCE(excluded.notes, contacts.notes),
            updated_at=excluded.updated_at
        """,
        (name, email, phone, notes, now, now),
    )
    conn.commit()
    return {"name": name, "status": "upserted"}


# =========================================================================
# 10. Bild-/Foto-Analyse (multimodal via Claude)
# =========================================================================


@tool(
    {
        "name": "analyze_image",
        "description": (
            "Analysiert ein Bild (z. B. Beleg, Statusfoto) multimodal via Claude und beantwortet "
            "eine dazu gestellte Frage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Lokaler Pfad zur Bilddatei"},
                "question": {
                    "type": "string",
                    "description": "Was soll zum Bild analysiert werden?",
                    "default": "Beschreibe das Bild und extrahiere relevante Daten (z. B. Beträge, Datum).",
                },
            },
            "required": ["image_path"],
        },
    }
)
async def analyze_image(
    image_path: str,
    question: str = "Beschreibe das Bild und extrahiere relevante Daten (z. B. Beträge, Datum).",
) -> dict[str, Any]:
    import openai

    from config import settings

    path = Path(image_path)
    if not path.exists():
        raise ToolExecutionError(f"Bilddatei nicht gefunden: {image_path}")

    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if media_type is None:
        raise ToolExecutionError(f"Nicht unterstütztes Bildformat: {path.suffix}")

    api_key = connectors_manager.get_credential("openrouter", "api_key") or (
        settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else None
    )
    if not api_key:
        raise ToolExecutionError("Kein OpenRouter-API-Key konfiguriert (Connector 'openrouter' fehlt).")

    model = connectors_manager.get_credential("openrouter", "sonnet_model") or connectors_manager.get_setting(
        "claude_model", settings.claude_model
    )
    image_b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

    client = openai.AsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    try:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                    ],
                }
            ],
        )
    except openai.OpenAIError as exc:
        raise ToolExecutionError(f"Bildanalyse über OpenRouter fehlgeschlagen: {exc}") from exc

    text = response.choices[0].message.content or ""
    return {"analysis": text.strip()}


# =========================================================================
# 11. Wetter
# =========================================================================


@tool(
    {
        "name": "weather_current",
        "description": "Fragt das aktuelle Wetter für einen Ort über einen echten Wetterdienst ab.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }
)
async def weather_current(city: str) -> dict[str, Any]:
    api_key = connectors_manager.get_credential("weather", "api_key")
    if not api_key:
        raise ToolExecutionError("Kein Wetter-Connector konfiguriert (Connector 'weather' fehlt).")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api_key, "units": "metric", "lang": "de"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(f"Wetterdienst-Fehler ({exc.response.status_code}): {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Wetterdienst nicht erreichbar: {exc}") from exc

    data = response.json()
    return {
        "city": city,
        "temperature_c": data.get("main", {}).get("temp"),
        "feels_like_c": data.get("main", {}).get("feels_like"),
        "condition": (data.get("weather") or [{}])[0].get("description"),
        "humidity_percent": data.get("main", {}).get("humidity"),
        "wind_speed_ms": data.get("wind", {}).get("speed"),
    }


# =========================================================================
# 13-14. Langzeit-Gedächtnis ("dazulernen")
#
# Fakten, die der Nutzer explizit mitteilt (Präferenzen, wiederkehrende
# Infos, Korrekturen), werden hier persistent abgelegt und bei jedem
# System-Prompt automatisch mit eingespielt (siehe brain_router.MemoryStore).
# Auch das ist deterministisch: Jarvis "errät" gespeichertes Wissen nie,
# er liest es aus SQLite.
# =========================================================================


@tool(
    {
        "name": "remember_fact",
        "description": (
            "Speichert eine Tatsache/Präferenz dauerhaft im Langzeit-Gedächtnis, damit sie in "
            "künftigen Gesprächen automatisch bekannt ist. Nutzen, wenn der Nutzer explizit "
            "etwas mitteilt, das man sich merken soll (z. B. Vorlieben, wiederkehrende Fakten)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Kurzer, eindeutiger Schlüssel, z. B. 'lieblingskaffee'"},
                "value": {"type": "string", "description": "Der zu merkende Inhalt"},
                "category": {"type": "string", "description": "z. B. 'präferenz', 'kontext', 'projekt'"},
            },
            "required": ["key", "value"],
        },
    }
)
async def remember_fact(key: str, value: str, category: Optional[str] = None) -> dict[str, Any]:
    now = _now_iso()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO memory (key, value, category, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=excluded.updated_at
        """,
        (key, value, category, now, now),
    )
    conn.commit()
    return {"key": key, "status": "remembered"}


@tool(
    {
        "name": "recall_facts",
        "description": "Durchsucht das Langzeit-Gedächtnis nach gespeicherten Fakten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff, optional - leer lässt alles zurückgeben"},
            },
        },
    }
)
async def recall_facts(query: Optional[str] = None) -> dict[str, Any]:
    conn = get_connection()
    if query:
        rows = conn.execute(
            "SELECT * FROM memory WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM memory ORDER BY updated_at DESC LIMIT 50").fetchall()
    return {"facts": [dict(row) for row in rows]}


# =========================================================================
# 15. System-Check (echte Subprocess-Abfrage - KEINE Halluzination)
# =========================================================================

_SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.@-]+$")


@tool(
    {
        "name": "system_check_service",
        "description": (
            "Prüft über systemctl, ob ein Dienst auf dem Server aktiv ist. Liefert den echten "
            "Systemstatus - wird NIEMALS vom Sprachmodell geraten."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string", "description": "z. B. 'nginx', 'docker'"}},
            "required": ["service_name"],
        },
    }
)
async def system_check_service(service_name: str) -> dict[str, Any]:
    if not _SERVICE_NAME_PATTERN.match(service_name):
        raise ToolExecutionError(f"Ungültiger Dienstname: {service_name!r}")

    try:
        process = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
    except FileNotFoundError as exc:
        raise ToolExecutionError("systemctl ist auf diesem System nicht verfügbar.") from exc
    except asyncio.TimeoutError as exc:
        raise ToolExecutionError(f"systemctl-Abfrage für '{service_name}' hat zu lange gedauert.") from exc

    state = stdout.decode("utf-8").strip()
    return {"service_name": service_name, "state": state, "active": state == "active"}
