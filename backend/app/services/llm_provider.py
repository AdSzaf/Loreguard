import json
import logging
from dataclasses import dataclass


logger = logging.getLogger("loreguard.llm")


@dataclass
class ExtractedFact:
    """
    A candidate fact proposed by an LLM from prose text. Not a
    Fact row yet -- ProseFactExtractor still has to resolve
    `subject`/`object` against known entities before anything gets
    persisted. Nothing from an LLM is trusted as ground truth
    (plan section 14): it only ever produces candidates for the
    deterministic rule engine to compare.
    """

    subject: str
    predicate: str
    object: str
    confidence: float
    source_text: str
    # Only set for facts that express a NUMBER at/about the object
    # (e.g. "age at this event"), not for ordinary facts -- see
    # Fact.object_number's docstring in app/models/fact.py.
    object_number: float | None = None


class LLMProvider:
    """
    Abstract LLM provider (mirrors EmbeddingProvider's pattern, and
    the plan's own LLMProvider sketch in section 15). The rest of
    the app only depends on this interface, so swapping Anthropic
    for Gemini/OpenAI/local Ollama/etc. is a one-class change --
    see get_llm_provider() below for how the app picks one.
    """

    def extract_facts(
        self,
        text: str,
        known_entity_names: list[str],
    ) -> list[ExtractedFact]:
        raise NotImplementedError


EXTRACTION_SYSTEM_PROMPT = """\
Jesteś ekstraktorem faktów dla aplikacji do wykrywania sprzeczności \
w światach fantasy/sci-fi. Z podanego fragmentu tekstu wypisz \
ustrukturyzowane fakty: kto/co, w jakiej relacji, z kim/czym lub jaką \
wartością.

Zasady:
- Wypisuj TYLKO fakty jednoznacznie stwierdzone w tekście. Nie zgaduj, \
  nie wnioskuj pośrednio, nie uzupełniaj wiedzą spoza tekstu.
- predicate pisz krótko, w języku tekstu źródłowego, w formie \
  bezokolicznikowej/rzeczownikowej (np. "zmarł", "urodził się", \
  "był ojcem", nie pełnym zdaniem).
- Jeśli fakt dotyczy daty/roku, umieść samą liczbę/opis daty w polu \
  "object" (np. "842", "wiosna 842"), a nie całe zdanie. Jeśli tekst \
  NIE podaje daty wprost (np. mówi tylko "zginął w tej bitwie" bez \
  roku), NIE zgaduj daty -- w object wpisz nazwę własną rzeczy/miejsca/\
  wydarzenia, którego dotyczy fakt (patrz przykład 2 niżej).
- KLUCZOWE -- polski szyk zdania bywa odwrócony, a zaimki ("w niej", \
  "przez niego", "jego", "która") odnoszą się do czegoś wymienionego \
  wcześniej lub w tytule/kontekście notatki. subject i object MUSZĄ \
  być pełnymi nazwami własnymi -- NIGDY nie wpisuj zaimka ("w niej", \
  "go", "jej") jako object. Jeśli zaimek odnosi się do samego tematu \
  notatki (np. do wydarzenia, o którym jest cały artykuł), użyj jego \
  pełnej nazwy jako object.
- subject i object podawaj jako nazwy własne dokładnie tak, jak \
  występują w tekście (nie tłumacz, nie skracaj, nie zamieniaj na \
  zaimki).
- Pomijaj fakty niepewne, spekulacje, plotki opisane jako plotki -- \
  chyba że tekst wyraźnie mówi "plotka głosi, że X", wtedy wypisz to \
  jako fakt z object opisującym treść plotki i niższym confidence.
- confidence to Twoja pewność, że tekst NAPRAWDĘ to stwierdza (nie \
  pewność że to prawda w świecie): 0.9-1.0 dla wprost napisanego, \
  0.5-0.8 dla domyślnego ale jasnego, poniżej 0.5 dla niepewnego.
- source_text to dokładny cytat (fragment zdania) z tekstu, na \
  podstawie którego wyciągnięto fakt.
- SPECJALNY PRZYPADEK -- wiek w momencie wydarzenia: jeśli tekst \
  mówi, że ktoś miał określony wiek PODCZAS jakiegoś wydarzenia \
  (np. "mając zaledwie 12 lat, objęła dowództwo w bitwie X"), \
  wypisz fakt z predicate="wiek_podczas", object = nazwa własna \
  wydarzenia/bitwy/sytuacji (NIE liczba), oraz DODATKOWO pole \
  "object_number" = sam wiek jako liczba (np. 12). Pole \
  object_number pomijaj całkowicie dla wszystkich innych faktów.

Przykłady:

1. Tekst: "Umarł w 3030 K.E." (notatka o osobie "Serigius I")
   -> {{"subject": "Serigius I", "predicate": "umarł", \
"object": "3030 K.E.", "confidence": 0.95, "source_text": "Umarł w 3030 K.E."}}

2. Tekst: "Zginął w niej Serigius I." (notatka o wydarzeniu \
"Bitwa pod Soizon", zaimek "w niej" odnosi się do tej bitwy -- BRAK \
roku w tym zdaniu, więc object to nazwa bitwy, NIE zgadujemy daty)
   -> {{"subject": "Serigius I", "predicate": "zginął", \
"object": "Bitwa pod Soizon", "confidence": 0.9, \
"source_text": "Zginął w niej Serigius I."}}

3. Tekst: "W 842 roku Elira, mająca zaledwie 12 lat, objęła \
dowództwo nad armią Valdoru w Bitwie pod Arven." (wiek podczas \
wydarzenia -- użyj object_number)
   -> {{"subject": "Elira", "predicate": "wiek_podczas", \
"object": "Bitwa pod Arven", "object_number": 12, \
"confidence": 0.9, "source_text": "mająca zaledwie 12 lat"}}

Znane encje w tym świecie (subject/object powinny się do nich \
odnosić, jeśli to możliwe): {known_entities}

Odpowiedz WYŁĄCZNIE poprawnym JSON-em, bez markdown, bez komentarzy: \
lista obiektów z kluczami: subject, predicate, object, confidence, \
source_text, oraz opcjonalnie object_number (tylko dla faktów typu \
"wiek_podczas", patrz przykład 3). Jeśli nie ma żadnych faktów, zwróć [].
"""


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines).strip()

    return text


def _parse_extracted_facts(raw_text: str) -> list[ExtractedFact]:
    """
    Shared JSON-array-of-facts parser used by every provider, so
    each provider only has to get raw text out of its own SDK's
    response object -- the parsing/validation logic (and its
    quirks: code fences, malformed items, out-of-range confidence)
    lives in exactly one place.

    Logs the raw response whenever parsing yields nothing, so a
    silent "0 facts extracted" in the API response is diagnosable
    from the server console instead of being a total mystery.
    """

    original = raw_text
    raw_text = _strip_code_fences(raw_text.strip())

    if not raw_text:
        logger.warning("LLM returned an empty response.")
        return []

    try:
        items = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(
            "LLM response was not valid JSON, dropping it. "
            "Raw response: %r",
            original[:2000],
        )
        return []

    if not isinstance(items, list):
        logger.warning(
            "LLM response was valid JSON but not a list, dropping it. "
            "Raw response: %r",
            original[:2000],
        )
        return []

    facts: list[ExtractedFact] = []
    dropped = 0

    for item in items:
        if not isinstance(item, dict):
            dropped += 1
            continue

        try:
            object_number_raw = item.get("object_number")

            facts.append(
                ExtractedFact(
                    subject=str(item["subject"]).strip(),
                    predicate=str(item["predicate"]).strip(),
                    object=str(item["object"]).strip(),
                    confidence=float(item.get("confidence", 0.5)),
                    source_text=str(item.get("source_text", "")).strip(),
                    object_number=(
                        float(object_number_raw)
                        if object_number_raw is not None
                        else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue

    if dropped:
        logger.warning(
            "Dropped %d malformed item(s) from LLM response.", dropped
        )

    if not facts and items:
        logger.info(
            "LLM returned a JSON list but every item was malformed. "
            "Raw response: %r",
            original[:2000],
        )

    return facts


class AnthropicLLMProvider(LLMProvider):
    """
    Real LLM-backed extraction using the Anthropic Messages API.

    Requires settings.anthropic_api_key. Construction itself never
    touches the network, so it's safe to instantiate speculatively
    (see get_llm_provider()).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5",
    ):
        # Imported lazily so the `anthropic` package is only
        # required when this provider is actually used.
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def extract_facts(
        self,
        text: str,
        known_entity_names: list[str],
    ) -> list[ExtractedFact]:
        text = text.strip()

        if not text:
            return []

        system_prompt = EXTRACTION_SYSTEM_PROMPT.format(
            known_entities=", ".join(known_entity_names) or "(brak)",
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": text}],
        )

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        return _parse_extracted_facts(raw_text)


class GeminiLLMProvider(LLMProvider):
    """
    Real LLM-backed extraction using Google's Gemini API (the
    `google-genai` SDK). Requires settings.gemini_api_key.

    Uses Gemini's native JSON response mode (response_mime_type=
    "application/json") instead of asking nicely in the prompt --
    more reliable than Anthropic's plain-text-that-happens-to-be-
    JSON approach, but both end up parsed by the same
    _parse_extracted_facts() so behavior stays consistent either
    way.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
    ):
        # Imported lazily so the `google-genai` package is only
        # required when this provider is actually used.
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def extract_facts(
        self,
        text: str,
        known_entity_names: list[str],
    ) -> list[ExtractedFact]:
        text = text.strip()

        if not text:
            return []

        from google.genai import types

        system_prompt = EXTRACTION_SYSTEM_PROMPT.format(
            known_entities=", ".join(known_entity_names) or "(brak)",
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )

        return _parse_extracted_facts(response.text or "")


def get_llm_provider(settings) -> LLMProvider | None:
    """
    Picks whichever LLM provider is actually configured, so the
    rest of the app never has to know or care which one is in use.

    Selection:
      - settings.llm_provider == "anthropic" -> Anthropic, or None
        if its key isn't set (explicit choice, no silent fallback)
      - settings.llm_provider == "gemini" -> Gemini, or None if its
        key isn't set
      - settings.llm_provider == "auto" (default) -> Gemini if its
        key is set (it's the free option), else Anthropic if its
        key is set, else None
    """

    choice = (settings.llm_provider or "auto").strip().lower()

    if choice == "anthropic":
        if not settings.anthropic_api_key:
            return None
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    if choice == "gemini":
        if not settings.gemini_api_key:
            return None
        return GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    # auto
    if settings.gemini_api_key:
        return GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    if settings.anthropic_api_key:
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    return None

