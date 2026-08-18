from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conflict, ConflictStatus
from app.rules.base import ConflictCandidate, Rule
from app.rules.logical_rules import ExclusiveFactRule
from app.rules.temporal_rules import EventDateRangeRule


class ConsistencyEngine:
    """
    Runs all registered rules and turns their findings into
    Conflict rows.

    Idempotent by design:
      - re-running never creates a duplicate of a conflict that's
        already tracked (open or otherwise)
      - it never touches a conflict the person already reviewed
        (CONFIRMED / DISMISSED / EXPLAINED) -- per the project
        concept, the person is always the final arbiter, so a
        dismissed conflict must stay dismissed even if the same
        rule fires again on a later sync
    """

    def __init__(self, db: Session, rules: list[Rule] | None = None):
        self.db = db
        self.rules = rules or [
            ExclusiveFactRule(),
            EventDateRangeRule(),
        ]

    def run(self) -> dict:
        candidates: list[ConflictCandidate] = []

        for rule in self.rules:
            candidates.extend(rule.evaluate(self.db))

        created = 0
        skipped = 0

        for candidate in candidates:
            if self._already_tracked(candidate):
                skipped += 1
                continue

            self.db.add(
                Conflict(
                    entity_id=candidate.entity_id,
                    rule_name=candidate.rule_name,
                    severity=candidate.severity,
                    confidence=candidate.confidence,
                    status=ConflictStatus.OPEN,
                    explanation=candidate.explanation,
                    fact_a_id=candidate.fact_a_id,
                    fact_b_id=candidate.fact_b_id,
                    related_event_id=candidate.related_event_id,
                )
            )
            created += 1

        self.db.flush()

        return {
            "candidates_found": len(candidates),
            "created": created,
            "skipped_existing": skipped,
        }

    def _already_tracked(self, candidate: ConflictCandidate) -> bool:
        query = select(Conflict).where(
            Conflict.rule_name == candidate.rule_name,
            Conflict.entity_id == candidate.entity_id,
        )

        if candidate.fact_a_id is not None:
            fact_ids = [candidate.fact_a_id, candidate.fact_b_id]

            query = query.where(
                Conflict.fact_a_id.in_(fact_ids),
                Conflict.fact_b_id.in_(fact_ids),
            )

        if candidate.related_event_id is not None:
            query = query.where(
                Conflict.related_event_id == candidate.related_event_id
            )

        return self.db.scalar(query) is not None
