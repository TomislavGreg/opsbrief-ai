"""Whole-history and paged reads come from one coherent snapshot (AI-098).

``read_all_events`` once gathered the history a page at a time, taking the store
lock separately for each page. A write landing between two of those page reads
shifted the newest-first order under the reader, so the read could return a row
twice and omit the event that had just been inserted. It now reads the whole
matching history in one query under a single hold of the store lock, so a
concurrent write lands wholly before or after the read and the snapshot stays
coherent. ``list_page`` reads a page and its total the same way, so within one
request the total agrees with the page.

The concurrency tests share one store across threads and release them together
with a :class:`threading.Barrier`, so the read and the write genuinely contend
without sleeps. The guarantee is scoped to the single shared store the service
runs, as the incident concurrency tests are: separate connections to the same
file are not serialised by that lock and are out of scope here.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.events import Event, EventInput
from opsbrief.services.history import read_all_events
from opsbrief.storage import EventStore

START = datetime(2026, 7, 29, 9, 30, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[EventStore]:
    """Return a store backed by a throwaway in-memory database shared by the test."""
    with EventStore.open("sqlite:///:memory:") as store:
        yield store


def make_event(index: int) -> Event:
    """Return an event occurring ``index`` minutes after START, uniquely ordered.

    Distinct occurrence times give a total newest-first order, so a complete
    read can be checked against the exact expected sequence.
    """
    return Event.from_input(
        EventInput(
            source="rostering",
            event_type="shift.unfilled",
            subject=f"event {index}",
            occurred_at=START + timedelta(minutes=index),
        )
    )


def add_bulk(store: EventStore, count: int, *, start: int = 0) -> list[Event]:
    """Store ``count`` events occurring in ascending order and return them."""
    events = [make_event(index) for index in range(start, start + count)]
    store.add_all(events)
    return events


def run_together(operations: list[Callable[[], object]]) -> list[object]:
    """Run ``operations`` on separate threads released together by one barrier."""
    barrier = threading.Barrier(len(operations))
    results: list[object] = [None] * len(operations)

    def worker(index: int, operation: Callable[[], object]) -> None:
        barrier.wait()
        results[index] = operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(worker, index, op) for index, op in enumerate(operations)]
        for future in futures:
            future.result()
    return results


def test_read_all_events_returns_every_event_newest_first(store: EventStore) -> None:
    events = add_bulk(store, 5)

    result = read_all_events(store)

    assert [event.id for event in result] == [event.id for event in reversed(events)]


def test_read_all_events_on_an_empty_store_is_empty(store: EventStore) -> None:
    assert read_all_events(store) == []


@pytest.mark.parametrize("count", [499, 500, 501, 1000, 1001])
def test_read_all_events_reads_past_the_former_page_boundary(store: EventStore, count: int) -> None:
    # The history was formerly gathered 500 rows at a time, so exact multiples and
    # their neighbours are where a page walk could cap the read or repeat a row.
    events = add_bulk(store, count)

    ids = [event.id for event in read_all_events(store)]

    assert len(ids) == count
    assert len(set(ids)) == count
    assert ids == [event.id for event in reversed(events)]


def test_read_all_events_snapshot_is_coherent_under_concurrent_insert(store: EventStore) -> None:
    # More than the former 500-row page, so the old paged read took the lock twice
    # and a write could slip between the pages; the single-query read cannot.
    existing = add_bulk(store, 600)
    committed = {event.id for event in existing}

    for index in range(600, 630):
        new_event = make_event(index)

        snapshot, _ = run_together(
            [
                lambda: read_all_events(store),
                lambda event=new_event: store.add(event),
            ]
        )

        ids = [event.id for event in snapshot]
        assert len(ids) == len(set(ids))
        seen = set(ids)
        # One coherent view: everything already committed, and the new event either
        # wholly present (the read saw the write) or wholly absent (it did not).
        assert seen == committed or seen == committed | {new_event.id}
        committed.add(new_event.id)


def test_list_page_returns_the_page_and_the_total(store: EventStore) -> None:
    events = add_bulk(store, 5)

    page, total = store.list_page(limit=2, offset=0)

    assert total == 5
    assert [event.id for event in page] == [event.id for event in reversed(events)][:2]


def test_list_page_reads_page_and_total_from_one_snapshot(store: EventStore) -> None:
    add_bulk(store, 5)
    committed = 5

    for index in range(1000, 1030):
        new_event = make_event(index)

        result, _ = run_together(
            [
                lambda: store.list_page(limit=500, offset=0),
                lambda event=new_event: store.add(event),
            ]
        )
        page, total = result

        page_ids = {event.id for event in page}
        # The limit exceeds the match count, so the page holds every match: its
        # size equals the total, and the new event is in the page exactly when the
        # total counted it. A page and total from different snapshots could not
        # both hold.
        assert len(page) == total
        assert (new_event.id in page_ids) == (total == committed + 1)
        committed += 1
