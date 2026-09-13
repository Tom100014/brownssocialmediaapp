"""
brain_router.py - Das zentrale "Gehirn" von Jarvis.

Verantwortlichkeiten:
    1. Kontext-Loader: liest eine schlanke, vorab gepufferte JSON-Kontextdatei
       (Termine, Prio-Status, Nutzerprofil) und reicht sie als System-Kontext
       an das jeweilige LLM weiter.
    2. Hybrid-Routing: entscheidet je Anfrage, ob ein schnelles Modell
       (Standard: Gemini 2.5 Flash, für Status/Routine) oder ein starkes
       Modell mit Tool-Calling (Standard: Claude 3.5 Sonnet, für komplexe
       Entscheidungen) angesprochen wird.
    3. Einheitliche Antwort-Schnittstelle für server_api.py, unabhängig
       davon, welches Modell tatsächlich geantwortet hat.

Beide Modelle werden über OpenRouter (https://openrouter.ai) angesprochen -
ein einziger API-Key deckt beliebige Modell-Anbieter im OpenAI-kompatiblen
Format ab, statt separate Anthropic-/Google-SDKs und -Keys zu pflegen.

Tools werden NICHT von diesem Modul ausgeführt - brain_router.py ruft bei
Tool-Calls lediglich einen injizierten `tool_executor` (aus tools_manager.py)
auf und speist dessen Resultat zurück in den Konversationsverlauf. So bleibt
das Routing frei von Fachlogik.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import openai

from config import CONTEXT_DIR, settings
from connectors_manager import connectors_manager

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

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

        # Der Client wird lazy (und bei jeder Anfrage neu aufgelöst) gebaut, da
        # der Key sich über den Connector-Store (server_api.py: /connectors)
        # jederzeit ändern kann, ohne dass der Server neu gestartet werden muss.
        self._openrouter_client_cache: tuple[str, openai.AsyncOpenAI] | None = None

    def _resolve_openrouter_client(self) -> openai.AsyncOpenAI:
        api_key = connectors_manager.get_credential("openrouter", "api_key") or (
            settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else None
        )
        if not api_key:
            raise ProviderError(
                "Kein OpenRouter-API-Key konfiguriert. Bitte Connector 'openrouter' über "
                "POST /connectors anlegen."
            )
        if self._openrouter_client_cache is not None and self._openrouter_client_cache[0] == api_key:
            return self._openrouter_client_cache[1]

        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/tom100014/brownssocialmediaapp",
                "X-Title": "Jarvis",
            },
        )
        self._openrouter_client_cache = (api_key, client)
        return client

    def _resolve_flash_model(self) -> str:
        return connectors_manager.get_credential("openrouter", "flash_model") or connectors_manager.get_setting(
            "gemini_model", settings.gemini_model
        )

    def _resolve_sonnet_model(self) -> str:
        return connectors_manager.get_credential("openrouter", "sonnet_model") or connectors_manager.get_setting(
            "claude_model", settings.claude_model
        )

    @staticmethod
    def _to_openai_tools(tool_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Konvertiert Anthropic-Tool-Schemas (name/description/input_schema) in das
        OpenAI-Function-Calling-Format, das OpenRouter für alle Modelle einheitlich
        erwartet."""
        return [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description", ""),
                    "parameters": schema.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for schema in tool_schemas
        ]

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

    # -- Flash-Pfad (schnelles Modell, kein Tool-Calling) --------------------

    async def _call_flash(self, user_input: str) -> BrainResponse:
        system_fragment = (
            PERSONA_PROMPT
            + self._context_loader.as_system_prompt_fragment()
            + self._memory_loader.as_system_prompt_fragment()
        )
        client = self._resolve_openrouter_client()
        model = self._resolve_flash_model()

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_fragment},
                    {"role": "user", "content": user_input},
                ],
                timeout=15.0,
            )
        except openai.APIStatusError as exc:
            raise ProviderError(f"OpenRouter-Fehler ({exc.status_code}, {model}): {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"OpenRouter nicht erreichbar: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise ProviderError(f"OpenRouter-Timeout ({model}) nach 15s.") from exc

        text = response.choices[0].message.content if response.choices else None
        if not text:
            raise ProviderError(f"Flash-Modell ({model}) lieferte eine leere Antwort.")

        return BrainResponse(text=text.strip(), model_used=ModelTarget.FLASH, raw=response)

    # -- Sonnet-Pfad (starkes Modell mit Tool-Calling) -----------------------

    async def _call_sonnet(
        self, user_input: str, conversation_history: list[dict[str, Any]]
    ) -> BrainResponse:
        system_prompt = (
            PERSONA_PROMPT
            + self._context_loader.as_system_prompt_fragment()
            + self._memory_loader.as_system_prompt_fragment()
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": user_input},
        ]
        tool_calls_made: list[str] = []
        client = self._resolve_openrouter_client()
        model = self._resolve_sonnet_model()
        openai_tools = self._to_openai_tools(self._tool_schemas) if self._tool_schemas else None

        for _ in range(self._max_tool_iterations):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=openai_tools,
                    max_tokens=1024,
                )
            except openai.APIStatusError as exc:
                raise ProviderError(f"OpenRouter-Fehler ({exc.status_code}, {model}): {exc.message}") from exc
            except openai.APIConnectionError as exc:
                raise ProviderError(f"OpenRouter nicht erreichbar: {exc}") from exc

            choice = response.choices[0]
            message = choice.message

            if not message.tool_calls:
                return BrainResponse(
                    text=(message.content or "").strip(),
                    model_used=ModelTarget.SONNET,
                    tool_calls_made=tool_calls_made,
                    raw=response,
                )

            if self._tool_executor is None:
                raise ProviderError(
                    f"{model} fordert einen Tool-Call an, aber es ist kein tool_executor konfiguriert."
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            for tool_call in message.tool_calls:
                tool_calls_made.append(tool_call.function.name)
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    result = await self._tool_executor(tool_call.function.name, arguments)
                    content = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.exception("Tool '%s' fehlgeschlagen", tool_call.function.name)
                    content = f"Fehler bei Tool-Ausführung: {exc}"

                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": content})
        else:
            raise ProviderError(
                f"Tool-Call-Schleife nach {self._max_tool_iterations} Iterationen abgebrochen "
                "(mögliche Endlosschleife)."
            )
