"""
audio_pipeline.py - Voice-In/Voice-Out-Strecke.

STT: Deepgram (Streaming-Websocket via deepgram-sdk).
TTS: ElevenLabs (HTTP-Streaming).

Beide Provider beziehen ihre API-Keys bevorzugt aus dem Connector-Store
(connectors_manager.py) und fallen auf die statischen `.env`-Werte in
config.py zurück, falls noch kein Connector angelegt wurde.

Vorgeschaltet läuft eine phonetische Autokorrektur für typische
STT-Fehlinterpretationen (z. B. "Java" -> "Jarvis").
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncIterator, Optional

import httpx

# deepgram-sdk 4.x+ ist ein komplett neu generierter Client ohne die klassische
# Live-Websocket-API - deshalb ist deepgram-sdk in requirements.txt auf <4.0 gepinnt.
from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents,
)

from config import settings
from connectors_manager import connectors_manager

logger = logging.getLogger("jarvis.audio_pipeline")

# Phonetische Korrekturtabelle: häufige STT-Fehlinterpretationen -> korrekt.
# Wird als Wortgrenzen-Regex angewendet, case-insensitive.
PHONETIC_CORRECTIONS: dict[str, str] = {
    "java": "jarvis",
    "jarwis": "jarvis",
    "dscharwis": "jarvis",
}

ELEVENLABS_STREAM_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"


class AudioPipelineError(Exception):
    pass


def autocorrect_transcript(raw_text: str) -> str:
    """Wendet die phonetische Glättung auf ein STT-Ergebnis an."""
    corrected = raw_text
    for wrong, right in PHONETIC_CORRECTIONS.items():
        corrected = re.sub(rf"\b{re.escape(wrong)}\b", right, corrected, flags=re.IGNORECASE)
    return corrected


def _resolve_deepgram_key() -> str:
    api_key = connectors_manager.get_credential("deepgram", "api_key") or (
        settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
    )
    if not api_key:
        raise AudioPipelineError(
            "Kein Deepgram-API-Key konfiguriert. Bitte Connector 'deepgram' über POST /connectors anlegen."
        )
    return api_key


def _resolve_elevenlabs_credentials() -> tuple[str, str]:
    api_key = connectors_manager.get_credential("elevenlabs", "api_key") or (
        settings.elevenlabs_api_key.get_secret_value() if settings.elevenlabs_api_key else None
    )
    if not api_key:
        raise AudioPipelineError(
            "Kein ElevenLabs-API-Key konfiguriert. Bitte Connector 'elevenlabs' über POST /connectors anlegen."
        )
    voice_id = connectors_manager.get_credential("elevenlabs", "voice_id") or settings.elevenlabs_voice_id
    return api_key, voice_id


class AudioPipeline:
    """Kapselt STT (Deepgram) und TTS (ElevenLabs)."""

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], *, sample_rate: int = 16000, encoding: str = "linear16"
    ) -> str:
        """Streamt Audio-Chunks an Deepgram und liefert den finalen, autokorrigierten Text.

        Wartet bis Deepgram das Ende der Sprachpause meldet (`is_final=True` auf dem
        letzten Transkript-Event) und aggregiert alle finalen Segmente.
        """
        api_key = _resolve_deepgram_key()
        client = DeepgramClient(api_key)

        final_segments: list[str] = []
        done = asyncio.Event()
        loop = asyncio.get_running_loop()

        connection = client.listen.asyncwebsocket.v("1")

        async def on_message(_, result, **kwargs) -> None:
            try:
                alternatives = result.channel.alternatives
                if not alternatives:
                    return
                transcript = alternatives[0].transcript
                if transcript and result.is_final:
                    final_segments.append(transcript)
                if getattr(result, "speech_final", False):
                    loop.call_soon_threadsafe(done.set)
            except Exception:
                logger.exception("Fehler beim Verarbeiten eines Deepgram-Events")

        async def on_error(_, error, **kwargs) -> None:
            logger.error("Deepgram-Fehler: %s", error)
            loop.call_soon_threadsafe(done.set)

        connection.on(LiveTranscriptionEvents.Transcript, on_message)
        connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model=connectors_manager.get_setting("deepgram_model", settings.deepgram_model),
            language=connectors_manager.get_setting("deepgram_language", settings.deepgram_language),
            encoding=encoding,
            sample_rate=sample_rate,
            smart_format=True,
        )

        started = await connection.start(options)
        if not started:
            raise AudioPipelineError("Deepgram-Verbindung konnte nicht gestartet werden.")

        try:
            async for chunk in audio_chunks:
                await connection.send(chunk)
        finally:
            await connection.finish()

        try:
            await asyncio.wait_for(done.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Deepgram hat kein speech_final-Signal gesendet, nutze bisherige Segmente.")

        raw_text = " ".join(final_segments).strip()
        if not raw_text:
            raise AudioPipelineError("Deepgram lieferte keinen erkennbaren Text.")

        return autocorrect_transcript(raw_text)

    async def synthesize_stream(
        self, text: str, *, voice_id: Optional[str] = None
    ) -> AsyncIterator[bytes]:
        """Streamt TTS-Audio (ElevenLabs, MP3) für den übergebenen Text zurück."""
        if not text or not text.strip():
            raise ValueError("text darf nicht leer sein.")

        api_key, default_voice_id = _resolve_elevenlabs_credentials()
        resolved_voice_id = voice_id or default_voice_id
        url = ELEVENLABS_STREAM_URL.format(voice_id=resolved_voice_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream(
                    "POST",
                    url,
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                    },
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        raise AudioPipelineError(
                            f"ElevenLabs-Fehler ({response.status_code}): {error_body.decode(errors='replace')}"
                        )
                    async for audio_chunk in response.aiter_bytes():
                        if audio_chunk:
                            yield audio_chunk
            except httpx.HTTPError as exc:
                raise AudioPipelineError(f"ElevenLabs nicht erreichbar: {exc}") from exc

    async def synthesize_full(self, text: str, *, voice_id: Optional[str] = None) -> bytes:
        """Bequemlichkeitsmethode für Clients, die keine Chunk-für-Chunk-Wiedergabe
        unterstützen (z. B. ein simples <audio>-Tag im Browser): sammelt den
        gesamten Stream in einem MP3-Byte-Objekt."""
        chunks = [chunk async for chunk in self.synthesize_stream(text, voice_id=voice_id)]
        return b"".join(chunks)

    async def transcribe_file(self, audio_bytes: bytes, *, mime_type: str = "audio/webm") -> str:
        """Transkribiert eine vollständige Audiodatei (z. B. eine im Browser
        aufgenommene Sprachnachricht) über Deepgrams Prerecorded-REST-API -
        einfacher und robuster für Datei-Uploads als der Live-Websocket-Pfad
        in `transcribe_stream`, der für kontinuierliches Mikrofon-Streaming
        gedacht ist."""
        if not audio_bytes:
            raise ValueError("audio_bytes darf nicht leer sein.")

        api_key = _resolve_deepgram_key()
        model = connectors_manager.get_setting("deepgram_model", settings.deepgram_model)
        language = connectors_manager.get_setting("deepgram_language", settings.deepgram_language)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    params={"model": model, "language": language, "smart_format": "true"},
                    headers={"Authorization": f"Token {api_key}", "Content-Type": mime_type},
                    content=audio_bytes,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise AudioPipelineError(
                    f"Deepgram-Fehler ({exc.response.status_code}): {exc.response.text}"
                ) from exc
            except httpx.HTTPError as exc:
                raise AudioPipelineError(f"Deepgram nicht erreichbar: {exc}") from exc

        data = response.json()
        try:
            transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, IndexError) as exc:
            raise AudioPipelineError("Deepgram-Antwort enthielt kein Transkript.") from exc

        if not transcript.strip():
            raise AudioPipelineError("Deepgram lieferte keinen erkennbaren Text.")

        return autocorrect_transcript(transcript.strip())
