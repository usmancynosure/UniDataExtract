"""Rich rendering for the CLI: a clean, scannable view of one extraction result.

Pure presentation — nothing here touches the network or the models' logic, so the
pipeline stays usable as a plain library and this can be swapped for any frontend.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .pipeline import PipelineResult


def banner() -> Panel:
    title = Text("UniCompanion", style="bold magenta")
    subtitle = Text("Admissions & Tuition ETL — domain in, structured data out", style="dim")
    return Panel(Text.assemble(title, "\n", subtitle), border_style="magenta", expand=False)


def _money(item) -> str:
    if item.cost is None:
        return "[dim]—[/dim]"
    return f"{item.currency or 'USD'} {item.cost:,}"


def _or_dash(value) -> str:
    return str(value) if value not in (None, "") else "[dim]—[/dim]"


def render_result(console: Console, result: PipelineResult) -> None:
    """Print a full, human-readable summary of one PipelineResult."""
    data = result.data
    ov = data.overview
    method_color = "green" if result.method == "gemini" else "yellow"
    name = (ov.university_name if ov else None) or result.domain
    header = Text.assemble(
        (name, "bold"), ("   "), (result.domain, "dim"), ("   via "), (result.method, method_color)
    )
    console.print(Panel(header, border_style=method_color, expand=False))

    _render_overview(console, data)
    _render_tuition(console, data)
    _render_deadlines(console, data)
    _render_sources(console, data)
    _render_quality(console, result)
    console.print()


def _render_quality(console: Console, result: PipelineResult) -> None:
    q = result.quality
    conf = q.confidence.get("overall", "n/a")
    conf_color = {"high": "green", "medium": "yellow", "low": "red"}.get(conf, "white")
    head = Text.assemble(
        ("confidence ", "dim"), (conf, conf_color),
        ("   grounded ", "dim"), (q.confidence.get("tuition_grounded", "—"), "white"),
        ("   issues ", "dim"), (str(q.issue_count), "red" if q.issue_count else "green"),
        ("   time ", "dim"), (f"{result.elapsed_seconds:.1f}s", "white"),
    )
    lines = [head]
    if q.missing_fields:
        lines.append(Text(f"missing: {', '.join(q.missing_fields)}", style="yellow"))
    if q.invalid_dates:
        lines.append(Text(f"invalid dates: {', '.join(q.invalid_dates[:3])}", style="yellow"))
    if q.duplicates:
        lines.append(Text(f"duplicates: {len(q.duplicates)}", style="yellow"))
    if q.field_sources:
        attr = "; ".join(f"{k}→{len(v)} src" for k, v in q.field_sources.items())
        lines.append(Text(f"attribution: {attr}", style="dim"))
    console.print(Panel(Text("\n").join(lines), title="Quality & confidence", border_style="dim", expand=False))


def _render_overview(console: Console, data) -> None:
    ov = data.overview
    if ov is None:
        return
    loc = ov.location
    con = ov.contact
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    if loc:
        place = ", ".join(x for x in [loc.city, loc.state, loc.postal_code, loc.country] if x)
        t.add_row("Location", _or_dash(place))
    if con:
        t.add_row("Phone", _or_dash(con.phone))
        t.add_row("Email", _or_dash(con.email))
    console.print(Panel(t, title="Overview", border_style="blue", expand=False))


def _render_tuition(console: Console, data) -> None:
    if not data.tuition_breakdown:
        console.print(Panel("[dim]No tuition figures extracted[/dim]", border_style="green", expand=False))
        return
    table = Table(title="Tuition / Cost", title_style="bold green", header_style="green")
    table.add_column("Fee type")
    table.add_column("Cost", justify="right")
    for item in data.tuition_breakdown:
        table.add_row(_or_dash(item.fee_type), _money(item))
    console.print(table)


def _render_deadlines(console: Console, data) -> None:
    if not data.admission_deadlines:
        return
    table = Table(title="Admission Deadlines", title_style="bold cyan", header_style="cyan")
    table.add_column("Type")
    table.add_column("Date")
    table.add_column("Notes")
    for d in data.admission_deadlines:
        dtype = d.deadline_type.value if d.deadline_type else "—"
        table.add_row(dtype, _or_dash(d.deadline_date), _or_dash(d.notes))
    console.print(table)


def _render_sources(console: Console, data) -> None:
    table = Table(title=f"Sources ({len(data.page_metadata)})", title_style="bold", header_style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Title", overflow="fold")
    table.add_column("URL", overflow="fold")
    for s in data.page_metadata:
        table.add_row(_or_dash(s.status_code), _or_dash(s.page_title), _or_dash(s.url))
    console.print(table)
