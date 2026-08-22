from pathlib import Path

import yaml

from app.models import EntityType


# Built-in defaults covering common Polish and English vocabulary.
# These are just a starting point -- anything in the vault's own
# .loreguard/schema.yaml is merged on top and takes precedence.
# A tag or field name that isn't recognised is simply ignored, it
# never causes an error or forces a shape onto a note.

DEFAULT_ENTITY_TYPE_TAGS: dict[str, EntityType] = {
    "postać": EntityType.PERSON,
    "postac": EntityType.PERSON,
    "person": EntityType.PERSON,
    "character": EntityType.PERSON,
    "bóg": EntityType.DEITY,
    "bog": EntityType.DEITY,
    "bóstwo": EntityType.DEITY,
    "bostwo": EntityType.DEITY,
    "deity": EntityType.DEITY,
    "god": EntityType.DEITY,
    "kraj": EntityType.COUNTRY,
    "państwo": EntityType.COUNTRY,
    "panstwo": EntityType.COUNTRY,
    "country": EntityType.COUNTRY,
    "nation": EntityType.COUNTRY,
    "region": EntityType.REGION,
    "kraina": EntityType.REGION,
    "miejsce": EntityType.PLACE,
    "lokacja": EntityType.PLACE,
    "place": EntityType.PLACE,
    "location": EntityType.PLACE,
    "rasa": EntityType.RACE,
    "race": EntityType.RACE,
    "organizacja": EntityType.ORGANIZATION,
    "organization": EntityType.ORGANIZATION,
    "frakcja": EntityType.FACTION,
    "faction": EntityType.FACTION,
    "przedmiot": EntityType.ITEM,
    "artefakt": EntityType.ITEM,
    "item": EntityType.ITEM,
    "artifact": EntityType.ITEM,
    "wydarzenie": EntityType.EVENT,
    "bitwa": EntityType.EVENT,
    "wojna": EntityType.EVENT,
    "event": EntityType.EVENT,
    "battle": EntityType.EVENT,
    "war": EntityType.EVENT,
    "koncepcja": EntityType.CONCEPT,
    "concept": EntityType.CONCEPT,
}

DEFAULT_FIELD_ALIASES: dict[str, list[str]] = {
    "date": ["date", "data", "kiedy", "rok", "data_wydarzenia"],
    "date_start": ["date_start", "data_od", "od"],
    "date_end": ["date_end", "data_do", "do"],
    "location": ["location", "lokalizacja", "miejsce", "gdzie"],
    "outcome": [
        "outcome", "wynik", "rezultat", "zakonczenie", "zakończenie",
    ],
    "description": ["description", "opis"],
    "participants": ["participants", "uczestnicy", "strony"],
}

# Groups of relationship predicates that are mutually exclusive:
# if two facts link the same (subject, object) pair using
# predicates from two DIFFERENT groups, that's a contradiction
# (e.g. "córka" in one group, "siostra" in another -> can't both
# be true about the same two entities). Predicates within the same
# group are treated as compatible/synonymous, not conflicting.
DEFAULT_RELATIONSHIP_GROUPS: list[list[str]] = [
    ["ojciec", "matka", "rodzic", "father", "mother", "parent"],
    ["syn", "córka", "corka", "dziecko", "son", "daughter", "child"],
    [
        "brat", "siostra", "rodzeństwo", "rodzenstwo",
        "brother", "sister", "sibling",
    ],
    [
        "mąż", "maz", "żona", "zona", "małżonek", "malzonek",
        "husband", "wife", "spouse",
    ],
]

# Different words for the same underlying concept, so facts using
# different vocabulary for "died" (say) are still compared against
# each other by ExclusiveFactRule instead of silently passing each
# other by because the raw predicate strings don't match.
# Everything in a group is treated as equivalent -- NOT mutually
# exclusive (that's DEFAULT_RELATIONSHIP_GROUPS, a different thing).
DEFAULT_PREDICATE_SYNONYMS: dict[str, str] = {
    "zginął": "died", "zginęła": "died", "zmarł": "died",
    "zmarła": "died", "umarł": "died", "umarła": "died",
    "died": "died", "death": "died", "dies": "died",
    "urodził się": "born", "urodziła się": "born", "narodziny": "born",
    "born": "born", "birth": "born",

    # Age stated at a specific event (see EXTRACTION_SYSTEM_PROMPT's
    # "wiek_podczas" example and AgeImpossibilityRule).
    "wiek_podczas": "age_at_event", "wiek_w_trakcie": "age_at_event",
    "age_at_event": "age_at_event", "age_during": "age_at_event",
}

# Named participant roles beyond the generic "participants" bucket.
# role -> list of frontmatter field names that carry that role.
DEFAULT_ROLE_FIELDS: dict[str, list[str]] = {
    "commander": [
        "commander", "commanders", "dowódca", "dowodca",
        "dowódcy", "dowodcy",
    ],
}


class VaultSchema:
    """
    Vault-specific vocabulary for classifying entities and reading
    event-like frontmatter, loaded from `.loreguard/schema.yaml` in
    the vault root and merged on top of the built-in PL/EN defaults.

    Nothing here is mandatory. A note with no recognised tag simply
    isn't classified (entity_type stays OTHER); a note with no
    recognised date-like field simply isn't treated as an Event.
    The app never guesses a field's meaning -- it only recognises
    vocabulary that's either built in or that the user declared.

    Example `.loreguard/schema.yaml`:

        entity_types:
          mag: person
          artefakt_legendarny: item

        field_aliases:
          date: [rok_wydarzenia]
          location: [lokacja_glowna]

        roles:
          victim: [ofiara, zginął]

        event_tags:
          - starcie
    """

    def __init__(self, vault_path: Path | str):
        vault_path = Path(vault_path)

        self._entity_type_tags = dict(DEFAULT_ENTITY_TYPE_TAGS)

        self._field_aliases: dict[str, list[str]] = {
            concept: list(aliases)
            for concept, aliases in DEFAULT_FIELD_ALIASES.items()
        }

        self._role_fields: dict[str, list[str]] = {
            role: list(aliases)
            for role, aliases in DEFAULT_ROLE_FIELDS.items()
        }

        self._relationship_groups: list[set[str]] = [
            set(group) for group in DEFAULT_RELATIONSHIP_GROUPS
        ]

        self._predicate_synonyms: dict[str, str] = {
            term.casefold(): canonical
            for term, canonical in DEFAULT_PREDICATE_SYNONYMS.items()
        }

        self._event_tags: set[str] = {
            tag
            for tag, entity_type in DEFAULT_ENTITY_TYPE_TAGS.items()
            if entity_type == EntityType.EVENT
        }

        self._load_overrides(vault_path)

    def _load_overrides(self, vault_path: Path) -> None:
        schema_path = vault_path / ".loreguard" / "schema.yaml"

        if not schema_path.exists():
            return

        with open(schema_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        for tag, type_name in (data.get("entity_types") or {}).items():
            try:
                resolved = EntityType(str(type_name).strip().lower())
            except ValueError:
                continue

            self._entity_type_tags[str(tag).strip().casefold()] = resolved

            if resolved == EntityType.EVENT:
                self._event_tags.add(str(tag).strip().casefold())

        for concept, aliases in (data.get("field_aliases") or {}).items():
            bucket = self._field_aliases.setdefault(concept, [])
            bucket.extend(
                str(alias).strip().casefold() for alias in aliases
            )

        for role, aliases in (data.get("roles") or {}).items():
            bucket = self._role_fields.setdefault(role, [])
            bucket.extend(
                str(alias).strip().casefold() for alias in aliases
            )

        for tag in (data.get("event_tags") or []):
            self._event_tags.add(str(tag).strip().casefold())

        for canonical, terms in (data.get("predicate_synonyms") or {}).items():
            for term in terms:
                self._predicate_synonyms[str(term).strip().casefold()] = (
                    str(canonical).strip().casefold()
                )

        for group in (data.get("relationship_groups") or []):
            self._relationship_groups.append(
                {str(item).strip().casefold() for item in group}
            )

    def resolve_entity_type(
        self,
        tags: list | None,
    ) -> EntityType | None:
        """
        Returns the EntityType implied by a note's `tags`, or None
        if no tag is recognised. Never returns OTHER by inference --
        the caller decides what to do when nothing matches.
        """

        if not tags:
            return None

        for tag in tags:
            key = str(tag).strip().casefold()

            if key in self._entity_type_tags:
                return self._entity_type_tags[key]

        return None

    def is_event(self, tags: list | None) -> bool:
        if not tags:
            return False

        return any(
            str(tag).strip().casefold() in self._event_tags
            for tag in tags
        )

    def get_field(self, frontmatter: dict, concept: str):
        """
        Looks up a semantic concept (e.g. "date", "location") in
        frontmatter, trying every known alias for that concept.
        Matching is case-insensitive on the frontmatter key.
        Returns None if nothing matches.
        """

        aliases = self._field_aliases.get(concept, [concept])
        lowered = {
            str(key).strip().casefold(): value
            for key, value in frontmatter.items()
        }

        for alias in aliases:
            if alias in lowered and lowered[alias] is not None:
                return lowered[alias]

        return None

    def get_field_aliases(self, concept: str) -> list[str]:
        return self._field_aliases.get(concept, [concept])

    def canonicalize_predicate(self, predicate: str) -> str:
        """
        Maps a raw predicate string to a canonical form so
        different vocabulary for the same concept ("zginął" /
        "umarł" / "died") is treated as one predicate when checking
        for contradictions. Predicates not in the synonym table are
        returned casefolded/stripped, unchanged otherwise.
        """

        key = predicate.strip().casefold()
        return self._predicate_synonyms.get(key, key)

    def get_role_fields(self) -> dict[str, list[str]]:
        return self._role_fields

    def has_any_date_field(self, frontmatter: dict) -> bool:
        return (
            self.get_field(frontmatter, "date") is not None
            or self.get_field(frontmatter, "date_start") is not None
        )

    def relationship_group_of(self, predicate: str) -> int | None:
        """
        Returns the index of the relationship-exclusivity group a
        predicate belongs to, or None if the predicate isn't a
        known relationship term (e.g. "rasa" isn't relational, so
        it's never compared by RelationshipContradictionRule).
        """

        key = predicate.strip().casefold()

        for index, group in enumerate(self._relationship_groups):
            if key in group:
                return index

        return None
