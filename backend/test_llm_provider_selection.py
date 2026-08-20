"""
Tests get_llm_provider() (which provider gets picked based on
config) and _parse_extracted_facts() (shared JSON parsing). Does
NOT make any real network calls -- constructing an SDK client just
stores config, it doesn't validate the key over the network, so
this is safe to run with fake keys and no internet access.

Run with:
    python test_llm_provider_selection.py
"""

from types import SimpleNamespace

from app.services.llm_provider import (
    AnthropicLLMProvider,
    GeminiLLMProvider,
    _parse_extracted_facts,
    get_llm_provider,
)


passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed

    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


def fake_settings(**overrides):
    base = {
        "llm_provider": "auto",
        "anthropic_api_key": None,
        "anthropic_model": "claude-haiku-4-5",
        "gemini_api_key": None,
        "gemini_model": "gemini-2.5-flash-lite",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


print("=" * 60)
print("CASE 1: auto mode picks whichever key is set")
print("=" * 60)

provider = get_llm_provider(fake_settings())
check("no keys set -> None", provider is None)

provider = get_llm_provider(fake_settings(anthropic_api_key="sk-ant-fake"))
check(
    "only Anthropic key set -> AnthropicLLMProvider",
    isinstance(provider, AnthropicLLMProvider),
)

provider = get_llm_provider(fake_settings(gemini_api_key="fake-gemini-key"))
check(
    "only Gemini key set -> GeminiLLMProvider",
    isinstance(provider, GeminiLLMProvider),
)

provider = get_llm_provider(
    fake_settings(
        anthropic_api_key="sk-ant-fake",
        gemini_api_key="fake-gemini-key",
    )
)
check(
    "both keys set, auto mode -> Gemini wins (it's free)",
    isinstance(provider, GeminiLLMProvider),
)

print()
print("=" * 60)
print("CASE 2: explicit llm_provider overrides auto-detection")
print("=" * 60)

provider = get_llm_provider(
    fake_settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-fake",
        gemini_api_key="fake-gemini-key",
    )
)
check(
    "explicit 'anthropic' wins even though Gemini key is also set",
    isinstance(provider, AnthropicLLMProvider),
)

provider = get_llm_provider(
    fake_settings(
        llm_provider="anthropic",
        gemini_api_key="fake-gemini-key",
    )
)
check(
    "explicit 'anthropic' with no anthropic key -> None (no silent fallback)",
    provider is None,
)

print()
print("=" * 60)
print("CASE 3: provider model comes from settings, not hardcoded")
print("=" * 60)

provider = get_llm_provider(
    fake_settings(
        anthropic_api_key="sk-ant-fake",
        anthropic_model="claude-sonnet-5",
    )
)
check(
    "custom anthropic_model is respected",
    provider.model == "claude-sonnet-5",
)

provider = get_llm_provider(
    fake_settings(
        gemini_api_key="fake-gemini-key",
        gemini_model="gemini-3-flash",
    )
)
check(
    "custom gemini_model is respected",
    provider.model == "gemini-3-flash",
)

print()
print("=" * 60)
print("CASE 4: shared JSON parsing (both providers use this)")
print("=" * 60)

facts = _parse_extracted_facts(
    '[{"subject": "Aldren II", "predicate": "zmarł", '
    '"object": "842", "confidence": 0.95, "source_text": "..."}]'
)
check("parses a clean JSON array", len(facts) == 1)
check("fields map correctly", facts[0].subject == "Aldren II" and facts[0].object == "842")

facts = _parse_extracted_facts(
    '```json\n[{"subject": "X", "predicate": "y", "object": "z", '
    '"confidence": 0.5, "source_text": "..."}]\n```'
)
check("strips markdown code fences", len(facts) == 1)

facts = _parse_extracted_facts("not json at all")
check("garbage input returns empty list, not an exception", facts == [])

facts = _parse_extracted_facts(
    '[{"subject": "X", "predicate": "y"}, '
    '{"subject": "Z", "predicate": "w", "object": "v"}]'
)
check(
    "item missing required 'object' key is dropped, valid one kept",
    len(facts) == 1 and facts[0].subject == "Z",
)

facts = _parse_extracted_facts("[]")
check("empty array is valid (no facts found)", facts == [])

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
