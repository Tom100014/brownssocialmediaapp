"""
connectors_manager.py - Zentrale Verwaltung aller externen Connectors und
allgemeinen Jarvis-Einstellungen.

Das ist die "eine Stelle", an der API-Keys/Tokens für Anthropic, Gemini,
Deepgram, ElevenLabs, Google Calendar, Gmail, Spotify, Wetter usw. sowie
freie Laufzeit-Einstellungen (Routing-Modus, Sprache, Stimme, ...) gespeichert
werden. Secrets liegen verschlüsselt in SQLite (siehe storage.py); nach
außen (API/Logs) werden sie ausschließlich redigiert ausgegeben.

Andere Module (brain_router.py, audio_pipeline.py, tools_manager.py) fragen
ihre Credentials über `connectors_manager.get_credential(...)` ab und fallen
bei Bedarf auf die statischen `.env`-Defaults in config.py zurück.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from storage import decrypt, encrypt, get_connection

logger = logging.getLogger("jarvis.connectors_manager")


class ConnectorValidationError(Exception):
    """Die übergebenen Credentials/Config passen nicht zum Connector-Schema."""


class ConnectorNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ConnectorField:
    key: str
    required: bool = True
    secret: bool = True
    description: str = ""


@dataclass(frozen=True)
class ConnectorSchema:
    connector_type: str
    label: str
    category: str  # "llm" | "voice" | "calendar" | "email" | "music" | "data" | "custom"
    fields: list[ConnectorField] = field(default_factory=list)


# Bekannte Connector-Typen. Neue Typen können ergänzt werden, ohne bestehenden
# Code zu brechen - unbekannte Typen werden als "custom" mit Freiform-Feldern
# akzeptiert (siehe upsert_connector).
CONNECTOR_SCHEMAS: dict[str, ConnectorSchema] = {
    "openrouter": ConnectorSchema(
        connector_type="openrouter",
        label="OpenRouter (LLM-Gateway für Claude + Gemini)",
        category="llm",
        fields=[
            ConnectorField("api_key", description="OpenRouter API-Key"),
            ConnectorField(
                "sonnet_model",
                required=False,
                secret=False,
                description="Modell-Slug für komplexe Aufgaben, z. B. anthropic/claude-3.5-sonnet",
            ),
            ConnectorField(
                "flash_model",
                required=False,
                secret=False,
                description="Modell-Slug für schnelle Antworten, z. B. google/gemini-2.5-flash",
            ),
        ],
    ),
    "deepgram": ConnectorSchema(
        connector_type="deepgram",
        label="Deepgram (STT)",
        category="voice",
        fields=[ConnectorField("api_key", description="Deepgram API-Key")],
    ),
    "elevenlabs": ConnectorSchema(
        connector_type="elevenlabs",
        label="ElevenLabs (TTS)",
        category="voice",
        fields=[
            ConnectorField("api_key", description="ElevenLabs API-Key"),
            ConnectorField("voice_id", required=False, secret=False, description="Standard-Voice-ID"),
        ],
    ),
    "google_calendar": ConnectorSchema(
        connector_type="google_calendar",
        label="Google Calendar",
        category="calendar",
        fields=[
            ConnectorField("client_id", secret=False),
            ConnectorField("client_secret"),
            ConnectorField("refresh_token"),
        ],
    ),
    "gmail": ConnectorSchema(
        connector_type="gmail",
        label="Gmail",
        category="email",
        fields=[
            ConnectorField("client_id", secret=False),
            ConnectorField("client_secret"),
            ConnectorField("refresh_token"),
        ],
    ),
    "spotify": ConnectorSchema(
        connector_type="spotify",
        label="Spotify",
        category="music",
        fields=[
            ConnectorField("client_id", secret=False),
            ConnectorField("client_secret"),
            ConnectorField("refresh_token"),
        ],
    ),
    "weather": ConnectorSchema(
        connector_type="weather",
        label="Wetterdienst",
        category="data",
        fields=[ConnectorField("api_key")],
    ),
    "webhook": ConnectorSchema(
        connector_type="webhook",
        label="Generischer Webhook",
        category="custom",
        fields=[
            ConnectorField("url", secret=False),
            ConnectorField("secret", required=False),
        ],
    ),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_schema(connector_type: str) -> Optional[ConnectorSchema]:
    return CONNECTOR_SCHEMAS.get(connector_type)


def list_schemas() -> list[dict[str, Any]]:
    """JSON-serialisierbare Übersicht aller bekannten Connector-Typen, z. B.
    damit eine spätere Admin-UI dynamisch Formulare rendern kann."""
    return [
        {
            "connector_type": schema.connector_type,
            "label": schema.label,
            "category": schema.category,
            "fields": [
                {
                    "key": f.key,
                    "required": f.required,
                    "secret": f.secret,
                    "description": f.description,
                }
                for f in schema.fields
            ],
        }
        for schema in CONNECTOR_SCHEMAS.values()
    ]


def _validate_credentials(connector_type: str, credentials: dict[str, Any]) -> None:
    schema = get_schema(connector_type)
    if schema is None:
        # Unbekannter Typ -> erlaubt als "custom", aber muss mind. ein Feld haben.
        if not credentials:
            raise ConnectorValidationError(
                f"Unbekannter Connector-Typ '{connector_type}' benötigt mindestens ein Credential-Feld."
            )
        return

    missing = [
        f.key for f in schema.fields
        if f.required and not str(credentials.get(f.key, "")).strip()
    ]
    if missing:
        raise ConnectorValidationError(
            f"Connector '{connector_type}' fehlt Pflichtfelder: {', '.join(missing)}"
        )


def _redact(connector_type: str, credentials: dict[str, Any]) -> dict[str, Any]:
    schema = get_schema(connector_type)
    secret_keys = {f.key for f in schema.fields if f.secret} if schema else set(credentials.keys())

    redacted: dict[str, Any] = {}
    for key, value in credentials.items():
        if key in secret_keys and isinstance(value, str) and value:
            redacted[key] = f"{value[:3]}…{value[-2:]}" if len(value) > 6 else "•••"
        else:
            redacted[key] = value
    return redacted


@dataclass
class ConnectorRecord:
    name: str
    connector_type: str
    credentials: dict[str, Any]
    config: dict[str, Any]
    enabled: bool
    created_at: str
    updated_at: str

    def redacted(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connector_type": self.connector_type,
            "credentials": _redact(self.connector_type, self.credentials),
            "config": self.config,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ConnectorsManager:
    """CRUD + verschlüsselte Ablage für Connectors, plus Key-Value-Settings."""

    def __init__(self, cache_ttl_seconds: float = 5.0) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, ConnectorRecord]] = {}

    # -- Connectors ---------------------------------------------------------

    def upsert_connector(
        self,
        name: str,
        connector_type: str,
        credentials: dict[str, Any],
        config: Optional[dict[str, Any]] = None,
        enabled: bool = True,
    ) -> ConnectorRecord:
        if not name or not name.strip():
            raise ConnectorValidationError("Connector-Name darf nicht leer sein.")

        _validate_credentials(connector_type, credentials)

        existing = self._get_raw(name)
        now = _now_iso()
        created_at = existing["created_at"] if existing else now

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO connectors (name, connector_type, credentials_encrypted, config_json, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                connector_type=excluded.connector_type,
                credentials_encrypted=excluded.credentials_encrypted,
                config_json=excluded.config_json,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (
                name,
                connector_type,
                encrypt(json.dumps(credentials, ensure_ascii=False)),
                json.dumps(config or {}, ensure_ascii=False),
                int(enabled),
                created_at,
                now,
            ),
        )
        conn.commit()
        self._cache.pop(name, None)
        logger.info("Connector '%s' (%s) gespeichert.", name, connector_type)
        return self.get_connector(name)  # type: ignore[return-value]

    def get_connector(self, name: str) -> Optional[ConnectorRecord]:
        cached = self._cache.get(name)
        if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
            return cached[1]

        raw = self._get_raw(name)
        if raw is None:
            return None

        record = ConnectorRecord(
            name=raw["name"],
            connector_type=raw["connector_type"],
            credentials=json.loads(decrypt(raw["credentials_encrypted"])),
            config=json.loads(raw["config_json"]),
            enabled=bool(raw["enabled"]),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
        )
        self._cache[name] = (time.monotonic(), record)
        return record

    def _get_raw(self, name: str) -> Optional[dict[str, Any]]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM connectors WHERE name = ?", (name,)).fetchone()
        return dict(row) if row is not None else None

    def list_connectors(self) -> list[ConnectorRecord]:
        conn = get_connection()
        rows = conn.execute("SELECT name FROM connectors ORDER BY name").fetchall()
        records = [self.get_connector(row["name"]) for row in rows]
        return [r for r in records if r is not None]

    def delete_connector(self, name: str) -> None:
        conn = get_connection()
        cursor = conn.execute("DELETE FROM connectors WHERE name = ?", (name,))
        conn.commit()
        self._cache.pop(name, None)
        if cursor.rowcount == 0:
            raise ConnectorNotFoundError(f"Connector '{name}' existiert nicht.")
        logger.info("Connector '%s' gelöscht.", name)

    def get_credential(self, name: str, field_key: str, default: Optional[str] = None) -> Optional[str]:
        """Bequemer Zugriff für andere Module, z. B.
        `connectors_manager.get_credential("anthropic", "api_key")`."""
        record = self.get_connector(name)
        if record is None or not record.enabled:
            return default
        return record.credentials.get(field_key, default)

    # -- Settings (Key/Value) -----------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        conn = get_connection()
        row = conn.execute("SELECT value_json FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value_json"])

    def get_all_settings(self) -> dict[str, Any]:
        conn = get_connection()
        rows = conn.execute("SELECT key, value_json FROM app_settings").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def set_setting(self, key: str, value: Any) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), _now_iso()),
        )
        conn.commit()

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        for key, value in values.items():
            self.set_setting(key, value)
        return self.get_all_settings()


connectors_manager = ConnectorsManager()
