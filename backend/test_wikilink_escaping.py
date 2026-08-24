r"""
Reproduces the exact crash the user hit: a wikilink with an
escaped pipe inside a Markdown table (Obsidian requires `\|` to
avoid breaking table syntax), e.g. `[[Magnia\|Magnii]]`, previously
extracted "Magnia\" (trailing backslash) as the entity name, which
crashed Postgres's ILIKE (backslash is ITS escape character).

Run with:
    python test_wikilink_escaping.py
"""

import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.db_utils import ci_equals
from app.core.wikilinks import iter_wikilinks, parse_wikilink
from app.core.vault_schema import VaultSchema
from app.models import Entity, EntityType
from app.services.entity_extractor import EntityExtractor
from app.services.entity_resolver import EntityResolver
from pathlib import Path


passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed

    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


print("=" * 60)
print("CASE 1: escaped-pipe wikilink (Markdown table syntax)")
print("=" * 60)

table_row = "| Era | Data |\n| --- | --- |\n| [[Magnia\\|Magnii]] | 842-900 |\n"

results = list(iter_wikilinks(table_row))
check("exactly one wikilink found", len(results) == 1)

if results:
    target, alias = results[0]
    check("target has NO trailing backslash", target == "Magnia")
    check("alias correctly captured", alias == "Magnii")
    print(f"  parsed: target={target!r}, alias={alias!r}")

print()
print("=" * 60)
print("CASE 2: parse_wikilink (single-link fullmatch, frontmatter-style)")
print("=" * 60)

parsed = parse_wikilink("[[Magnia\\|Magnii]]")
check("fullmatch also strips the escape backslash", parsed == ("Magnia", "Magnii"))

parsed_plain = parse_wikilink("[[Arven]]")
check("plain wikilink (no alias) still works", parsed_plain == ("Arven", None))

parsed_not_link = parse_wikilink("just plain text")
check("non-wikilink text returns None", parsed_not_link is None)

print()
print("=" * 60)
print("CASE 3: full EntityExtractor + EntityResolver pipeline")
print("=" * 60)

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))
extractor = EntityExtractor()
resolver = EntityResolver(db, schema)

candidates = extractor.extract_from_content(table_row)
check("EntityExtractor finds the candidate", len(candidates) == 1)

if candidates:
    entity = resolver.resolve(candidates[0])
    db.commit()

    check(
        "entity resolves/creates without crashing, name is clean",
        entity.name == "Magnia",
    )

    # This is the exact query shape that crashed against Postgres
    # (ILIKE with a value ending in a bare backslash). Confirming it
    # doesn't even build a LIKE pattern is the real regression test
    # -- ci_equals uses func.lower()/==, which has no metacharacters
    # to misinterpret regardless of backend.
    from sqlalchemy import select

    refound = db.scalar(
        select(Entity).where(ci_equals(Entity.name, "magnia"))
    )
    check("ci_equals finds it back, case-insensitively", refound is not None and refound.id == entity.id)

print()
print("=" * 60)
print("CASE 4: ci_equals is immune to LIKE metacharacters in general")
print("=" * 60)

# Names containing %, _, or a trailing \ must be matched as LITERAL
# strings, not interpreted as wildcards/escapes.
tricky_names = ["100%_Pewny", "Coś\\", "A_B", "50%"]

for name in tricky_names:
    e = Entity(name=name, entity_type=EntityType.OTHER)
    db.add(e)
db.commit()

from sqlalchemy import select

for name in tricky_names:
    found = db.scalar(select(Entity).where(ci_equals(Entity.name, name)))
    check(f"ci_equals handles {name!r} literally, no crash", found is not None)

# And critically: "A_B" must NOT match "AXB" via wildcard behavior.
decoy = Entity(name="AXB", entity_type=EntityType.OTHER)
db.add(decoy)
db.commit()

ab_match = db.scalars(
    select(Entity).where(ci_equals(Entity.name, "A_B"))
).all()
check(
    "'_' in a name is NOT treated as a single-char wildcard",
    len(ab_match) == 1 and ab_match[0].name == "A_B",
)

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

db.close()

if failed:
    raise SystemExit(1)
