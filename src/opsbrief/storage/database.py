"""SQLite connection handling for the event store.

Persistence is deliberately thin: one SQLite file, one table per stored
concept, plain SQL. There is no object-relational mapper because nothing in
the roadmap yet needs one.
"""

import sqlite3
from pathlib import Path

SQLITE_URL_PREFIX = "sqlite:///"
IN_MEMORY_PATH = ":memory:"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    subject      TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    severity     TEXT NOT NULL,
    status       TEXT,
    entity_type  TEXT,
    entity_id    TEXT,
    due_at       TEXT,
    external_id  TEXT,
    metadata     TEXT NOT NULL,
    received_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS events_occurred_at_idx ON events (occurred_at);
CREATE INDEX IF NOT EXISTS events_source_external_id_idx ON events (source, external_id);
"""


def database_path(database_url: str) -> str:
    """Return the SQLite path named by ``database_url``.

    Only ``sqlite:///`` URLs are accepted. Anything else is refused loudly
    rather than silently falling back to a local file.
    """
    if not database_url.startswith(SQLITE_URL_PREFIX):
        raise ValueError(
            f"unsupported database URL {database_url!r}: only {SQLITE_URL_PREFIX} is supported"
        )
    path = database_url[len(SQLITE_URL_PREFIX) :].strip()
    if not path:
        raise ValueError(f"database URL {database_url!r} names no SQLite database")
    return path


def connect(database_url: str) -> sqlite3.Connection:
    """Open a connection to the database named by ``database_url``.

    The parent directory of a file database is created when missing so that a
    fresh checkout runs without a setup step.
    """
    path = database_path(database_url)
    if path != IN_MEMORY_PATH:
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the tables and indexes the service needs, if they are absent."""
    with connection:
        connection.executescript(SCHEMA)
