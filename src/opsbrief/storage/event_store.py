"""Storage of operational events in SQLite."""

import json
import sqlite3
from datetime import UTC, datetime
from threading import Lock
from types import TracebackType

from opsbrief.events import Event, EventSeverity, EventStatus, MetadataValue
from opsbrief.storage.database import connect, create_schema

#: Fixed-width UTC representation, so stored timestamps sort in string order.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_COLUMNS = (
    "id",
    "source",
    "event_type",
    "subject",
    "occurred_at",
    "severity",
    "status",
    "entity_type",
    "entity_id",
    "due_at",
    "external_id",
    "metadata",
    "received_at",
)

_INSERT = (
    f"INSERT INTO events ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(':' + column for column in _COLUMNS)})"
)

_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM events"


class DuplicateEventIdError(Exception):
    """Raised when an event is stored under an identifier already in use."""


def format_timestamp(value: datetime) -> str:
    """Return ``value`` as the fixed-width UTC text stored in the database."""
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(value: str) -> datetime:
    """Return the UTC datetime held in a stored timestamp."""
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def _to_row(event: Event) -> dict[str, object]:
    """Return the database row representing ``event``."""
    return {
        "id": event.id,
        "source": event.source,
        "event_type": event.event_type,
        "subject": event.subject,
        "occurred_at": format_timestamp(event.occurred_at),
        "severity": event.severity.value,
        "status": None if event.status is None else event.status.value,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "due_at": None if event.due_at is None else format_timestamp(event.due_at),
        "external_id": event.external_id,
        "metadata": json.dumps(event.metadata, sort_keys=True),
        "received_at": format_timestamp(event.received_at),
    }


def _filters(
    source: str | None,
    event_type: str | None,
    severity: EventSeverity | None,
    status: EventStatus | None,
) -> dict[str, object]:
    """Return the column filters as stored values, enums resolved to their text."""
    return {
        "source": source,
        "event_type": event_type,
        "severity": None if severity is None else severity.value,
        "status": None if status is None else status.value,
    }


def _filter_clause(filters: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Return a WHERE clause and its parameters for the given column filters.

    Only entries whose value is not ``None`` become equality conditions, so an
    omitted filter widens the result rather than narrowing it to nothing. The
    column names are fixed by the caller, never taken from request data.
    """
    active = {column: value for column, value in filters.items() if value is not None}
    if not active:
        return "", {}
    clause = " WHERE " + " AND ".join(f"{column} = :{column}" for column in active)
    return clause, active


def _from_row(row: sqlite3.Row) -> Event:
    """Return the event a database row represents."""
    metadata: dict[str, MetadataValue] = json.loads(row["metadata"])
    due_at = row["due_at"]
    return Event(
        id=row["id"],
        source=row["source"],
        event_type=row["event_type"],
        subject=row["subject"],
        occurred_at=parse_timestamp(row["occurred_at"]),
        severity=row["severity"],
        status=row["status"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        due_at=None if due_at is None else parse_timestamp(due_at),
        external_id=row["external_id"],
        metadata=metadata,
        received_at=parse_timestamp(row["received_at"]),
    )


class EventStore:
    """Reads and writes stored operational events.

    A store owns its connection. Access is serialised with a lock because
    FastAPI runs synchronous handlers in a thread pool and a SQLite connection
    is not safe to share across threads unguarded.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = Lock()
        create_schema(connection)

    @classmethod
    def open(cls, database_url: str) -> "EventStore":
        """Open a store against the database named by ``database_url``."""
        return cls(connect(database_url))

    def add(self, event: Event) -> Event:
        """Store ``event`` and return it.

        Raises :class:`DuplicateEventIdError` if the identifier is already
        taken, so that a clash surfaces instead of overwriting stored history.
        """
        with self._lock, self._connection:
            self._insert(event)
        return event

    def add_or_get(self, event: Event) -> Event:
        """Store ``event``, or return the event already stored under its key.

        An event carrying an ``external_id`` is deduplicated per ``source``: if
        the producer has already submitted an event under the same
        ``(source, external_id)``, that stored event is returned unchanged and
        ``event`` is not stored, so a producer that resubmits after a retry or a
        redelivery does not create a duplicate. An event with no ``external_id``
        carries no resubmission key and is always stored.

        The lookup and the insert happen together under the store lock, so two
        concurrent resubmissions of the same key cannot both be stored. The
        returned event is ``event`` itself when it was stored, and the
        previously stored event when the submission was recognised as a
        resubmission; callers can tell the two apart by comparing ``id``.
        """
        with self._lock, self._connection:
            key = self._resubmission_key(event)
            if key is not None:
                stored = self._find_by_key(key)
                if stored is not None:
                    return stored
            self._insert(event)
        return event

    def _insert(self, event: Event) -> None:
        """Insert one event, translating an id clash into ``DuplicateEventIdError``.

        The caller holds the lock and the connection's transaction.
        """
        try:
            self._connection.execute(_INSERT, _to_row(event))
        except sqlite3.IntegrityError as error:
            raise DuplicateEventIdError(
                f"an event with id {event.id!r} is already stored"
            ) from error

    def add_all(self, events: list[Event]) -> list[Event]:
        """Store every event in ``events`` atomically and return them.

        Either all of the events are stored or none are: if any identifier is
        already taken, or clashes with another in the same batch, the whole
        insert is rolled back and :class:`DuplicateEventIdError` is raised, so a
        partly-applied batch never reaches storage. An empty list stores
        nothing and returns an empty list.
        """
        if not events:
            return []
        with self._lock, self._connection:
            try:
                self._connection.executemany(_INSERT, [_to_row(event) for event in events])
            except sqlite3.IntegrityError as error:
                raise DuplicateEventIdError(
                    "the batch contains an event id that is already stored"
                ) from error
        return events

    def add_all_or_get(self, events: list[Event]) -> list[Event]:
        """Store each event, or return the one already held under its key, atomically.

        This is :meth:`add_or_get` applied across a batch under a single lock and
        transaction. An event carrying an ``external_id`` is deduplicated per
        ``source``, matched both against events already stored and against
        earlier events in the same batch: the first submission under a
        ``(source, external_id)`` key is stored, and any later one sharing that
        key returns that event instead of being stored again. An event with no
        ``external_id`` carries no resubmission key and is always stored.

        Returns one event per submitted event, in the submitted order: the newly
        stored event where it was stored, and the previously stored event where
        the submission was recognised as a resubmission, so a caller can tell the
        two apart by comparing ``id``. The new events are stored all-or-nothing:
        if any of their identifiers clashes with stored history the whole insert
        is rolled back and :class:`DuplicateEventIdError` is raised, so a batch
        never reaches storage partly applied. An empty list stores nothing.
        """
        if not events:
            return []
        resolved: list[Event] = []
        to_insert: list[Event] = []
        with self._lock, self._connection:
            seen: dict[tuple[str, str], Event] = {}
            for event in events:
                key = self._resubmission_key(event)
                if key is not None:
                    earlier = seen.get(key)
                    if earlier is not None:
                        resolved.append(earlier)
                        continue
                    stored = self._find_by_key(key)
                    if stored is not None:
                        seen[key] = stored
                        resolved.append(stored)
                        continue
                    seen[key] = event
                resolved.append(event)
                to_insert.append(event)
            try:
                self._connection.executemany(_INSERT, [_to_row(event) for event in to_insert])
            except sqlite3.IntegrityError as error:
                raise DuplicateEventIdError(
                    "the batch contains an event id that is already stored"
                ) from error
        return resolved

    @staticmethod
    def _resubmission_key(event: Event) -> tuple[str, str] | None:
        """Return the ``(source, external_id)`` key an event deduplicates on, if any."""
        return (event.source, event.external_id) if event.external_id else None

    def _find_by_key(self, key: tuple[str, str]) -> Event | None:
        """Return the earliest event stored under a resubmission key, or ``None``.

        The caller holds the store lock. The first submission under a key wins, so
        the oldest match is returned when more than one somehow shares the key.
        """
        source, external_id = key
        row = self._connection.execute(
            f"{_SELECT} WHERE source = :source AND external_id = :external_id "
            "ORDER BY received_at, id LIMIT 1",
            {"source": source, "external_id": external_id},
        ).fetchone()
        return None if row is None else _from_row(row)

    def get(self, event_id: str) -> Event | None:
        """Return the stored event with ``event_id``, or ``None`` if there is none."""
        with self._lock:
            row = self._connection.execute(f"{_SELECT} WHERE id = :id", {"id": event_id}).fetchone()
        return None if row is None else _from_row(row)

    def list_events(
        self,
        *,
        source: str | None = None,
        event_type: str | None = None,
        severity: EventSeverity | None = None,
        status: EventStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Return stored events, most recently occurred first.

        Each supplied filter narrows the result to events whose column matches
        it exactly; omitted filters do not narrow it. ``limit`` and ``offset``
        page through the matches, so successive pages of the same filters walk
        the whole result without gaps or repeats.

        Ties on ``occurred_at`` are broken by ``received_at`` and then ``id`` so
        that the order is stable across calls, which is what makes paging safe.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clause, params = _filter_clause(_filters(source, event_type, severity, status))
        params["limit"] = limit
        params["offset"] = offset
        with self._lock:
            rows = self._connection.execute(
                f"{_SELECT}{clause} "
                "ORDER BY occurred_at DESC, received_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset",
                params,
            ).fetchall()
        return [_from_row(row) for row in rows]

    def count(
        self,
        *,
        source: str | None = None,
        event_type: str | None = None,
        severity: EventSeverity | None = None,
        status: EventStatus | None = None,
    ) -> int:
        """Return how many stored events match the given filters.

        With no filters this is the total number of stored events; otherwise it
        counts every match, independent of any pagination, so a caller can tell
        how many pages a filtered listing spans.
        """
        clause, params = _filter_clause(_filters(source, event_type, severity, status))
        with self._lock:
            return int(
                self._connection.execute(f"SELECT COUNT(*) FROM events{clause}", params).fetchone()[
                    0
                ]
            )

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
