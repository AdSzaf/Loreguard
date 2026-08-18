from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConflictSeverity, Event
from app.rules.base import ConflictCandidate, Rule


class EventDateRangeRule(Rule):
    """
    An event's end year can't be before its start year.

    Catches typos or swapped fields in frontmatter (e.g. a vault
    using `data_od`/`data_do` where the two got mixed up) using
    only a single event's own data -- no cross-document comparison
    needed, so it's useful even in a small, mostly-pantheon vault.
    """

    name = "event_date_range"

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        events = db.scalars(
            select(Event).where(
                Event.date_start_year.is_not(None),
                Event.date_end_year.is_not(None),
            )
        ).all()

        candidates: list[ConflictCandidate] = []

        for event in events:
            if event.date_end_year < event.date_start_year:
                candidates.append(
                    ConflictCandidate(
                        entity_id=event.entity_id,
                        rule_name=self.name,
                        severity=ConflictSeverity.LOW,
                        confidence=0.95,
                        explanation=(
                            f"Event '{event.entity.name}' ends "
                            f"({event.date_end_year}) before it starts "
                            f"({event.date_start_year})."
                        ),
                        related_event_id=event.id,
                    )
                )

        return candidates
