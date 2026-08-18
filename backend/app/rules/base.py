from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ConflictSeverity


@dataclass
class ConflictCandidate:
    """
    A potential conflict found by a Rule, before it's checked
    against existing Conflict rows and (maybe) persisted.
    """

    entity_id: int
    rule_name: str
    severity: ConflictSeverity
    confidence: float
    explanation: str
    fact_a_id: int | None = None
    fact_b_id: int | None = None
    related_event_id: int | None = None


class Rule:
    """
    Base class for deterministic consistency rules.

    Rules read whatever Facts/Events already exist -- they never
    care whether that data came from frontmatter (today) or from
    LLM-extracted prose (later, roadmap step 19). This is the
    "Deterministic Rules Engine" box from the architecture diagram.
    """

    name: str = "base_rule"

    def evaluate(self, db: Session) -> list[ConflictCandidate]:
        raise NotImplementedError
