"""Seed a store with synthetic demo data.

Populate an empty store with a coherent, made-up day of operations so a public
demo shows a full dashboard (recent events, active risks, a daily brief and a
tracked incident with a timeline) without anyone posting events first. The data
is the sports-operations match-day fixture and the worked quality-control
incident declared over it, both deterministic and carrying no private, customer
or personal data, in line with the project's data policy.

Seeding is guarded and idempotent: it runs only when the event store is empty, so
it never mixes synthetic data into a store that already holds real events and
never seeds a second time across restarts.
"""

from opsbrief.samples import build_sample_qc_incident, load_sample_match_stored_events
from opsbrief.storage import EventStore, IncidentStore


def seed_demo_data(event_store: EventStore, incident_store: IncidentStore) -> bool:
    """Seed synthetic demo data into the stores when the event store is empty.

    Stores the match-day fixture as events and the worked QC incident declared
    over them, so a demo has recent events, active risks, a daily brief and a
    tracked incident with a timeline to show. It runs only when the event store
    holds no events, so a store that already carries real data is left untouched
    and a restart does not seed the same data twice. The incident is added only
    when one under its id is not already stored, so the seed stays idempotent even
    if the two stores fall out of step.

    Returns ``True`` when the data was seeded and ``False`` when the event store
    already held events and nothing was written.
    """
    if event_store.count() > 0:
        return False
    event_store.add_all(load_sample_match_stored_events())
    incident = build_sample_qc_incident()
    if incident_store.get(incident.id) is None:
        incident_store.add(incident)
    return True


__all__ = ["seed_demo_data"]
