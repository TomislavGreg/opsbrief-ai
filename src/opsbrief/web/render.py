"""Rendering the dashboard view to a self-contained HTML page.

Server-rendered and dependency-free: the page is assembled from the standard
library, with a small inline stylesheet so it needs no separate asset request.
Every dynamic value is escaped through :func:`html.escape` as it is placed, so
an operator-supplied setting (the service name, the environment label) cannot
inject markup. The rendering is a pure function of the view, so the same view
always produces the same page.
"""

from html import escape

from opsbrief.web.schema import DashboardLink, DashboardView, RecentEventRow

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  line-height: 1.5;
  color: #1a1a1a;
  background: #f5f5f5;
}
main { max-width: 48rem; margin: 0 auto; padding: 2rem 1.25rem 3rem; }
header h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
.identity { color: #555; margin: 0 0 1.5rem; }
.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 0.5rem;
  background: #e0e7ff;
  color: #3730a3;
  font-size: 0.8rem;
  font-weight: 600;
}
.lead { margin: 0 0 1.5rem; }
section.panel { margin: 0 0 2rem; }
section.panel h2 { font-size: 1.15rem; margin: 0 0 0.5rem; }
.panel .caption { color: #555; font-size: 0.9rem; margin: 0 0 0.75rem; }
.panel .empty {
  background: #fff;
  border: 1px solid #e2e2e2;
  border-radius: 0.6rem;
  padding: 0.75rem 1rem;
  color: #555;
  margin: 0;
}
.events {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e2e2e2;
  border-radius: 0.6rem;
  overflow: hidden;
  font-size: 0.9rem;
}
.events th, .events td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #eee;
  vertical-align: top;
}
.events th { background: #fafafa; font-size: 0.8rem; color: #555; }
.events tr:last-child td { border-bottom: none; }
.events td.subject { width: 40%; }
.events time { color: #555; white-space: nowrap; }
ul.links { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.75rem; }
ul.links li {
  background: #fff;
  border: 1px solid #e2e2e2;
  border-radius: 0.6rem;
  padding: 0.75rem 1rem;
}
ul.links a { font-weight: 600; text-decoration: none; color: #1d4ed8; }
ul.links a:hover { text-decoration: underline; }
ul.links p { margin: 0.25rem 0 0; color: #555; font-size: 0.95rem; }
footer { margin-top: 2rem; color: #777; font-size: 0.85rem; }
""".strip()


def _render_event_row(row: RecentEventRow) -> str:
    """Render one recent-event table row, escaping every field."""
    status = escape(row.status) if row.status else "&mdash;"
    return (
        "<tr>"
        f"<td><time>{escape(row.occurred_at)}</time></td>"
        f"<td>{escape(row.source)}</td>"
        f"<td>{escape(row.event_type)}</td>"
        f'<td class="subject">{escape(row.subject)}</td>'
        f"<td>{escape(row.severity)}</td>"
        f"<td>{status}</td>"
        "</tr>"
    )


def _render_recent_events(view: DashboardView) -> str:
    """Render the recent-events panel: a bounded, newest-first table.

    On an empty store the panel says so plainly rather than rendering an empty
    table. When the store holds more events than the panel shows, a caption names
    how many of the total are on view, mirroring the way a brief context reports a
    bounded recent view.
    """
    if not view.recent_events:
        return (
            '<section class="panel">'
            "<h2>Recent events</h2>"
            '<p class="empty">No operational events have been recorded yet.</p>'
            "</section>"
        )
    shown = len(view.recent_events)
    if view.total_events > shown:
        caption = f"Showing the {shown} most recent of {view.total_events} events."
    else:
        caption = f"The {shown} most recent events." if shown != 1 else "The most recent event."
    rows = "\n".join(_render_event_row(row) for row in view.recent_events)
    return (
        '<section class="panel">'
        "<h2>Recent events</h2>"
        f'<p class="caption">{escape(caption)}</p>'
        '<table class="events">'
        "<thead><tr>"
        "<th>Occurred</th><th>Source</th><th>Type</th>"
        "<th>Subject</th><th>Severity</th><th>Status</th>"
        "</tr></thead>"
        f"<tbody>\n{rows}\n</tbody>"
        "</table>"
        "</section>"
    )


def _render_link(link: DashboardLink) -> str:
    """Render one navigation card, escaping every field."""
    return (
        "<li>"
        f'<a href="{escape(link.href, quote=True)}">{escape(link.label)}</a>'
        f"<p>{escape(link.description)}</p>"
        "</li>"
    )


def render_dashboard_page(view: DashboardView) -> str:
    """Return the dashboard as a complete HTML document.

    The shell shows the running service's identity and links into the existing
    JSON endpoints. It is a face for the API, not a second source of truth: the
    later dashboard views render some of these panels inline, and this page
    states plainly that it does so.
    """
    recent_events = _render_recent_events(view)
    links = "\n".join(_render_link(link) for link in view.links)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(view.service_name)} dashboard</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<header>
<h1>{escape(view.service_name)}</h1>
<p class="identity">Operations dashboard <span class="badge">{escape(view.environment)}</span></p>
</header>
<p class="lead">Turn structured operational events into daily briefs, risk warnings and
incident summaries. This dashboard is a server-rendered face over the existing API;
the recent-events panel is rendered inline, and the links below reach the other JSON
endpoints.</p>
{recent_events}
<ul class="links">
{links}
</ul>
<footer>Version {escape(view.version)}</footer>
</main>
</body>
</html>
"""
