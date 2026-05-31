"""Render a UniversityData result into a shareable, self-contained report.

`to_html` returns a single HTML document (inline CSS, no external assets) suitable
for emailing, printing to PDF, or opening straight from disk. `to_markdown` gives a
plaintext-friendly version for READMEs or PRs. Both read only the validated schema.
"""

from __future__ import annotations

from html import escape

from .present import format_cost, group_by_category, tuition_summary
from .schema import UniversityData


def _place(data: UniversityData) -> str | None:
    ov = data.overview
    if not ov or not ov.location:
        return None
    loc = ov.location
    parts = [loc.city, loc.state, loc.postal_code, loc.country]
    return ", ".join(p for p in parts if p) or None


def to_html(data: UniversityData, domain: str, quality=None) -> str:
    ov = data.overview
    name = (ov.university_name if ov else None) or domain
    contact = ov.contact if ov else None
    place = _place(data)
    summary = tuition_summary(data.tuition_breakdown)

    rng = "—"
    if summary["lowest"] is not None:
        rng = f"${summary['lowest']:,} – ${summary['highest']:,}"

    tuition_rows = ""
    for category, items in group_by_category(data.tuition_breakdown):
        tuition_rows += f'<tr class="grp"><td colspan="2">{escape(category)}</td></tr>'
        for it in items:
            tuition_rows += (
                f"<tr><td>{escape(it.fee_type or '—')}</td>"
                f'<td class="num">{escape(format_cost(it))}</td></tr>'
            )
    if not tuition_rows:
        tuition_rows = '<tr><td colspan="2" class="muted">No tuition figures extracted.</td></tr>'

    deadline_rows = "".join(
        f"<tr><td>{escape(d.deadline_type.value if d.deadline_type else '—')}</td>"
        f"<td>{escape(d.deadline_date or '—')}</td>"
        f"<td>{escape(d.notes or '—')}</td></tr>"
        for d in data.admission_deadlines
    ) or '<tr><td colspan="3" class="muted">No deadlines extracted.</td></tr>'

    source_rows = "".join(
        f"<tr><td>{escape(s.status_code or '—')}</td>"
        f"<td>{escape(s.page_title or '—')}</td>"
        f'<td><a href="{escape(s.url or "")}">{escape(s.url or "—")}</a></td></tr>'
        for s in data.page_metadata
    )

    quality_html = ""
    if quality is not None:
        bits = [
            f'<div class="kv"><span>Confidence</span><span>{escape(quality.confidence.get("overall", "—"))}</span></div>',
            f'<div class="kv"><span>Tuition grounded</span><span>{escape(quality.confidence.get("tuition_grounded", "—"))}</span></div>',
            f'<div class="kv"><span>Quality issues</span><span>{quality.issue_count}</span></div>',
        ]
        if quality.missing_fields:
            bits.append(f'<div class="kv"><span>Missing</span><span>{escape(", ".join(quality.missing_fields))}</span></div>')
        for fieldname, urls in quality.field_sources.items():
            bits.append(f'<div class="kv"><span>{escape(fieldname)}</span><span>{len(urls)} source(s)</span></div>')
        quality_html = f'<div class="card"><h2>Data quality &amp; confidence</h2>{"".join(bits)}</div>'

    contact_html = ""
    if contact or place:
        contact_html = f"""
        <div class="card">
          <h2>Overview</h2>
          <div class="kv"><span>Location</span><span>{escape(place or '—')}</span></div>
          <div class="kv"><span>Phone</span><span>{escape((contact.phone if contact else None) or '—')}</span></div>
          <div class="kv"><span>Email</span><span>{escape((contact.email if contact else None) or '—')}</span></div>
        </div>"""

    return _TEMPLATE.format(
        name=escape(name),
        domain=escape(domain),
        contact=contact_html,
        fee_count=summary["count"],
        categories=summary["categories"],
        cost_range=escape(rng),
        deadline_count=len(data.admission_deadlines),
        tuition_rows=tuition_rows,
        deadline_rows=deadline_rows,
        source_rows=source_rows,
        quality_section=quality_html,
    )


def to_markdown(data: UniversityData, domain: str) -> str:
    ov = data.overview
    name = (ov.university_name if ov else None) or domain
    contact = ov.contact if ov else None
    lines = [f"# {name}", "", f"`{domain}`", ""]

    place = _place(data)
    lines += ["## Overview", "", f"- **Location:** {place or '—'}"]
    lines += [f"- **Phone:** {(contact.phone if contact else None) or '—'}"]
    lines += [f"- **Email:** {(contact.email if contact else None) or '—'}", ""]

    lines += ["## Tuition / Cost", "", "| Category | Fee type | Cost |", "|---|---|---|"]
    for category, items in group_by_category(data.tuition_breakdown):
        for it in items:
            lines.append(f"| {category} | {it.fee_type or '—'} | {format_cost(it)} |")
    if not data.tuition_breakdown:
        lines.append("| — | No tuition figures extracted | — |")
    lines.append("")

    lines += ["## Admission deadlines", "", "| Type | Date | Notes |", "|---|---|---|"]
    for d in data.admission_deadlines:
        dtype = d.deadline_type.value if d.deadline_type else "—"
        lines.append(f"| {dtype} | {d.deadline_date or '—'} | {d.notes or '—'} |")
    if not data.admission_deadlines:
        lines.append("| — | — | No deadlines extracted |")
    lines += ["", "## Sources", ""]
    lines += [f"- [{s.status_code}] {s.url}" for s in data.page_metadata]
    return "\n".join(lines) + "\n"


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — UniCompanion report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Inter, sans-serif; color:#0F172A;
         background:#F1F5F9; margin:0; padding:2rem; }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  .hero {{ background:linear-gradient(135deg,#0EA5E9,#0369A1); color:#fff; border-radius:16px;
          padding:1.6rem 1.8rem; box-shadow:0 10px 26px rgba(2,132,199,.28); }}
  .hero h1 {{ margin:0; font-size:1.7rem; }}
  .hero .domain {{ opacity:.9; margin-top:.2rem; }}
  .stats {{ display:flex; gap:1rem; margin:1.2rem 0; flex-wrap:wrap; }}
  .stat {{ flex:1; min-width:150px; background:#fff; border:1px solid #E2E8F0; border-radius:12px;
          padding:.9rem 1rem; box-shadow:0 1px 3px rgba(15,23,42,.05); }}
  .stat .l {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:#64748B; font-weight:700; }}
  .stat .v {{ font-size:1.4rem; font-weight:800; color:#0284C7; margin-top:.2rem; }}
  .card {{ background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:1.1rem 1.3rem;
          margin-bottom:1.2rem; box-shadow:0 1px 3px rgba(15,23,42,.05); }}
  h2 {{ font-size:1rem; text-transform:uppercase; letter-spacing:.05em; color:#0F172A; margin:0 0 .8rem; }}
  .kv {{ display:flex; justify-content:space-between; padding:.4rem 0; border-bottom:1px solid #F1F5F9; }}
  .kv:last-child {{ border:none; }} .kv span:first-child {{ color:#64748B; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:.5rem .6rem; border-bottom:1px solid #F1F5F9; font-size:.92rem; }}
  th {{ color:#64748B; text-transform:uppercase; font-size:.7rem; letter-spacing:.05em; }}
  td.num {{ text-align:right; font-variant-numeric: tabular-nums; font-weight:600; }}
  tr.grp td {{ background:#F8FAFC; font-weight:700; color:#0369A1; }}
  .muted {{ color:#94A3B8; }}
  a {{ color:#0284C7; text-decoration:none; word-break:break-all; }}
  footer {{ color:#94A3B8; font-size:.8rem; text-align:center; margin-top:1.5rem; }}
</style></head>
<body><div class="wrap">
  <div class="hero"><h1>{name}</h1><div class="domain">{domain}</div></div>
  <div class="stats">
    <div class="stat"><div class="l">Fee items</div><div class="v">{fee_count}</div></div>
    <div class="stat"><div class="l">Categories</div><div class="v">{categories}</div></div>
    <div class="stat"><div class="l">Cost range</div><div class="v">{cost_range}</div></div>
    <div class="stat"><div class="l">Deadlines</div><div class="v">{deadline_count}</div></div>
  </div>
  {contact}
  <div class="card"><h2>Tuition / Cost breakdown</h2>
    <table><thead><tr><th>Fee</th><th class="num">Cost</th></tr></thead>
    <tbody>{tuition_rows}</tbody></table>
  </div>
  <div class="card"><h2>Admission deadlines</h2>
    <table><thead><tr><th>Type</th><th>Date</th><th>Notes</th></tr></thead>
    <tbody>{deadline_rows}</tbody></table>
  </div>
  <div class="card"><h2>Sources</h2>
    <table><thead><tr><th>Status</th><th>Title</th><th>URL</th></tr></thead>
    <tbody>{source_rows}</tbody></table>
  </div>
  {quality_section}
  <footer>Generated by UniCompanion · admissions &amp; tuition ETL</footer>
</div></body></html>
"""
