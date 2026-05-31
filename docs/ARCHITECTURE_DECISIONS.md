# Architecture Decision Records

Short records of the significant design decisions for this project — the context, the
choice, the alternatives considered, and the consequences. The goal is to make the
*reasoning* reviewable, not just the code.

---

## ADR-001 — Deterministic discovery over an agentic crawler

**Context.** We must find Admissions/Tuition pages from only a domain. One option is an
LLM "agent" that reads pages and decides which links to follow (ReAct-style).

**Decision.** Use deterministic link scoring + a priority breadth-first crawl (depth ≤ 2).

**Alternatives considered.**
- *Agentic crawler* — flexible, but non-deterministic, slower, more expensive (an LLM call
  per navigation step), and hard to unit-test or reproduce.
- *Plain BFS/DFS* — simple, but wastes a fixed page budget on irrelevant pages.

**Consequences.** Discovery is fast, free, reproducible, and unit-testable. The cost is a
hand-tuned keyword vocabulary (`config.py`), which is a fair trade for reliability. If a
site truly needed adaptive navigation, the LLM could be added as a *ranking* signal without
giving it control of the crawl.

---

## ADR-002 — LLM extraction with a deterministic fallback (not LLM-only, not rules-only)

**Context.** Extraction must be high quality but also robust when the API key/quota is
unavailable, and must never block the pipeline.

**Decision.** Gemini is the primary extractor; a regex/heuristic extractor is the fallback.
Both emit the same intermediate shape via one normalizer.

**Alternatives considered.**
- *LLM-only* — best quality, but a hard dependency on an external service and quota.
- *Rules-only* — free and deterministic, but brittle on messy real-world layouts.

**Consequences.** The pipeline always produces valid output. The `method` field records
which path ran. A single `assemble_core()` keeps normalization (and the "never guess" rule)
in one place regardless of source.

---

## ADR-003 — Grounding pass for anti-hallucination

**Context.** LLMs can produce plausible but fabricated numbers. The brief explicitly forbids
fabrication and prefers `null`.

**Decision.** After extraction, drop any cost/phone/email/postal that does not appear
verbatim on a fetched page (checking comma and plain number forms).

**Alternatives considered.**
- *Trust the prompt* — "don't guess" instructions help but don't guarantee.
- *Confidence threshold from the model* — model self-confidence is poorly calibrated.

**Consequences.** Fabrication is structurally prevented, not merely discouraged (measured 0%
on the gold set). The trade-off is precision over recall: a real figure formatted oddly can be
dropped. Fuzzy numeric matching would raise recall without reintroducing hallucination.

---

## ADR-004 — Strict schema output; run metadata kept out of the JSON

**Context.** The output must match the provided Pydantic schema exactly, yet we also compute
useful signals (extractor used, confidence, scores, timing, citations).

**Decision.** The JSON document contains only the provided schema. All extra signals live on
a `PipelineResult` wrapper and in side `*.quality.json` files.

**Alternatives considered.**
- *Extend the schema* — richer output, but no longer matches the grader's contract.

**Consequences.** The deliverable is byte-for-byte the provided schema (re-validated in tests),
while operators still get confidence, attribution, and citations alongside it.

---

## ADR-005 — `requests` by default, Playwright optional (not Scrapy)

**Context.** Most `.edu` admissions/tuition pages are server-rendered; some are JS-heavy.

**Decision.** Default to a `requests` transport; offer a Playwright (headless Chromium)
backend behind `--render`. The fetch transport is pluggable; all policy is shared.

**Alternatives considered.**
- *Scrapy* — powerful, but heavy framework overhead for a depth-2, few-pages-per-site crawl.
- *Playwright-always* — handles JS, but ~10× slower and a 150 MB browser dependency by default.

**Consequences.** The common case is fast and light; JS rendering is one flag away. No
framework lock-in.

---

## ADR-006 — Prompt-guided JSON + local validation (with native-schema as a future option)

**Context.** We need structured JSON from the LLM that conforms to the schema.

**Decision.** Send an explicit JSON shape with hard rules at temperature 0, then parse and
re-validate locally with Pydantic.

**Alternatives considered.**
- *Native `response_schema` / controlled generation* — forces valid JSON at the API layer.
  A strong upgrade; deferred because local validation already guarantees correctness and gives
  finer control over the "null, don't guess" behavior and normalization.

**Consequences.** The model never has the final say on types; malformed output is caught and
falls back. Moving to native structured decoding is a drop-in future improvement.

---

## ADR-007 — No vector database, no fine-tuning

**Context.** RAG/embeddings and fine-tuning are common reflexes for "LLM + documents".

**Decision.** Use neither.

**Alternatives considered.**
- *Vector DB / RAG* — useful for retrieval over large corpora; here each site is tiny and we
  already select the few relevant pages deterministically, so retrieval adds latency and
  infrastructure for no gain.
- *Fine-tuning* — needs labeled data and a training/serving pipeline; zero-shot extraction with
  grounding already meets the bar.

**Consequences.** Simpler system, no extra infrastructure, easier to reason about and deploy.
