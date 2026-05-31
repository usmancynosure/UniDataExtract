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

load_dotenv()

st.set_page_config(page_title="UniDataExtract", page_icon="🎓", layout="wide")

st.markdown(
    """
    <div style="padding:1.2rem 0 0.4rem">
      <span style="font-size:2.1rem;font-weight:800;
            background:linear-gradient(90deg,#7c3aed,#db2777);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        🎓 UniDataExtract
      </span>
      <div style="color:#6b7280;margin-top:-2px">
        Admissions &amp; Tuition ETL — a university domain in, structured data out.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Run")
    domain = st.text_input("University domain", value="bucknell.edu", placeholder="e.g. salisbury.edu")
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    use_llm = st.toggle("Gemini extraction", value=has_key, help="Falls back to heuristics if off or no key")
    if use_llm and not has_key:
        st.warning("No GEMINI_API_KEY found — will use the heuristic extractor.", icon="⚠️")
    render = st.toggle("JavaScript rendering (Playwright)", value=False)
    max_pages = st.slider("Max pages", 6, 40, 24)
    max_depth = st.slider("Max crawl depth", 1, 2, 2)
    go = st.button("Extract", type="primary", use_container_width=True)


def _money(v):
    return f"${v:,.0f}" if v is not None else "—"


if go and domain.strip():
    settings = CrawlSettings(max_pages=max_pages, max_depth=max_depth, render=render)

    with st.status(f"Discovering **{domain}** …", expanded=True) as status:
        log = st.empty()
        seen: list[str] = []

        def on_page(page) -> None:
            seen.append(f"`{page.category}` · d{page.depth} · {page.result.url}")
            log.markdown("  \n".join(seen[-12:]))

        try:
            data = run(domain.strip(), settings=settings, use_llm=use_llm, on_page=on_page)
            status.update(label=f"Done — {len(data.sources)} pages used", state="complete")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            status.update(label="Failed", state="error")
            st.error(str(exc))
            st.stop()

    # -- headline metrics ------------------------------------------------
    st.subheader(data.name or data.domain)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Method", data.extraction_method)
    c2.metric("Tuition rows", len(data.tuition))
    c3.metric("Deadlines", len(data.admission_deadlines))
    c4.metric("Sources", len(data.sources))

    if data.overview:
        st.caption(data.overview)

    left, right = st.columns(2)
    with left:
        st.markdown("**Contact**")
        st.table({k: [v or "—"] for k, v in data.contact.model_dump().items()})
    with right:
        st.markdown("**Admission deadlines**")
        if data.admission_deadlines:
            st.dataframe(
                [
                    {
                        "Name": d.name,
                        "Applicant": d.applicant_type or "—",
                        "Date": d.deadline.isoformat() if d.deadline else (d.deadline_text or "—"),
                    }
                    for d in data.admission_deadlines
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No deadlines extracted.")

    st.markdown("**Tuition / Cost**")
    if data.tuition:
        st.dataframe(
            [
                {
                    "Student": t.student_type or "—",
                    "Residency": t.residency or "—",
                    "Year": t.academic_year or "—",
                    "Tuition": _money(t.tuition),
                    "Fees": _money(t.fees),
                    "Room & Board": _money(t.room_and_board),
                    "Total": _money(t.total_cost_of_attendance),
                }
                for t in data.tuition
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No tuition figures extracted.")

    st.markdown("**Sources**")
    st.dataframe(
        [
            {
                "Type": s.page_type,
                "Depth": s.depth,
                "Score": s.relevance_score,
                "Status": s.http_status,
                "URL": s.url,
            }
            for s in data.sources
        ],
        hide_index=True,
        use_container_width=True,
    )

    payload = data.model_dump_json(indent=2)
    st.download_button("⬇ Download JSON", payload, file_name=f"{domain.replace('.', '_')}.json")
    with st.expander("Raw JSON"):
        st.code(payload, language="json")
else:
    st.info("Enter a university domain in the sidebar and click **Extract**.")
