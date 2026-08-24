from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


def ci_equals(column, value: str) -> ColumnElement:
    """
    Case-insensitive EXACT match -- use this instead of
    `column.ilike(value)` whenever the intent is "same string,
    ignoring case" rather than an actual wildcard search.

    `.ilike()` treats %, _, and a trailing \\ as pattern
    metacharacters. A value containing any of them either matches
    the wrong rows silently (a stray "_" acts as a single-character
    wildcard) or crashes outright on Postgres (a trailing "\\"
    breaks LIKE's escape-sequence parsing entirely -- this is
    exactly what happened with a wikilink alias escaped for a
    Markdown table, e.g. `[[Magnia\\|Magnii]]`).

    `func.lower(column) == func.lower(value)` has no such
    metacharacters to worry about -- it's a plain string comparison.
    """

    return func.lower(column) == func.lower(value)
