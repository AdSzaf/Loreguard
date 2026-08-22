from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vault_schema import VaultSchema
from app.models import ConflictSeverity, Fact
from app.rules.base import ConflictCandidate, Rule
from app.rules.temporal_utils import resolve_year_from_fact
from app.services.event_extractor import DateParser


# Canonical predicates (after VaultSchema.canonicalize_predicate)
# whose values are fundamentally dates/years, even when phrased as
# "died in that event" rather than "died in year X". For these,
# the rule resolves an actual year before comparing -- see
# _resolve() below.
TEMPORAL_PREDICATES = {"died", "born"}


class ExclusiveFactRule(Rule):
    """
    A subject shouldn't have two different values recorded for the
    same predicate -- e.g. two different `rasa` for one character,
    or two different death years for one person.

    This is the generic mechanism behind plan section 23's
    "character_single_death" / "kingdom_single_capital" idea. It
    doesn't special-case any predicate name -- instead, predicates
    are grouped by VaultSchema.canonicalize_predicate() first, so
    "zginął" (from one article) and "umarł" (from another) are
    compared as the same underlying concept even though an LLM (or
    two different authors) used different words for it.

    Grounding temporal facts against Event dates
    ---------------------------------------------
    A death/birth fact's object is sometimes an EVENT ("zginął w
    Bitwie pod Soizon") rather than a literal year ("umarł w 3030").
    Comparing those naively (an entity vs a string) would either
    always look "different" (even if the battle really did happen
    in 3030 -- a false positive) or never be usefully explained.

    Instead, for TEMPORAL_PREDICATES, this rule looks up the
    linked Event's own date_start_year (already extracted from
    frontmatter by EventExtractor -- no LLM involved in this step)
    and compares actual years. If the event has no known date, it
    falls back to comparing by entity/text identity, same as
    before -- still surfaced, just at slightly lower confidence,
    since it's a softer signal than a directly grounded date clash.

    Facts pointing at an Entity are compared by entity id. Plain
    text facts are compared case-insensitively after normalizing
    whitespace, so trivial formatting differences ("Człowiek " vs
    "człowiek") don't create noise.

    If a predicate has 3+ distinct values across facts, only the
    first two distinct variants are reported as a representative
    pair, to keep the number of conflicts manageable.
    """

    name = "exclusive_fact"

    def __init__(self, schema: VaultSchema):
        self.schema = schema
        self.date_parser = DateParser()

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        facts = db.scalars(select(Fact)).all()

        grouped: dict[tuple[int, str], list[Fact]] = defaultdict(list)

        for fact in facts:
            key = (
                fact.subject_entity_id,
                self.schema.canonicalize_predicate(fact.predicate),
            )
            grouped[key].append(fact)

        candidates: list[ConflictCandidate] = []

        for (entity_id, canonical_predicate), group in grouped.items():
            is_temporal = canonical_predicate in TEMPORAL_PREDICATES

            resolved = {
                fact.id: self._resolve(db, fact, is_temporal)
                for fact in group
            }

            by_value: dict[str, list[Fact]] = defaultdict(list)

            for fact in group:
                by_value[resolved[fact.id][0]].append(fact)

            if len(by_value) < 2:
                continue

            variants = list(by_value.values())
            fact_a = variants[0][0]
            fact_b = variants[1][0]

            _, display_a, year_a = resolved[fact_a.id]
            _, display_b, year_b = resolved[fact_b.id]

            grounded = is_temporal and year_a is not None and year_b is not None

            label = (
                f"'{fact_a.predicate}'"
                if fact_a.predicate.strip().casefold()
                == fact_b.predicate.strip().casefold()
                else f"'{fact_a.predicate}'/'{fact_b.predicate}'"
            )

            candidates.append(
                ConflictCandidate(
                    entity_id=entity_id,
                    rule_name=self.name,
                    severity=ConflictSeverity.MEDIUM,
                    confidence=0.95 if grounded else 0.9,
                    explanation=(
                        f"{label} has conflicting values: "
                        f"'{display_a}' "
                        f"(from {fact_a.document.title}) vs "
                        f"'{display_b}' "
                        f"(from {fact_b.document.title})"
                    ),
                    fact_a_id=fact_a.id,
                    fact_b_id=fact_b.id,
                )
            )

        return candidates

    def _resolve(
        self,
        db: Session,
        fact: Fact,
        is_temporal: bool,
    ) -> tuple[str, str, int | None]:
        """
        Returns (normalize_key, display_string, resolved_year).
        resolved_year is None unless is_temporal and an actual year
        could be determined (either directly, or via a linked
        Event's date_start_year).
        """

        if is_temporal:
            year = resolve_year_from_fact(db, fact, self.date_parser)

            if year is not None:
                if fact.object_entity_id is not None:
                    event_name = (
                        fact.object_entity.name
                        if fact.object_entity
                        else "?"
                    )
                    return (
                        f"year:{year}",
                        f"{year} (data wydarzenia: {event_name})",
                        year,
                    )

                return f"year:{year}", str(year), year

        if fact.object_entity_id is not None:
            name = fact.object_entity.name if fact.object_entity else "?"
            return f"entity:{fact.object_entity_id}", name, None

        normalized_text = " ".join(
            (fact.object_value or "").strip().casefold().split()
        )

        return normalized_text, (fact.object_value or "?"), None
