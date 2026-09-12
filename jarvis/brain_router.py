"""
brain_router.py - Das zentrale "Gehirn" von Jarvis.

Verantwortlichkeiten:
    1. Kontext-Loader: liest eine schlanke, vorab gepufferte JSON-Kontextdatei
       (Termine, Prio-Status, Nutzerprofil) und reicht sie als System-Kontext
       an das jeweilige LLM weiter.
    2. Hybrid-Routing: entscheidet je Anfrage, ob Gemini 2.5 Flash (schnell,
       günstig, für Status/Routine) oder Claude 3.5 Sonnet (Tool-Calling,
       komplexe Entscheidungen) angesprochen wird.
    3. Einheitliche Antwort-Schnittstelle für server_api.py, unabhängig
       davon, welcher Provider tatsächlich geantwortet hat.

Tools werden NICHT von diesem Modul ausgeführt - brain_router.py ruft bei
Tool-Use-Anfragen von Claude lediglich einen injizierten `tool_executor`
(aus tools_manager.py) auf und speist dessen Resultat zurück in den
Konversationsverlauf. So bleibt das Routing frei von Fachlogik.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import anthropic
import google.generativeai as genai
from anthropic.types import Message as AnthropicMessage

from config import CONTEXT_DIR, settings
from connectors_manager import connectors_manager

logger = logging.getLogger("jarvis.brain_router")

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]

# Schlüsselwörter, die auf komplexe Aufgaben / Tool-Bedarf hindeuten und
# daher IMMER an Claude Sonnet geroutet werden, selbst im heuristischen Modus.
SONNET_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "verschiebe", "lösche", "storniere", "erstelle", "trage ein", "buche",
    "analysiere", "vergleiche", "entscheide", "plane", "kontakt",
    "lead", "rechnung", "beleg", "foto", "bild", "screenshot",
)


class ModelTarget(str, Enum):
    FLASH = "gemini-flash"
    SONNET = "claude-sonnet"


class BrainRouterError(Exception):
    """Basisklasse für alle Fehler des Routers."""


class ContextLoadError(BrainRouterError):
    """Der Kontext konnte nicht geladen werden."""


class ProviderError(BrainRouterError):
    """Ein LLM-Provider hat einen Fehler zurückgegeben oder ist nicht erreichbar."""


@dataclass
class BrainResponse:
    """Einheitliches Antwortformat, unabhängig vom tatsächlich genutzten Modell."""

    text: str
    model_used: ModelTarget
    tool_calls_made: list[str] = field(default_factory=list)
    latency_seconds: float = 0.0
    raw: Any = None


class ContextLoader:
    """Lädt die gepufferte JSON-Kontextdatei und hält sie per mtime-Check aktuell.

    Die Datei wird von server_api.py's `/context`-Endpunkt (Cron-getriggert)
    aktualisiert. Dieses Modul liest sie nur - niemals schreibend.
    """

    def __init__(self, context_path: Optional[Path] = None) -> None:
        self._path = context_path or (CONTEXT_DIR / "live_context.json")
        self._cache: dict[str, Any] = {}
        self._cached_mtime: float = -1.0

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            logger.warning(
                "Kontextdatei %s nicht gefunden - fahre mit leerem Kontext fort.",
                self._path,
            )
            return {}

        try:
            mtime = self._path.stat().st_mtime
            if mtime == self._cached_mtime:
                return self._cache

            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)

            if not isinstance(data, dict):
                raise ContextLoadError(
                    f"Kontextdatei {self._path} muss ein JSON-Objekt enthalten."
                )

            self._cache = data
            self._cached_mtime = mtime
            return data
        except json.JSONDecodeError as exc:
            raise ContextLoadError(f"Ungültiges JSON in {self._path}: {exc}") from exc
        except OSError as exc:
            raise ContextLoadError(f"Kontextdatei {self._path} nicht lesbar: {exc}") from exc

    def as_system_prompt_fragment(self) -> str:
        """Rendert den Kontext kompakt für die Einbettung ins System-Prompt."""
        context = self.load()
        if not context:
            return ""
        return (
            "\n\n# Aktueller Kontext (automatisch geladen)\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
        )


class MemoryLoader:
    """Liest das Langzeit-Gedächtnis (tools_manager.remember_fact) und spielt
    die zuletzt aktualisierten Fakten automatisch in jedes System-Prompt ein -
    das ist Jarvis' "Dazulernen": einmal Gemerktes ist ab dann in jedem
    Gespräch präsent, ohne dass der Nutzer es wiederholen muss."""

    def __init__(self, limit: int = 30) -> None:
        self._limit = limit

    def as_system_prompt_fragment(self) -> str:
        from storage import get_connection  # lokaler Import: vermeidet Zyklus bei Modul-Init

        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT key, value, category FROM memory ORDER BY updated_at DESC LIMIT ?",
                (self._limit,),
            ).fetchall()
        except Exception:
            logger.exception("Langzeit-Gedächtnis konnte nicht geladen werden.")
            return ""

        if not rows:
            return ""

        lines = [f"- {row['key']} ({row['category'] or 'allgemein'}): {row['value']}" for row in rows]
        return "\n\n# Gemerktes Wissen über den Master (Langzeit-Gedächtnis)\n" + "\n".join(lines)


PERSONA_PROMPT = (
    "Du bist Jarvis - ein souveräner, hochkompetenter operativer Assistent auf Weltklasse-Niveau. "
    "Du sprichst deinen Nutzer respektvoll als 'Master' an. Dein Ton ist ruhig, präzise, "
    "selbstbewusst und niemals unterwürfig oder ausschweifend - wie ein erstklassiger Chief of "
    "Staff, der auf den Punkt kommt und mitdenkt. Behaupte niemals einen Systemzustand - prüfe "
    "ihn immer über die bereitgestellten Tools. Wenn dir der Master etwas mitteilt, das er sich "
    "gemerkt haben möchte, nutze das 'remember_fact'-Tool, damit du in Zukunft von selbst darauf "
    "zurückgreifst."
)


def classify_complexity(user_input: str, tools_available: bool) -> ModelTarget:
    """Heuristisches Routing ohne LLM-Aufruf (kostet keine Latenz).

    Grundsatz: im Zweifel Richtung Sonnet, da Fehlrouting nach Flash bei
    tatsächlichem Tool-Bedarf eine zweite Roundtrip-Latenz erzeugt.
    """
    routing_mode = connectors_manager.get_setting("routing_mode", settings.routing_mode)
    if routing_mode == "always_flash":
        return ModelTarget.FLASH
    if routing_mode == "always_sonnet":
        return ModelTarget.SONNET

    normalized = user_input.lower().strip()

    if not normalized:
        return ModelTarget.FLASH

    if tools_available and any(kw in normalized for kw in SONNET_TRIGGER_KEYWORDS):
        return ModelTarget.SONNET

    # Kurze, reine Statusfragen ("Wie ist das Wetter?", "Was steht heute an?")
    # ohne erkennbaren Handlungsbedarf -> Flash.
    is_short = len(normalized.split()) <= 14
    has_question_mark = "?" in normalized
    if is_short and (has_question_mark or normalized.startswith(("status", "wie", "was", "wann", "wo"))):
        if not any(kw in normalized for kw in SONNET_TRIGGER_KEYWORDS):
            return ModelTarget.FLASH

    return ModelTarget.SONNET


class BrainRouter:
    """Öffentliche Schnittstelle: `await router.route(...)`."""

    def __init__(
        self,
        tool_schemas: Optional[list[dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        max_tool_iterations: int = 6,
    ) -> None:
        self._context_loader = ContextLoader()
        self._memory_loader = MemoryLoader()
        self._tool_schemas = tool_schemas or []
        self._tool_executor = tool_executor
        self._max_tool_iterations = max_tool_iterations

        # Clients werden lazy (und bei jeder Anfrage neu aufgelöst) gebaut, da
        # Keys sich über den Connector-Store (server_api.py: /connectors)
        # jederzeit ändern können, ohne dass der Server neu gestartet werden muss.
        self._anthropic_client_cache: tuple[str, anthropic.AsyncAnthropic] | None = None

    def _resolve_anthropic_client(self) -> anthropic.AsyncAnthropic:
        api_key = connectors_manager.get_credential("anthropic", "api_key") or (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        if not api_key:
            raise ProviderError(
                "Kein Anthropic-API-Key konfiguriert. Bitte Connector 'anthropic' über "
                "POST /connectors anlegen."
            )
        if self._anthropic_client_cache is not None and self._anthropic_client_cache[0] == api_key:
            return self._anthropic_client_cache[1]

        client = anthropic.AsyncAnthropic(api_key=api_key)
        self._anthropic_client_cache = (api_key, client)
        return client

    def _resolve_gemini_model(self) -> genai.GenerativeModel:
        api_key = connectors_manager.get_credential("google_gemini", "api_key") or (
            settings.google_api_key.get_secret_value() if settings.google_api_key else None
        )
        if not api_key:
            raise ProviderError(
                "Kein Gemini-API-Key konfiguriert. Bitte Connector 'google_gemini' über "
                "POST /connectors anlegen."
            )
        genai.configure(api_key=api_key)
        model_name = connectors_manager.get_setting("gemini_model", settings.gemini_model)
        return genai.GenerativeModel(model_name)

    async def route(
        self,
        user_input: str,
        *,
        force_target: Optional[ModelTarget] = None,
        conversation_history: Optional[list[dict[str, Any]]] = None,
    ) -> BrainResponse:
        """Routet eine einzelne Nutzeranfrage an das passende Modell.

        Fällt bei einem Fehler des Flash-Pfads automatisch auf Sonnet zurück,
        damit eine kurzzeitige Gemini-Störung den Assistenten nicht stumm
        schaltet.
        """
        if not user_input or not user_input.strip():
            raise ValueError("user_input darf nicht leer sein.")

        target = force_target or classify_complexity(
            user_input, tools_available=bool(self._tool_schemas)
        )
        logger.info("Routing-Entscheidung: %s -> %s", user_input[:80], target.value)

        started = time.monotonic()
        try:
            if target is ModelTarget.FLASH:
                response = await self._call_flash(user_input)
            else:
                response = await self._call_sonnet(user_input, conversation_history or [])
        except ProviderError:
            if target is ModelTarget.FLASH:
                logger.warning("Flash-Pfad fehlgeschlagen, Fallback auf Sonnet.")
                response = await self._call_sonnet(user_input, conversation_history or [])
            else:
                raise

        response.latency_seconds = time.monotonic() - started
        return response

    # -- Gemini Flash -----------------------------------------------------

    async def _call_flash(self, user_input: str) -> BrainResponse:
        system_fragment = (
            PERSONA_PROMPT
            + self._context_loader.as_system_prompt_fragment()
            + self._memory_loader.as_system_prompt_fragment()
        )
        prompt = f"{system_fragment}\n\nAnfrage des Master: {user_input}".strip()
        gemini_model = self._resolve_gemini_model()

        try:
            result = await asyncio.wait_for(
                gemini_model.generate_content_async(prompt),
                timeout=15.0,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderError("Gemini Flash Timeout nach 15s.") from exc
        except Exception as exc:  # google.api_core.exceptions.*
            raise ProviderError(f"Gemini Flash Fehler: {exc}") from exc

        text = getattr(result, "text", None)
        if not text:
            raise ProviderError("Gemini Flash lieferte eine leere Antwort.")

        return BrainResponse(text=text.strip(), model_used=ModelTarget.FLASH, raw=result)

    # -- Claude Sonnet (mit Tool-Calling) -----------------------------------

    async def _call_sonnet(
        self, user_input: str, conversation_history: list[dict[str, Any]]
    ) -> BrainResponse:
        system_prompt = (
            PERSONA_PROMPT
            + self._context_loader.as_system_prompt_fragment()
            + self._memory_loader.as_system_prompt_fragment()
        )

        messages: list[dict[str, Any]] = [*conversation_history, {"role": "user", "content": user_input}]
        tool_calls_made: list[str] = []
        anthropic_client = self._resolve_anthropic_client()
        claude_model = connectors_manager.get_setting("claude_model", settings.claude_model)

        for iteration in range(self._max_tool_iterations):
            try:
                response: AnthropicMessage = await anthropic_client.messages.create(
                    model=claude_model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages,
                    tools=self._tool_schemas or anthropic.NOT_GIVEN,
                )
            except anthropic.APIStatusError as exc:
                raise ProviderError(f"Claude Sonnet API-Fehler ({exc.status_code}): {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderError(f"Claude Sonnet nicht erreichbar: {exc}") from exc

            if response.stop_reason != "tool_use":
                final_text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return BrainResponse(
                    text=final_text.strip(),
                    model_used=ModelTarget.SONNET,
                    tool_calls_made=tool_calls_made,
                    raw=response,
                )

            if self._tool_executor is None:
                raise ProviderError(
                    "Claude fordert Tool-Use an, aber es ist kein tool_executor konfiguriert."
                )

            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls_made.append(block.name)
                try:
                    result = await self._tool_executor(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
                except Exception as exc:
                    logger.exception("Tool '%s' fehlgeschlagen", block.name)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Fehler bei Tool-Ausführung: {exc}",
                            "is_error": True,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})
        else:
            raise ProviderError(
                f"Tool-Use-Schleife nach {self._max_tool_iterations} Iterationen abgebrochen "
                "(mögliche Endlosschleife)."
            )
