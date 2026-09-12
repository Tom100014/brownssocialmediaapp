"""
audio_pipeline.py - Voice-In/Voice-Out-Strecke.

STATUS: Gerüst (Schritt 2 der Implementierung). Legt die Schnittstellen für
Deepgram-STT (Streaming) und ElevenLabs-TTS (Streaming) sowie eine
vorgeschaltete Autokorrektur für typische STT-Fehlinterpretationen fest
(z. B. "Java" -> "Jarvis", phonetische Glättung von Namen/Fachbegriffen).
Die konkrete Streaming-Implementierung folgt im nächsten Schritt.
"""

from __future__ import annotations

import logging
import re
from typing import AsyncIterator

logger = logging.getLogger("jarvis.audio_pipeline")

# Phonetische Korrekturtabelle: häufige STT-Fehlinterpretationen -> korrekt.
# Wird als Wortgrenzen-Regex angewendet, case-insensitive.
PHONETIC_CORRECTIONS: dict[str, str] = {
    "java": "jarvis",
    "jarwis": "jarvis",
    "dscharwis": "jarvis",
}


def autocorrect_transcript(raw_text: str) -> str:
    """Wendet die phonetische Glättung auf ein STT-Ergebnis an."""
    corrected = raw_text
    for wrong, right in PHONETIC_CORRECTIONS.items():
        corrected = re.sub(rf"\b{re.escape(wrong)}\b", right, corrected, flags=re.IGNORECASE)
    return corrected


class AudioPipeline:
    """Kapselt STT (Deepgram) und TTS (ElevenLabs)."""

    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes]) -> str:
        """Streamt Audio an Deepgram und liefert den finalen, autokorrigierten Text.

        TODO (nächster Schritt): echte Deepgram-Websocket-Anbindung.
        """
        raise NotImplementedError("Deepgram-Streaming folgt im nächsten Implementierungsschritt.")

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streamt TTS-Audio (ElevenLabs) für den übergebenen Text zurück.

        TODO (nächster Schritt): echte ElevenLabs-Streaming-Anbindung.
        """
        raise NotImplementedError("ElevenLabs-Streaming folgt im nächsten Implementierungsschritt.")
        yield b""  # pragma: no cover - macht die Funktion zum Generator
