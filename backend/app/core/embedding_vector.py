import json

from sqlalchemy.types import Text, TypeDecorator


class EmbeddingVector(TypeDecorator):
    """
    Stores a fixed-length embedding vector as a JSON array in a
    TEXT column.

    This intentionally does NOT use pgvector's native `vector`
    column type (which requires the `vector` Postgres extension to
    be installed) -- on a native Windows Postgres install without
    Docker, that extension can be a real setup hurdle, and a failed
    "CREATE EXTENSION" in a migration would block every migration
    after it. JSON-in-TEXT works on any backend with zero setup.

    The cost: similarity search happens in Python
    (EmbeddingService.find_similar), not as an indexed SQL query.
    That's fine up to at least a few thousand documents. If a vault
    ever gets big enough for that to matter, swap this column's
    type to pgvector's Vector(dimensions) and move the search into
    SQL (`ORDER BY embedding <=> :query`) -- EmbeddingService's
    public interface doesn't need to change either way.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None

        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None

        return json.loads(value)
