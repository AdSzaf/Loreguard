from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Fact
from app.services.event_extractor import DateParser


def resolve_year_from_fact(
    db: Session,
    fact: Fact,
    date_parser: DateParser,
) -> int | None:
    """
    Resolves a Fact's object to an actual year, whether the object
    is a literal date-like string ("3030 K.E.", parsed via
    DateParser) or a linked Event entity (whose own
    date_start_year -- extracted from frontmatter by
    EventExtractor, no LLM involved -- is used instead).

    Returns None if no year can be determined; callers should treat
    that as "nothing to compare", not as an error.
    """

    if fact.object_entity_id is not None:
        event = db.scalar(
            select(Event).where(Event.entity_id == fact.object_entity_id)
        )

        if event is not None and event.date_start_year is not None:
            return event.date_start_year

        return None

    if fact.object_value:
        year, _, _ = date_parser.parse(fact.object_value)
        return year

    return None
