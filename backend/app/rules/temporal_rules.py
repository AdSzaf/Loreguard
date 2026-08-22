from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vault_schema import VaultSchema
from app.models import ConflictSeverity, Event, Fact
from app.rules.base import ConflictCandidate, Rule
from app.rules.temporal_utils import resolve_year_from_fact
from app.services.event_extractor import DateParser


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


class AgeImpossibilityRule(Rule):
    """
    Plan section 6F: if prose states someone's age at a specific
    event ("mając zaledwie 12 lat, objęła dowództwo w Bitwie pod
    Arven"), and their birth year is known from elsewhere, the
    stated age must equal (event_year - birth_year). A mismatch is
    a hard, checkable contradiction -- the comparison itself needs
    no LLM, only plain arithmetic on numbers already in the
    database. The LLM's only job (see EXTRACTION_SYSTEM_PROMPT's
    "wiek_podczas" example) is producing the "age at event" fact in
    the first place.

    Requires, for the same subject:
      - a Fact whose canonicalized predicate is "age_at_event",
        with object_number set (the stated age) and an object
        that resolves to a year (via a linked Event's
        date_start_year -- see resolve_year_from_fact)
      - a Fact whose canonicalized predicate is "born", resolving
        to an actual year the same way

    Missing either piece means there's nothing to check for that
    fact -- this rule never guesses a birth year or an event date,
    it only compares numbers it can actually resolve.
    """

    name = "age_impossibility"

    def __init__(self, schema: VaultSchema):
        self.schema = schema
        self.date_parser = DateParser()

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        facts = db.scalars(select(Fact)).all()

        age_facts = [
            fact
            for fact in facts
            if fact.object_number is not None
            and self.schema.canonicalize_predicate(fact.predicate)
            == "age_at_event"
        ]

        candidates: list[ConflictCandidate] = []

        for age_fact in age_facts:
            event_year = resolve_year_from_fact(
                db, age_fact, self.date_parser
            )

            if event_year is None:
                continue

            birth_fact = next(
                (
                    fact
                    for fact in facts
                    if fact.subject_entity_id == age_fact.subject_entity_id
                    and self.schema.canonicalize_predicate(fact.predicate)
                    == "born"
                ),
                None,
            )

            if birth_fact is None:
                continue

            birth_year = resolve_year_from_fact(
                db, birth_fact, self.date_parser
            )

            if birth_year is None:
                continue

            expected_age = event_year - birth_year
            stated_age = age_fact.object_number

            if expected_age == stated_age:
                continue

            event_name = (
                age_fact.object_entity.name
                if age_fact.object_entity
                else "?"
            )

            stated_age_display = (
                int(stated_age)
                if float(stated_age).is_integer()
                else stated_age
            )

            candidates.append(
                ConflictCandidate(
                    entity_id=age_fact.subject_entity_id,
                    rule_name=self.name,
                    severity=ConflictSeverity.MEDIUM,
                    confidence=0.9,
                    explanation=(
                        f"'{age_fact.subject.name}' urodzony/a w "
                        f"{birth_year} miałby/miałaby {expected_age} lat "
                        f"podczas '{event_name}' ({event_year}), ale "
                        f"{age_fact.document.title} mówi o "
                        f"{stated_age_display} latach."
                    ),
                    fact_a_id=birth_fact.id,
                    fact_b_id=age_fact.id,
                )
            )

        return candidates
