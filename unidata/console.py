"""Rich rendering for the CLI: a clean, scannable view of one extraction result.

Pure presentation — nothing here touches the network or the models' logic, so the
pipeline stays usable as a plain library and this can be swapped for any frontend.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .schema import UniversityData

# Per-category accent colors, reused across the progress view and result tables.
CATEGORY_STYLE = {
    "homepage": "white",
    "admissions": "cyan",
    "tuition": "green",
    "other": "dim",
}


def banner() -> Panel:
    title = Text("UniDataExtract", style="bold magenta")
    subtitle = Text("Admissions & Tuition ETL — domain in, structured data out", style="dim")
    return Panel(Text.assemble(title, "\n", subtitle), border_style="magenta", expand=False)


def _money(value: float | None) -> str:
    return f"${value:,.0f}" if value is not None else "[dim]—[/dim]"


def _or_dash(value) -> str:
    return str(value) if value not in (None, "") else "[dim]—[/dim]"


def render_result(console: Console, data: UniversityData) -> None:
    """Print a full, human-readable summary of one UniversityData object."""
    method_color = "green" if data.extraction_method == "gemini" else "yellow"
    header = Text.assemble(
        (data.name or data.domain, "bold"),
        ("   "),
        (f"{data.domain}", "dim"),
        ("   via "),
        (data.extraction_method, method_color),
    )
    console.print(Panel(header, border_style=method_color, expand=False))

    if data.overview:
        console.print(Panel(data.overview, title="Overview", border_style="dim", expand=False))

    _render_contact(console, data)
    _render_tuition(console, data)
    _render_deadlines(console, data)
    _render_sources(console, data)
    console.print()


def _render_contact(console: Console, data: UniversityData) -> None:
    c = data.contact
    if not any([c.phone, c.email, c.mailing_address, c.admissions_office_url]):
        return
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Phone", _or_dash(c.phone))
    t.add_row("Email", _or_dash(c.email))
    t.add_row("Address", _or_dash(c.mailing_address))
    t.add_row("Admissions", _or_dash(c.admissions_office_url))
    console.print(Panel(t, title="Contact", border_style="blue", expand=False))


def _render_tuition(console: Console, data: UniversityData) -> None:
    table = Table(title="Tuition / Cost", title_style="bold green", header_style="green")
    for col in ("Student", "Residency", "Year", "Tuition", "Fees", "Room & Board", "Total"):
        table.add_column(col, justify="right" if col in {"Tuition", "Fees", "Room & Board", "Total"} else "left")
    if not data.tuition:
        console.print(Panel("[dim]No tuition figures extracted[/dim]", border_style="green", expand=False))
        return
    for row in data.tuition:
        table.add_row(
            _or_dash(row.student_type),
            _or_dash(row.residency),
            _or_dash(row.academic_year),
            _money(row.tuition),
            _money(row.fees),
            _money(row.room_and_board),
            _money(row.total_cost_of_attendance),
        )
    console.print(table)


def _render_deadlines(console: Console, data: UniversityData) -> None:
    if not data.admission_deadlines:
        return
    table = Table(title="Admission Deadlines", title_style="bold cyan", header_style="cyan")
    table.add_column("Name")
    table.add_column("Applicant")
    table.add_column("Date")
    for d in data.admission_deadlines:
        when = d.deadline.isoformat() if d.deadline else (d.deadline_text or "—")
        table.add_row(d.name, _or_dash(d.applicant_type), when)
    console.print(table)


def _render_sources(console: Console, data: UniversityData) -> None:
    table = Table(title=f"Sources ({len(data.sources)})", title_style="bold", header_style="dim")
    table.add_column("Type")
    table.add_column("D", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("URL", overflow="fold")
    for s in data.sources:
        style = CATEGORY_STYLE.get(s.page_type, "white")
        score = f"{s.relevance_score:.1f}" if s.relevance_score is not None else "—"
        table.add_row(Text(s.page_type, style=style), str(s.depth), score, s.url)
    console.print(table)
