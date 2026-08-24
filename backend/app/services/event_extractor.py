import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db_utils import ci_equals
from app.core.vault_schema import VaultSchema
from app.core.wikilinks import parse_wikilink
from app.models import (
    Document,
    Entity,
    Event,
    DatePrecision,
    EventParticipant,
)
from app.schemas.document import ParsedDocument


class DateParser:
    """
    Parses fuzzy, human-written fantasy dates into a normalized
    (start_year, end_year, precision) triple.

    Handles things like:
        842
        842 n.e.
        rok 842
        wiosna 842
        marzec 842
        12 marca 842
        około 842
        820-825

    Does not attempt full calendar support (custom eras, multiple
    calendars). If no year-like number is found, precision is
    UNKNOWN and both years are None -- the caller decides what to
    do with that (usually: store the raw text, skip rule checks).
    """

    YEAR_PATTERN = re.compile(r"\d{1,5}")

    APPROX_WORDS = (
        "około",
        "ok.",
        "circa",
        "c.",
        "mniej więcej",
        "przypuszczalnie",
    )

    MONTHS = (
        "styczeń", "stycznia", "luty", "lutego", "marzec", "marca",
        "kwiecień", "kwietnia", "maj", "maja", "czerwiec", "czerwca",
        "lipiec", "lipca", "sierpień", "sierpnia", "wrzesień", "września",
        "październik", "października", "listopad", "listopada",
        "grudzień", "grudnia",
    )

    # "12 marca 842" -- day + month word + year. Matched first so a
    # day number is never mistaken for the second half of a range.
    DAY_PATTERN = re.compile(r"\b\d{1,2}\s+\w+\s+(\d{1,5})\b")

    # "820-825", "820 do 825", "820 – 825"
    RANGE_PATTERN = re.compile(
        r"(\d{1,5})\s*(?:-|–|—|do)\s*(\d{1,5})"
    )

    def parse(
        self,
        raw: str,
    ) -> tuple[int | None, int | None, DatePrecision]:
        if not raw:
            return None, None, DatePrecision.UNKNOWN

        text = raw.strip().lower()

        is_approximate = any(word in text for word in self.APPROX_WORDS)

        day_match = self.DAY_PATTERN.search(text)

        if day_match:
            year = int(day_match.group(1))
            precision = (
                DatePrecision.APPROXIMATE
                if is_approximate
                else DatePrecision.DAY
            )

            return year, year, precision

        if any(month in text for month in self.MONTHS):
            years = [int(match) for match in self.YEAR_PATTERN.findall(text)]

            if years:
                precision = (
                    DatePrecision.APPROXIMATE
                    if is_approximate
                    else DatePrecision.MONTH
                )

                return years[-1], years[-1], precision

        range_match = self.RANGE_PATTERN.search(text)

        if range_match:
            start, end = (
                int(range_match.group(1)),
                int(range_match.group(2)),
            )

            precision = (
                DatePrecision.APPROXIMATE
                if is_approximate
                else DatePrecision.YEAR
            )

            return min(start, end), max(start, end), precision

        years = [int(match) for match in self.YEAR_PATTERN.findall(text)]

        if not years:
            return None, None, DatePrecision.UNKNOWN

        year = years[0]
        precision = (
            DatePrecision.APPROXIMATE
            if is_approximate
            else DatePrecision.YEAR
        )

        return year, year, precision


class EventExtractor:
    """
    Extracts a structured Event from an Obsidian document's
    frontmatter, when that document represents an event.

    Nothing about field names is hardcoded: which frontmatter keys
    mean "date", "location", etc., and which tags mean "this note
    is an event", come entirely from VaultSchema (built-in PL/EN
    defaults, overridable per-vault via .loreguard/schema.yaml).

    A document is treated as an event when:
      - one of its `tags` is a recognised event tag, OR
      - it has a recognised date-like field (date/date_start)

    A document's own subject entity must already exist (see
    EntityIndexer.index_document / EntityResolver.resolve_subject)
    before this runs -- events attach to that entity rather than
    creating their own.

    Mirrors FactExtractor's style: no LLM involved, everything is
    parsed deterministically from frontmatter the author wrote.
    """

    def __init__(self, db: Session, schema: VaultSchema):
        self.db = db
        self.schema = schema
        self.date_parser = DateParser()

    def extract_from_document(
        self,
        document: Document,
        parsed_document: ParsedDocument,
    ) -> Event | None:
        frontmatter = parsed_document.frontmatter

        if not self._looks_like_event(frontmatter):
            return None

        entity = self.db.scalar(
            select(Entity).where(ci_equals(Entity.name, document.title))
        )

        if entity is None:
            # Subject entity should already exist from
            # EntityIndexer.index_document. If it somehow doesn't
            # (e.g. this is called outside the normal pipeline),
            # there's nothing to attach the event to.
            return None

        event = self.db.scalar(
            select(Event).where(Event.entity_id == entity.id)
        )

        if event is None:
            event = Event(
                entity_id=entity.id,
                document_id=document.id,
            )
            self.db.add(event)
        else:
            event.document_id = document.id

        date_start, date_end, precision = self._parse_dates(frontmatter)
        location = self._resolve_entity_field(
            self.schema.get_field(frontmatter, "location")
        )

        event.date_text = self._raw_date_text(frontmatter)
        event.date_start_year = date_start
        event.date_end_year = date_end
        event.precision = precision
        event.location_entity_id = location.id if location else None
        event.outcome = self._as_text(
            self.schema.get_field(frontmatter, "outcome")
        )
        event.description = self._as_text(
            self.schema.get_field(frontmatter, "description")
        )

        self.db.flush()

        self._sync_participants(event, frontmatter)

        self.db.flush()

        return event

    def _looks_like_event(self, frontmatter: dict) -> bool:
        if self.schema.is_event(frontmatter.get("tags")):
            return True

        return self.schema.has_any_date_field(frontmatter)

    def _parse_dates(
        self,
        frontmatter: dict,
    ) -> tuple[int | None, int | None, DatePrecision]:
        date_start_raw = self.schema.get_field(frontmatter, "date_start")
        date_end_raw = self.schema.get_field(frontmatter, "date_end")

        if date_start_raw is not None or date_end_raw is not None:
            start, _, start_precision = self.date_parser.parse(
                str(date_start_raw or "").strip()
            )
            end, _, end_precision = self.date_parser.parse(
                str(date_end_raw or "").strip()
            )

            precision = (
                DatePrecision.APPROXIMATE
                if DatePrecision.APPROXIMATE
                in (start_precision, end_precision)
                else start_precision
            )

            return start, (end if end is not None else start), precision

        raw_date = self.schema.get_field(frontmatter, "date")

        if raw_date is None:
            return None, None, DatePrecision.UNKNOWN

        return self.date_parser.parse(str(raw_date))

    def _raw_date_text(self, frontmatter: dict) -> str | None:
        for concept in ("date", "date_start"):
            value = self.schema.get_field(frontmatter, concept)

            if value is not None:
                return str(value).strip()

        return None

    @staticmethod
    def _as_text(value) -> str | None:
        if value is None:
            return None

        if isinstance(value, list):
            return ", ".join(str(item) for item in value)

        return str(value).strip() or None

    def _resolve_entity_field(self, value) -> Entity | None:
        if not value:
            return None

        name = self._strip_wikilink(str(value))

        if not name:
            return None

        return self.db.scalar(
            select(Entity).where(ci_equals(Entity.name, name))
        )

    @staticmethod
    def _strip_wikilink(value: str) -> str:
        parsed = parse_wikilink(value)

        if parsed:
            return parsed[0]

        return value.strip()

    def _sync_participants(
        self,
        event: Event,
        frontmatter: dict,
    ) -> None:
        """
        Rebuilds the participant list to match the current
        frontmatter, removing participants that were removed from
        the document and adding new ones.

        The generic "participants" concept always maps to role
        None. Any additional named role (e.g. "commander") comes
        from VaultSchema.get_role_fields(), so a vault can define
        its own roles without touching code.
        """

        existing_by_key = {
            (participant.entity_id, participant.role): participant
            for participant in event.participants
        }

        seen_keys: set[tuple[int, str | None]] = set()

        role_field_lookup: dict[str | None, list[str]] = {
            None: self.schema.get_field_aliases("participants"),
        }
        role_field_lookup.update(self.schema.get_role_fields())

        lowered_frontmatter = {
            str(key).strip().casefold(): value
            for key, value in frontmatter.items()
        }

        for role, aliases in role_field_lookup.items():
            raw_value = None

            for alias in aliases:
                if alias in lowered_frontmatter and lowered_frontmatter[alias] is not None:
                    raw_value = lowered_frontmatter[alias]
                    break

            if not raw_value:
                continue

            values = (
                raw_value if isinstance(raw_value, list) else [raw_value]
            )

            for item in values:
                candidate_entity = self._resolve_entity_field(item)

                if candidate_entity is None:
                    continue

                key = (candidate_entity.id, role)
                seen_keys.add(key)

                if key in existing_by_key:
                    continue

                self.db.add(
                    EventParticipant(
                        event_id=event.id,
                        entity_id=candidate_entity.id,
                        role=role,
                    )
                )

        for key, participant in existing_by_key.items():
            if key not in seen_keys:
                self.db.delete(participant)
