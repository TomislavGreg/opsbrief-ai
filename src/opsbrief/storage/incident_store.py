"""Storage of tracked incidents in SQLite.

An incident is a stateful record: it is declared once and then moves through
its lifecycle, gaining and shedding evidence as the situation develops. Unlike
an event, which is written once and never changes, an incident is stored on
declaration and saved again on every change, so the store separates ``add`` (a
new declaration) from ``save`` (a change to one that already exists).
"""

import json
import sqlite3
from threading import Lock
from types import TracebackType

from opsbrief.incidents import Incident, IncidentSeverity, IncidentStatus
from opsbrief.storage.database import connect, create_schema
from opsbrief.storage.event_store import format_timestamp, parse_timestamp

_COLUMNS = (
    "id",
    "title",
    "status",
    "severity",
    "opened_at",
    "updated_at",
    "resolved_at",
    "resolution_note",
    "event_ids",
)

_INSERT = (
    f"INSERT INTO incidents ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(':' + column for column in _COLUMNS)})"
)

_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM incidents"

#: The columns a save may change: everything but the identifier, which is fixed
#: when the incident is declared.
_UPDATABLE = tuple(column for column in _COLUMNS if column != "id")

_UPDATE = (
    f"UPDATE incidents SET {', '.join(f'{column} = :{column}' for column in _UPDATABLE)} "
    "WHERE id = :id"
)


class DuplicateIncidentIdError(Exception):
    """Raised when an incident is stored under an identifier already in use."""


class IncidentNotFoundError(Exception):
    """Raised when a save targets an incident that is not stored.

    ``save`` records a change to an incident that was already declared, so it
    refuses to write one that does not exist rather than silently inserting it,
    which would resurrect a record a caller believed was there.
    """


def _to_row(incident: Incident) -> dict[str, object]:
    """Return the database row representing ``incident``."""
    return {
        "id": incident.id,
        "title": incident.title,
        "status": incident.status.value,
        "severity": incident.severity.value,
        "opened_at": format_timestamp(incident.opened_at),
        "updated_at": format_timestamp(incident.updated_at),
        "resolved_at": (
            None if incident.resolved_at is None else format_timestamp(incident.resolved_at)
        ),
        "resolution_note": incident.resolution_note,
        "event_ids": json.dumps(incident.event_ids),
    }


def _from_row(row: sqlite3.Row) -> Incident:
    """Return the incident a database row represents."""
    resolved_at = row["resolved_at"]
    return Incident(
        id=row["id"],
        title=row["title"],
        status=row["status"],
        severity=row["severity"],
        opened_at=parse_timestamp(row["opened_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
        resolved_at=None if resolved_at is None else parse_timestamp(resolved_at),
        resolution_note=row["resolution_note"],
        event_ids=json.loads(row["event_ids"]),
    )


class IncidentStore:
    """Reads and writes stored incidents.

    Like :class:`~opsbrief.storage.event_store.EventStore`, the store owns its
    connection and serialises access with a lock, because FastAPI runs
    synchronous handlers in a thread pool and a SQLite connection is not safe to
    share across threads unguarded.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = Lock()
        create_schema(connection)

    @classmethod
    def open(cls, database_url: str) -> "IncidentStore":
        """Open a store against the database named by ``database_url``."""
        return cls(connect(database_url))

    def add(self, incident: Incident) -> Incident:
        """Store a newly declared ``incident`` and return it.

        Raises :class:`DuplicateIncidentIdError` if the identifier is already
        taken, so a clash surfaces instead of overwriting a tracked incident.
        """
        with self._lock, self._connection:
            try:
                self._connection.execute(_INSERT, _to_row(incident))
            except sqlite3.IntegrityError as error:
                raise DuplicateIncidentIdError(
                    f"an incident with id {incident.id!r} is already stored"
                ) from error
        return incident

    def save(self, incident: Incident) -> Incident:
        """Persist a change to an incident already stored and return it.

        Every column but the identifier is overwritten with the incident's
        current state, so a transition or an event link is recorded whole.
        Raises :class:`IncidentNotFoundError` if no incident carries the
        identifier, so a save never silently declares a fresh one.
        """
        with self._lock, self._connection:
            cursor = self._connection.execute(_UPDATE, _to_row(incident))
            if cursor.rowcount == 0:
                raise IncidentNotFoundError(f"no incident is stored under id {incident.id!r}")
        return incident

    def get(self, incident_id: str) -> Incident | None:
        """Return the stored incident with ``incident_id``, or ``None`` if there is none."""
        with self._lock:
            row = self._connection.execute(
                f"{_SELECT} WHERE id = :id", {"id": incident_id}
            ).fetchone()
        return None if row is None else _from_row(row)

    def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Incident]:
        """Return stored incidents, most recently opened first.

        A ``status`` filter narrows the result to incidents in that state, and a
        ``severity`` filter to incidents of that severity; omitting a filter does
        not narrow the result. ``limit`` and ``offset`` page through the matches.
        Ties on ``opened_at`` are broken by ``id`` so the order is stable across
        calls, which is what makes paging safe.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clause, params = _where(_filters(status, severity))
        params["limit"] = limit
        params["offset"] = offset
        with self._lock:
            rows = self._connection.execute(
                f"{_SELECT}{clause} ORDER BY opened_at DESC, id DESC LIMIT :limit OFFSET :offset",
                params,
            ).fetchall()
        return [_from_row(row) for row in rows]

    def count(
        self,
        *,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
    ) -> int:
        """Return how many stored incidents match the given filters.

        With no filter this is the total number of stored incidents; otherwise
        it counts every match independent of pagination, so a caller can tell
        how many pages a filtered listing spans. It takes the same filters as
        :meth:`list_incidents`, so a filtered listing and its total stay in step.
        """
        clause, params = _where(_filters(status, severity))
        with self._lock:
            return int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM incidents{clause}", params
                ).fetchone()[0]
            )

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "IncidentStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _filters(
    status: IncidentStatus | None,
    severity: IncidentSeverity | None,
) -> dict[str, object]:
    """Return the column filters as stored values, enums resolved to their text."""
    return {
        "status": None if status is None else status.value,
        "severity": None if severity is None else severity.value,
    }


def _where(filters: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Return a WHERE clause and its parameters for the given filters.

    Each filter whose value is not ``None`` becomes an ``=`` condition; an
    omitted filter widens the result rather than narrowing it to nothing. The
    column names are fixed by the caller, never taken from request data, and only
    the values are bound as parameters.
    """
    conditions: list[str] = []
    params: dict[str, object] = {}
    for column, value in filters.items():
        if value is not None:
            conditions.append(f"{column} = :{column}")
            params[column] = value
    if not conditions:
        return "", {}
    return " WHERE " + " AND ".join(conditions), params
