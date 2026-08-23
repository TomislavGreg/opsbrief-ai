# Security Policy

OpsBrief AI is a public project that turns operational events into briefs, risk
warnings and incident summaries. This document explains how to report a
vulnerability, which versions are supported, how the project is designed to stay
safe, and how to scan its dependencies for known advisories.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub's "Report a
vulnerability" flow on the Security tab, rather than opening a public issue. A
private report gives us a chance to fix a problem before it is widely known.

Please include enough to reproduce the issue: the affected endpoint or function,
the input that triggers it, and what you observed. We aim to acknowledge a
report within a few working days and to keep you updated while we work on a fix.

Do not include real credentials, customer data or personal data in a report.
This is a public project, and sample data must always be synthetic.

## Supported versions

The project is pre-1.0 and moves forward on `main`. Security fixes land on
`main` and are not backported to earlier tags. Run the latest release, or track
`main`, to receive them.

| Version | Supported |
|---------|-----------|
| `main`  | Yes |
| Older tags | No |

## Security design

Several design choices keep the service safe by construction rather than by
convention:

- **Risk detection is deterministic.** Rules, not a language model, decide what
  counts as a risk. A model only phrases a picture the service has already
  assembled, so a manipulated or malfunctioning model cannot invent a risk,
  change a severity or move an incident.
- **Model output is untrusted.** Text a provider returns is treated as external
  data: it is collapsed to a single line and truncated to a bounded length
  before it is kept, so injected formatting or unbounded text cannot shape a
  brief or a summary.
- **Input is validated.** Every request and response body is a Pydantic model.
  Unknown fields are rejected, timestamps without an offset are refused,
  batches and metadata are bounded, and query parameters are typed, so a
  malformed payload fails loudly instead of being partly applied.
- **Queries are parameterized.** The SQLite layer binds every value as a
  parameter and never builds SQL from request data, so a crafted field cannot
  reach the database as code.
- **Sensitive metadata is redacted.** A metadata value whose key names a
  sensitive term is masked with a visible `[redacted]` marker before the event
  is stored, so it never reaches the database or a later read. The term set is
  widened per deployment through `OPSBRIEF_REDACT_METADATA_KEYS`.
- **Model context is narrow.** A deployment can hold named event fields back
  from the material a model is shown through `OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS`,
  on top of what redaction masks at storage.
- **No secrets in the repository.** `.env` is ignored and `.env.example` holds
  placeholders only. Configuration comes from `OPSBRIEF_`-prefixed environment
  variables.

## Dependency scanning

Dependencies are kept small and are scanned for known advisories with
[`pip-audit`](https://pypi.org/project/pip-audit/), which ships in the project's
`dev` extra. After installing the development dependencies, scan the environment
with:

```bash
pip install -e ".[dev]"
pip-audit
```

`pip-audit` checks the installed packages against the Python advisory database
and reports any package with a known vulnerability and the version that fixes
it. Run it before a release and whenever a dependency is added or bumped. When
it reports a finding, upgrade the affected package to a fixed version and rerun
the scan.
