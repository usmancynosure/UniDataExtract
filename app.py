"""Streamlit web interface for UniDataExtract.

    streamlit run app.py

A thin presentation layer over `unidata.pipeline.run` — enter a domain, watch the
crawl discover pages live, and browse the structured result. All the logic lives in
the package; this file only renders.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from unidata.config import CrawlSettings
from unidata.pipeline import run
from unidata.present import fee_category, format_cost, tuition_summary

load_dotenv()

st.set_page_config(page_title="UniCompanion", page_icon="🎓", layout="wide")

# --------------------------------------------------------------------------
# Styling — a light, sky-blue, product-grade look
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

      html, body, [class*="css"], .stMarkdown, .stMetric { font-family: 'Inter', sans-serif; }
      .stApp { background: #F1F5F9; }
      .block-container { padding-top: 1.5rem; max-width: 1180px; }

      /* Hero */
      .hero {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 55%, #0369A1 100%);
        border-radius: 18px; padding: 2rem 2.2rem; color: #fff;
        box-shadow: 0 12px 30px rgba(2,132,199,0.28); margin-bottom: 1.4rem;
      }
      .hero h1 { font-size: 2rem; font-weight: 800; margin: 0; letter-spacing:-.5px; }
      .hero p  { margin: .35rem 0 0; opacity: .92; font-size: 1.02rem; }
      .hero .pills { margin-top: .9rem; }
      .pill {
        display:inline-block; background: rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
        color:#fff; padding:.18rem .7rem; border-radius:999px; font-size:.74rem; font-weight:600;
        margin-right:.4rem; backdrop-filter: blur(4px);
      }

      /* Cards */
      .card {
        background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:1.1rem 1.25rem;
        box-shadow:0 1px 3px rgba(15,23,42,.05); height:100%;
      }
      .card h3 {
        font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:#64748B;
        font-weight:700; margin:0 0 .7rem;
      }
      .metric { background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:1rem 1.1rem;
                box-shadow:0 1px 3px rgba(15,23,42,.05); }
      .metric .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:#64748B; font-weight:700; }
      .metric .value { font-size:1.7rem; font-weight:800; color:#0F172A; line-height:1.1; margin-top:.25rem; }
      .metric .value.accent { color:#0284C7; }

      .kv { display:flex; justify-content:space-between; gap:1rem; padding:.42rem 0; border-bottom:1px solid #F1F5F9; }
      .kv:last-child { border-bottom:none; }
      .kv .k { color:#64748B; font-weight:600; font-size:.86rem; }
      .kv .v { color:#0F172A; font-size:.9rem; text-align:right; word-break:break-word; }

      .sec-title { font-size:1.05rem; font-weight:700; color:#0F172A; margin:1.4rem 0 .6rem; }

      /* Buttons */
      .stButton button {
        background: linear-gradient(135deg,#0EA5E9,#0284C7); color:#fff; border:none;
        border-radius:10px; font-weight:700; padding:.55rem 1rem; box-shadow:0 4px 12px rgba(2,132,199,.3);
      }
      .stButton button:hover { filter:brightness(1.05); color:#fff; }

      /* Tables */
      [data-testid="stDataFrame"] { border:1px solid #E2E8F0; border-radius:12px; overflow:hidden; }

      [data-testid="stSidebar"] { background:#fff; border-right:1px solid #E2E8F0; }
      [data-testid="stSidebar"] h2 { color:#0F172A; }
      footer, #MainMenu { visibility:hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>🎓 UniCompanion</h1>
      <p>Your companion for university admissions &amp; tuition — one domain in, structured data out.</p>
      <div class="pills">
        <span class="pill">Auto page discovery</span>
        <span class="pill">Crawl depth ≤ 2</span>
        <span class="pill">Gemini + heuristic</span>
        <span class="pill">Pydantic-validated</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def _metric(label: str, value, accent: bool = False) -> str:
    cls = "value accent" if accent else "value"
    return f'<div class="metric"><div class="label">{label}</div><div class="{cls}">{value}</div></div>'


# --------------------------------------------------------------------------
# Sidebar controls
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Run extraction")
    domain = st.text_input("University domain", value="bucknell.edu", placeholder="e.g. salisbury.edu")
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    use_llm = st.toggle("Gemini extraction", value=has_key, help="Falls back to heuristics if off or no key")
    if use_llm and not has_key:
        st.warning("No GEMINI_API_KEY found — using the heuristic extractor.", icon="⚠️")
    render = st.toggle("JavaScript rendering (Playwright)", value=False)
    max_pages = st.slider("Max pages", 6, 40, 24)
    max_depth = st.slider("Max crawl depth", 1, 2, 2)
    go = st.button("Extract", type="primary", use_container_width=True)
    st.caption("Discovery is deterministic — the LLM only structures already-fetched text.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
if go and domain.strip():
    settings = CrawlSettings(max_pages=max_pages, max_depth=max_depth, render=render)

    with st.status(f"Discovering **{domain}** …", expanded=True) as status:
        log = st.empty()
        seen: list[str] = []

        def on_page(page) -> None:
            seen.append(f"`{page.category}` · d{page.depth} · {page.result.url}")
            log.markdown("  \n".join(seen[-12:]))

        try:
            result = run(domain.strip(), settings=settings, use_llm=use_llm, on_page=on_page)
            status.update(label=f"Done — {len(result.data.page_metadata)} pages used", state="complete")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            status.update(label="Failed", state="error")
            st.error(str(exc))
            st.stop()

    data = result.data
    ov = data.overview
    st.markdown(f"## {(ov.university_name if ov else None) or result.domain}")

    summary = tuition_summary(data.tuition_breakdown)
    lowest = f"${summary['lowest']:,}" if summary["lowest"] is not None else "—"
    highest = f"${summary['highest']:,}" if summary["highest"] is not None else "—"
    cols = st.columns(4)
    cards = [
        _metric("Extractor", result.method.capitalize(), accent=result.method == "gemini"),
        _metric("Fee items", summary["count"], accent=True),
        _metric("Lowest fee", lowest, accent=True),
        _metric("Highest fee", highest, accent=True),
    ]
    for col, html in zip(cols, cards, strict=False):
        col.markdown(html, unsafe_allow_html=True)

    q = result.quality
    st.caption(
        f"Confidence: **{q.confidence.get('overall', 'n/a')}** · "
        f"tuition grounded {q.confidence.get('tuition_grounded', '—')} · "
        f"{q.issue_count} quality issue(s) · {result.elapsed_seconds:.1f}s"
    )
    if q.missing_fields:
        st.warning("Missing: " + ", ".join(q.missing_fields), icon="⚠️")

    left, right = st.columns([1, 1])
    with left:
        loc = ov.location if ov else None
        con = ov.contact if ov else None
        place = ", ".join(x for x in [
            getattr(loc, "city", None), getattr(loc, "state", None),
            getattr(loc, "postal_code", None), getattr(loc, "country", None),
        ] if x) if loc else None
        rows = "".join(
            f'<div class="kv"><span class="k">{k}</span><span class="v">{v or "—"}</span></div>'
            for k, v in [
                ("Location", place),
                ("Phone", getattr(con, "phone", None)),
                ("Email", getattr(con, "email", None)),
            ]
        )
        st.markdown(f'<div class="card"><h3>Overview</h3>{rows}</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="sec-title">Admission deadlines</div>', unsafe_allow_html=True)
        if data.admission_deadlines:
            st.dataframe(
                [
                    {
                        "Type": d.deadline_type.value if d.deadline_type else "—",
                        "Date": d.deadline_date or "—",
                        "Notes": d.notes or "—",
                    }
                    for d in data.admission_deadlines
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No deadlines extracted.")

    st.markdown('<div class="sec-title">Tuition / Cost breakdown</div>', unsafe_allow_html=True)
    if data.tuition_breakdown:
        rows = sorted(
            (
                {"Category": fee_category(t.fee_type), "Fee type": t.fee_type or "—", "Cost": format_cost(t)}
                for t in data.tuition_breakdown
            ),
            key=lambda r: r["Category"],
        )
        cats = sorted({r["Category"] for r in rows})
        chosen = st.multiselect("Filter by category", cats, default=cats)
        st.dataframe(
            [r for r in rows if r["Category"] in chosen],
            hide_index=True,
            use_container_width=True,
            column_config={"Cost": st.column_config.TextColumn(width="small")},
        )
    else:
        st.info("No tuition figures extracted.")

    st.markdown('<div class="sec-title">Sources (page metadata)</div>', unsafe_allow_html=True)
    st.dataframe(
        [
            {"Status": s.status_code, "Page title": s.page_title, "URL": s.url}
            for s in data.page_metadata
        ],
        hide_index=True,
        use_container_width=True,
    )

    from unidata.report import to_html

    payload = data.model_dump_json(indent=2)
    slug = domain.replace(".", "_")
    dl1, dl2 = st.columns(2)
    dl1.download_button("⬇ Download JSON", payload, file_name=f"{slug}.json", use_container_width=True)
    dl2.download_button(
        "⬇ Download HTML report",
        to_html(data, domain, quality=result.quality),
        file_name=f"{slug}.html",
        mime="text/html",
        use_container_width=True,
    )
    with st.expander("Raw JSON"):
        st.code(payload, language="json")
else:
    st.markdown(
        '<div class="card"><h3>Get started</h3>'
        '<p style="color:#475569;margin:.2rem 0 0">Enter a university domain in the sidebar '
        'and click <b>Extract</b>. The pipeline discovers the Admissions and Tuition pages on '
        'its own, then returns clean, validated data.</p></div>',
        unsafe_allow_html=True,
    )
