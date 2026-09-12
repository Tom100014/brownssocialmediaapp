"""
storage.py - Persistenz-Fundament für den Jarvis-Backend-Store.

Stellt bereit:
    * eine gemeinsame, thread-sichere SQLite-Verbindung (WAL-Modus)
    * Verschlüsselung von Secrets-at-Rest via Fernet (symmetrisch, AES128-CBC+HMAC)

Der Master-Key kommt bevorzugt aus der Umgebungsvariable JARVIS_MASTER_KEY
(Produktivbetrieb). Ist er nicht gesetzt, wird beim ersten Start ein neuer
Schlüssel erzeugt und lokal unter data/master.key abgelegt - praktisch für
Entwicklung, aber NICHT für Multi-Server-Deployments geeignet (dort muss der
Key zentral verteilt und über die Umgebung injiziert werden).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import DATA_DIR, settings

logger = logging.getLogger("jarvis.storage")

DB_PATH = DATA_DIR / "jarvis.db"
MASTER_KEY_PATH = DATA_DIR / "master.key"

_connection_lock = threading.Lock()
_connection: sqlite3.Connection | None = None


class DecryptionError(Exception):
    """Ein gespeichertes Secret konnte nicht entschlüsselt werden (falscher Key?)."""


def _load_or_create_master_key() -> bytes:
    if settings.jarvis_master_key is not None:
        return settings.jarvis_master_key.get_secret_value().encode("utf-8")

    if MASTER_KEY_PATH.exists():
        return MASTER_KEY_PATH.read_bytes().strip()

    key = Fernet.generate_key()
    MASTER_KEY_PATH.write_bytes(key)
    MASTER_KEY_PATH.chmod(0o600)
    logger.warning(
        "Kein JARVIS_MASTER_KEY gesetzt - neuer Schlüssel wurde unter %s erzeugt. "
        "Für Produktivbetrieb bitte per Umgebungsvariable fest vorgeben und sichern!",
        MASTER_KEY_PATH,
    )
    return key


_fernet = Fernet(_load_or_create_master_key())


def encrypt(plaintext: str) -> bytes:
    return _fernet.encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet.decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Entschlüsselung fehlgeschlagen - Master-Key stimmt nicht mit dem "
            "verwendeten Schlüssel beim Verschlüsseln überein."
        ) from exc


def get_connection() -> sqlite3.Connection:
    """Liefert eine einzelne, geteilte SQLite-Verbindung (WAL, Foreign Keys an)."""
    global _connection
    with _connection_lock:
        if _connection is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            _connection.execute("PRAGMA journal_mode=WAL;")
            _connection.execute("PRAGMA foreign_keys=ON;")
            _connection.row_factory = sqlite3.Row
            _init_schema(_connection)
        return _connection


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS connectors (
            name                 TEXT PRIMARY KEY,
            connector_type       TEXT NOT NULL,
            credentials_encrypted BLOB NOT NULL,
            config_json          TEXT NOT NULL DEFAULT '{}',
            enabled              INTEGER NOT NULL DEFAULT 1,
            created_at           TEXT NOT NULL,
            updated_at           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key         TEXT PRIMARY KEY,
            value_json  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            done        INTEGER NOT NULL DEFAULT 0,
            due_date    TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS calendar_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT,
            location    TEXT,
            notes       TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            source        TEXT,
            contact_info  TEXT,
            notes         TEXT,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            email       TEXT,
            phone       TEXT,
            notes       TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        """
    )
    conn.commit()
