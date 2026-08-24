import re

# Single source of truth for Obsidian wikilink syntax across the
# whole app -- previously duplicated independently in three
# services, which is exactly how a bug like this survives a fix in
# one place while still lurking in the other two.
#
# Escaping the pipe as `\|` is required inside Markdown tables (the
# pipe is the column separator there), producing links like
# `[[Magnia\|Magnii]]`. Backslash is excluded from both capture
# groups, and an optional stray `\` immediately before the closing
# `|` or `]]` is consumed separately, so the escape character never
# ends up inside a captured name. A bare trailing backslash
# previously broke Postgres's ILIKE (its own escape character)
# whenever such a name reached the database.
WIKILINK_PATTERN = re.compile(
    r"\[\[([^\]|#\\]+)\\?(?:\|([^\]\\]+)\\?)?\]\]"
)


def parse_wikilink(text: str) -> tuple[str, str | None] | None:
    """
    Parses a string that should be ENTIRELY one wikilink (e.g. a
    frontmatter field value like `[[Arven]]`). Returns
    (target, alias_or_None), or None if the string isn't a wikilink
    at all (in which case callers typically fall back to treating
    it as plain text).
    """

    match = WIKILINK_PATTERN.fullmatch(text.strip())

    if not match:
        return None

    target = _clean(match.group(1))

    if not target:
        return None

    return target, _clean(match.group(2))


def iter_wikilinks(content: str):
    """
    Yields (target, alias_or_None) for every wikilink found
    anywhere within a larger block of text (e.g. a document body).
    """

    for match in WIKILINK_PATTERN.finditer(content):
        target = _clean(match.group(1))

        if not target:
            continue

        yield target, _clean(match.group(2))


def _clean(value: str | None) -> str | None:
    if value is None:
        return None

    # Defensive, in addition to the regex itself excluding
    # backslash: strip any stray trailing backslash regardless of
    # exactly how it got there.
    return value.strip().rstrip("\\").strip() or None
