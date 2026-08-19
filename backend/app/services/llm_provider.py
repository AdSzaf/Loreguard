import json
from dataclasses import dataclass


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


class LLMProvider:
    """
    Abstract LLM provider (mirrors EmbeddingProvider's pattern, and
    the plan's own LLMProvider sketch in section 15). The rest of
    the app only depends on this interface, so swapping Anthropic
    for OpenAI/local Ollama/etc. later is a one-class change.
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
  "object" (np. "842", "wiosna 842"), a nie całe zdanie.
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

Znane encje w tym świecie (subject/object powinny się do nich \
odnosić, jeśli to możliwe): {known_entities}

Odpowiedz WYŁĄCZNIE poprawnym JSON-em, bez markdown, bez komentarzy: \
lista obiektów z kluczami: subject, predicate, object, confidence, \
source_text. Jeśli nie ma żadnych faktów, zwróć [].
"""


class AnthropicLLMProvider(LLMProvider):
    """
    Real LLM-backed extraction using the Anthropic Messages API.

    Requires ANTHROPIC_API_KEY (see app.core.config.settings). If
    it's not set, the caller should fall back to a provider that
    doesn't need one (or simply not offer LLM extraction) --
    that's handled at the call site (main.py), not here, so this
    class stays simple.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
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
        ).strip()

        raw_text = self._strip_code_fences(raw_text)

        try:
            items = json.loads(raw_text)
        except json.JSONDecodeError:
            return []

        if not isinstance(items, list):
            return []

        facts: list[ExtractedFact] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            try:
                facts.append(
                    ExtractedFact(
                        subject=str(item["subject"]).strip(),
                        predicate=str(item["predicate"]).strip(),
                        object=str(item["object"]).strip(),
                        confidence=float(item.get("confidence", 0.5)),
                        source_text=str(item.get("source_text", "")).strip(),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

        return facts

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            return "\n".join(lines).strip()

        return text
