from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConflictSeverity, Fact
from app.rules.base import ConflictCandidate, Rule


class ExclusiveFactRule(Rule):
    """
    A subject shouldn't have two different values recorded for the
    same predicate -- e.g. two different `rasa` for one character,
    or (once prose extraction exists) two different `died` years
    for one person.

    This is the generic mechanism behind plan section 23's
    "character_single_death" / "kingdom_single_capital" idea. It
    doesn't special-case any predicate name, so it works today on
    frontmatter-sourced Facts, and needs no changes once step 19
    (LLM prose extraction) starts producing facts like `died`.

    Facts pointing at an Entity are compared by entity id. Plain
    text facts are compared case-insensitively after normalizing
    whitespace, so trivial formatting differences ("Człowiek " vs
    "człowiek") don't create noise.

    If a predicate has 3+ distinct values across facts, only the
    first two distinct variants are reported as a representative
    pair, to keep the number of conflicts manageable.
    """

    name = "exclusive_fact"

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        facts = db.scalars(select(Fact)).all()

        grouped: dict[tuple[int, str], list[Fact]] = defaultdict(list)

        for fact in facts:
            key = (
                fact.subject_entity_id,
                fact.predicate.strip().casefold(),
            )
            grouped[key].append(fact)

        candidates: list[ConflictCandidate] = []

        for (entity_id, predicate), group in grouped.items():
            by_value: dict[str, list[Fact]] = defaultdict(list)

            for fact in group:
                by_value[self._normalize(fact)].append(fact)

            if len(by_value) < 2:
                continue

            variants = list(by_value.values())
            fact_a = variants[0][0]
            fact_b = variants[1][0]

            candidates.append(
                ConflictCandidate(
                    entity_id=entity_id,
                    rule_name=self.name,
                    severity=ConflictSeverity.MEDIUM,
                    confidence=0.9,
                    explanation=(
                        f"'{predicate}' has conflicting values: "
                        f"'{self._display(fact_a)}' "
                        f"(from {fact_a.document.title}) vs "
                        f"'{self._display(fact_b)}' "
                        f"(from {fact_b.document.title})"
                    ),
                    fact_a_id=fact_a.id,
                    fact_b_id=fact_b.id,
                )
            )

        return candidates

    @staticmethod
    def _normalize(fact: Fact) -> str:
        if fact.object_entity_id is not None:
            return f"entity:{fact.object_entity_id}"

        return " ".join((fact.object_value or "").strip().casefold().split())

    @staticmethod
    def _display(fact: Fact) -> str:
        if fact.object_entity_id is not None:
            return fact.object_entity.name if fact.object_entity else "?"

        return fact.object_value or "?"
