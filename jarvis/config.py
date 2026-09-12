"""
Zentrale Konfiguration für den Jarvis-Assistenten.

Lädt API-Keys und Laufzeit-Parameter aus Umgebungsvariablen (bzw. einer
lokalen .env-Datei) und validiert sie beim Start. Alle anderen Module
importieren ausschließlich das `settings`-Singleton aus dieser Datei -
niemals direkt `os.environ`.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("jarvis.config")

BASE_DIR = Path(__file__).resolve().parent
CONTEXT_DIR = BASE_DIR / "context"
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """Typisierte, validierte Laufzeitkonfiguration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM-Provider -----------------------------------------------------
    # Optional: Die eigentliche Quelle der Wahrheit für API-Keys ist ab jetzt
    # der verschlüsselte Connector-Store (siehe connectors_manager.py), der
    # zur Laufzeit über die API gepflegt werden kann. Diese Felder dienen nur
    # noch als Fallback für den allerersten Start / lokale Entwicklung.
    anthropic_api_key: SecretStr | None = Field(default=None, description="Fallback-API-Key für Claude (Sonnet)")
    google_api_key: SecretStr | None = Field(default=None, description="Fallback-API-Key für Gemini (Flash)")

    claude_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Modell-ID für komplexe Analysen / Tool-Calling",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Modell-ID für schnelle Routine-Antworten",
    )

    # --- Sprachein-/ausgabe ----------------------------------------------
    deepgram_api_key: SecretStr | None = Field(default=None, description="Fallback-API-Key für Deepgram STT")
    elevenlabs_api_key: SecretStr | None = Field(default=None, description="Fallback-API-Key für ElevenLabs TTS")
    elevenlabs_voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM",
        description="Standard-Voice-ID für die TTS-Ausgabe",
    )

    deepgram_model: str = Field(default="nova-2", description="Deepgram STT-Modell")
    deepgram_language: str = Field(default="de", description="Sprachcode für STT")

    # --- Server / API ------------------------------------------------------
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=8420, ge=1, le=65535)
    api_auth_token: SecretStr = Field(
        ..., description="Shared Secret zur Absicherung von /chat, /webhook, /context"
    )
    cors_allowed_origins: str = Field(
        default="*",
        description=(
            "Kommagetrennte Liste erlaubter Origins für das Web-Frontend (z. B. "
            "'https://jarvis-frontend.vercel.app,http://localhost:3000'). '*' erlaubt alle."
        ),
    )

    # --- Lokaler Client (Laptop-Daemon) -----------------------------------
    local_client_poll_interval_seconds: float = Field(default=3.0, ge=1.0, le=30.0)
    server_base_url: str = Field(default="http://localhost:8420")

    # --- Routing -------------------------------------------------------
    routing_mode: Literal["heuristic", "always_flash", "always_sonnet"] = Field(
        default="heuristic",
        description="Routing-Strategie zwischen Gemini Flash und Claude Sonnet",
    )

    # --- Sonstiges -------------------------------------------------------
    log_level: str = Field(default="INFO")
    weather_api_key: SecretStr | None = Field(
        default=None, description="Fallback-API-Key für Wetterabfragen"
    )

    # --- Connector-Store ----------------------------------------------------
    jarvis_master_key: SecretStr | None = Field(
        default=None,
        description=(
            "Fernet-Schlüssel zur Verschlüsselung gespeicherter Connector-Credentials. "
            "Falls nicht gesetzt, wird beim ersten Start automatisch einer erzeugt und "
            "unter data/master.key persistiert (für Produktivbetrieb: per Env setzen!)."
        ),
    )

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in logging._nameToLevel:  # noqa: SLF001
            raise ValueError(f"Ungültiges log_level: {value}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """Lädt (und cached) die Konfiguration. Bricht beim ersten Zugriff hart ab,
    wenn Pflicht-Keys fehlen - besser ein klarer Startfehler als ein stiller
    Ausfall zur Laufzeit."""
    try:
        settings = Settings()
    except Exception as exc:  # pydantic.ValidationError
        logger.critical("Konfigurationsfehler beim Start von Jarvis: %s", exc)
        raise

    for directory in (CONTEXT_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    return settings


settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
