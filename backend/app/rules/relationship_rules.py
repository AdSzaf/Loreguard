from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vault_schema import VaultSchema
from app.models import ConflictSeverity, Fact
from app.rules.base import ConflictCandidate, Rule


class RelationshipContradictionRule(Rule):
    """
    Plan section 6D: "Elira jest córką Aldrena" vs "Elira jest
    siostrą Aldrena" -- the same pair of entities can't hold two
    relationship types that belong to different exclusivity groups
    (parent/child vs sibling vs spouse, by default).

    Which predicates belong to which group comes entirely from
    VaultSchema (built-in PL/EN defaults, extendable via
    `.loreguard/schema.yaml`'s `relationship_groups`). Predicates
    the schema doesn't recognise as relational (e.g. "rasa") are
    ignored by this rule -- ExclusiveFactRule already covers
    same-predicate contradictions on its own.
    """

    name = "relationship_contradiction"

    def __init__(self, schema: VaultSchema):
        self.schema = schema

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        facts = db.scalars(
            select(Fact).where(Fact.object_entity_id.is_not(None))
        ).all()

        grouped: dict[tuple[int, int], list[Fact]] = defaultdict(list)

        for fact in facts:
            group_index = self.schema.relationship_group_of(fact.predicate)

            if group_index is None:
                continue

            key = (fact.subject_entity_id, fact.object_entity_id)
            grouped[key].append(fact)

        candidates: list[ConflictCandidate] = []

        for (subject_id, _object_id), group in grouped.items():
            by_group: dict[int, Fact] = {}

            for fact in group:
                group_index = self.schema.relationship_group_of(
                    fact.predicate
                )

                if group_index in by_group:
                    continue

                by_group[group_index] = fact

            if len(by_group) < 2:
                continue

            facts_involved = list(by_group.values())
            fact_a, fact_b = facts_involved[0], facts_involved[1]

            candidates.append(
                ConflictCandidate(
                    entity_id=subject_id,
                    rule_name=self.name,
                    severity=ConflictSeverity.HIGH,
                    confidence=0.85,
                    explanation=(
                        f"'{fact_a.subject.name}' is described as both "
                        f"'{fact_a.predicate}' and '{fact_b.predicate}' "
                        f"of '{fact_a.object_entity.name}' "
                        f"({fact_a.document.title} vs "
                        f"{fact_b.document.title})."
                    ),
                    fact_a_id=fact_a.id,
                    fact_b_id=fact_b.id,
                )
            )

        return candidates
