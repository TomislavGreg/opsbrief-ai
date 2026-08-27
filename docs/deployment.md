# Deployment

How to run OpsBrief AI outside a development checkout. It is a single Python
process: one FastAPI application served by uvicorn, backed by a SQLite file. There
is no message broker, no background worker and no second service to coordinate, so
deployment is deliberately simple. This document covers the container image, the
configuration it reads, where its data lives, and the operational concerns (health
checks, a reverse proxy, upgrades) a real deployment has to settle.

It describes what exists today. Where a concern is intentionally left to the
surrounding environment (TLS, read-side access control), that is called out rather
than implied.

## What you are deploying

- One process: `uvicorn opsbrief.main:app`, listening on a TCP port (8000 by
  default in the image).
- One SQLite database file, holding the stored events and incidents. It is created
  on first use.
- No external services. The only AI provider implemented so far is the
  deterministic fake, which needs no model, no key and no network, so a default
  deployment makes no outbound calls.

Because the state is a single file, a deployment is stateful in exactly one place.
Everything else (the code, the settings) is disposable and rebuilt from the image
and the environment.

## Container image

The repository ships a `Dockerfile` that builds the service into
`python:3.12-slim`, installs the package, and runs uvicorn as an unprivileged
user. The image declares a health check against `/health`, so an orchestrator can
tell when the API is ready rather than merely running.

Build and run it directly:

```bash
docker build -t opsbrief-ai .
docker run --rm -p 8000:8000 --env-file .env opsbrief-ai
```

The image binds `0.0.0.0:8000` inside the container. Publish it to whatever host
port the environment expects (`-p 8000:8000` above maps host 8000 to container
8000).

### With Compose

`compose.yaml` runs the same image as a single `api` service and passes `.env`
through as `OPSBRIEF_`-prefixed settings. It is written for a local run and
restarts unless stopped:

```bash
cp .env.example .env      # then edit for the target environment
docker compose up -d --build
docker compose ps         # reports healthy once /health answers
docker compose logs -f api
```

For a persistent deployment, mount the database file (see
[Persistence](#persistence)) so the stored events and incidents survive a
container replacement. The bundled `compose.yaml` does not mount a volume, so its
database is scoped to the container's lifetime, which is fine for a demo and not
for anything you want to keep.

## Running without a container

The service is an ordinary Python package, so a host with Python 3.12 or newer can
run it without Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .                 # the runtime dependencies only, not ".[dev]"
uvicorn opsbrief.main:app --host 0.0.0.0 --port 8000
```

Install the base package (`pip install .`), not the `dev` extra, in production: the
extra pulls in the test and lint tooling, which a running service does not need.
Settings are read from the environment (and from a `.env` file in the working
directory when one is present), exactly as in the container.

The same install exposes the `opsbrief` command, which prints the current daily
brief over the configured database without starting the server. It reads the same
settings, so it is a convenient way to confirm a deployment's database and provider
are wired correctly:

```bash
opsbrief --format json
```

## Configuration

All settings are read from environment variables prefixed with `OPSBRIEF_`,
falling back to a `.env` file in the working directory when one is present.
`.env.example` lists them with inline notes; copy it to `.env` and edit, or set the
variables directly in the environment. Every setting has a default, so the service
starts with no configuration, but several defaults are meant for development and
should be set deliberately for a real deployment.

| Variable | Default | Notes |
|----------|---------|-------|
| `OPSBRIEF_APP_NAME` | `OpsBrief AI` | Service name reported by `/health`. |
| `OPSBRIEF_ENVIRONMENT` | `development` | Free-form environment label reported by `/health`. Set to `production` (or your own label) so a reader can tell instances apart. |
| `OPSBRIEF_LOG_LEVEL` | `info` | Log level label. |
| `OPSBRIEF_DATABASE_URL` | `sqlite:///./opsbrief.db` | The SQLite database. Only `sqlite:///` URLs are accepted. Point this at a path on durable storage (see [Persistence](#persistence)). |
| `OPSBRIEF_AI_PROVIDER` | `fake` | The AI provider. Only `fake` is implemented; an unknown name is refused at startup. |
| `OPSBRIEF_REDACT_METADATA_KEYS` | empty | Extra metadata key terms whose values are masked before storage, comma-separated. Adds to the built-in set. |
| `OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS` | empty | Event fields held back from the material a model is shown, comma-separated. Chosen from `source`, `event_type`, `subject`, `severity`, `status`, `occurred_at`. |
| `OPSBRIEF_WEBHOOK_SECRET` | empty | Shared secret for HMAC verification of `POST /webhooks/events`. Unset disables the webhook (404); when set it must be at least 16 characters. |
| `OPSBRIEF_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` | `300` | Allowed clock skew, in seconds, for the signed webhook timestamp. Must be positive. |

A misconfiguration fails loudly at startup rather than weakening the service
silently: a database URL that is not `sqlite:///`, an unknown AI provider, a
webhook secret shorter than 16 characters, a non-positive skew tolerance, or an
excluded field that is not one of the renderable set all raise at wiring time. This
is deliberate, so a bad setting stops a deploy rather than producing empty briefs
or unauthenticated writes later.

Settings are read once and cached for the life of the process, so a change to the
environment takes effect on the next restart, not live.

### Secrets

The only secret the service holds is `OPSBRIEF_WEBHOOK_SECRET`, and only when the
webhook is in use. Supply it through the environment (an orchestrator secret, a
secrets manager, a `.env` file kept out of version control), never in the image or
the repository. `.env` is git-ignored and excluded from the Docker build context,
so it is not baked into an image. When the webhook is not used, leave the secret
unset and the route stays disabled.

## Persistence

The service keeps its state in one SQLite file, named by `OPSBRIEF_DATABASE_URL`.
The file and its parent directory are created on first use, so no migration or
setup step is needed for a fresh deployment. All that a deployment has to do is put
that file on storage that outlives the process.

In a container, that means a mounted volume. Point the database at a path inside
the mount and mount a host directory or named volume there:

```bash
docker run --rm -p 8000:8000 \
  -e OPSBRIEF_DATABASE_URL=sqlite:////data/opsbrief.db \
  -v opsbrief-data:/data \
  opsbrief-ai
```

Note the four slashes: `sqlite:////data/opsbrief.db` is an absolute path
(`/data/opsbrief.db`), while `sqlite:///./opsbrief.db` is relative to the working
directory. The mounted directory must be writable by the image's `opsbrief` user
(uid 1000).

The equivalent in Compose is a named volume:

```yaml
services:
  api:
    # ... as in compose.yaml ...
    environment:
      OPSBRIEF_DATABASE_URL: sqlite:////data/opsbrief.db
    volumes:
      - opsbrief-data:/data

volumes:
  opsbrief-data:
```

### Backups

Because the state is a single file, a backup is a copy of that file. SQLite writes
in place, so copy it while the service is quiescent, or use SQLite's own
`.backup`/`VACUUM INTO` to take a consistent snapshot of a live database:

```bash
sqlite3 /data/opsbrief.db ".backup '/backups/opsbrief-$(date +%F).db'"
```

There is one process and one writer, so there is no coordination to do beyond
copying the file. Restoring is the reverse: stop the service, put the file back,
start it.

### Concurrency

A single SQLite connection is shared per store and guarded by a lock, because
SQLite is not safe to share across the threads FastAPI runs synchronous handlers
in. This makes the service correct on one process but means it is designed to run
as one process against one database file. Do not run several replicas against the
same SQLite file expecting them to coordinate: SQLite is a single-writer store, and
horizontal scaling is out of scope until a concrete need makes a different store
worth the weight (see the design constraints in the README's Architecture section).

## Health checks

`GET /health` answers `200` with the service name, version and environment once the
application is serving. It touches no external state, so it is a liveness and
readiness probe in one: a `200` means the process is up and answering.

```bash
curl http://127.0.0.1:8000/health
```

The container image already wires this into a Docker `HEALTHCHECK`. For an
orchestrator, point both the liveness and readiness probes at `/health`. There is
no separate startup dependency to wait on: the database is opened when the
application starts, so a `200` from `/health` means the store is open too.

## Running behind a reverse proxy

The service speaks plain HTTP and does not terminate TLS. A production deployment
puts it behind a reverse proxy (nginx, Caddy, a cloud load balancer) that
terminates TLS and forwards to the uvicorn port. Two points matter:

- **TLS is the proxy's job.** Terminate HTTPS at the proxy and forward over the
  internal network to the container port. The service has no TLS configuration of
  its own.
- **The webhook signature is over the raw body.** The HMAC is computed over the
  exact request bytes, so a proxy must forward the body unmodified. Do not enable
  anything that rewrites, re-encodes or re-compresses the request body between the
  sender and the service, or the signature will not verify. Buffering and plain
  forwarding are fine.

The read endpoints are unauthenticated by design (see the
[integration contract](integration-contract.md)). A deployment that needs to
restrict who can read briefs and events enforces that at the proxy or the network
boundary; the service itself does not authenticate reads.

## Upgrades

An upgrade replaces the code, not the data. Build or pull the new image, then
restart the service against the same database file; the stored events and incidents
are read by the new version unchanged. The database schema is created on first use
and additive changes carry their own handling, so a rolling replacement of a single
instance is the normal path:

```bash
docker compose pull        # or: docker compose build --pull
docker compose up -d
```

There is one process, so an upgrade is a brief restart rather than a coordinated
rollout. Take a backup first (above) if the release is significant, so a rollback is
a matter of restoring the file and running the previous image.

Generated output is versioned so a change is visible to a consumer: a daily brief
and an incident summary each carry an `output_version` and a `prompt_version`, which
change when the structure or the wording does. A platform reading generated output
across an upgrade can branch on those rather than being surprised by a change (see
the [integration contract](integration-contract.md)).

## Security posture

The deployment concerns above sit alongside the project's security policy in
[`../SECURITY.md`](../SECURITY.md), which records how to report a vulnerability and
the design choices that keep the service safe. In short, for a deployment: put the
service behind a TLS-terminating proxy, keep the webhook secret in the environment
and out of the image, restrict read access at the network boundary if you need to,
run the container as the unprivileged user it already defaults to, and scan
dependencies with `pip-audit` before a release. This is a public project that must
never hold private or personal data, so keep sensitive detail in event `metadata`,
where redaction masks it before storage.
