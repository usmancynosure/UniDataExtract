"""Field-level evaluation harness for the extraction pipeline.

Compares pipeline output against a small hand-verified gold set and reports
coverage, precision, recall, and fabrication rate per field — so the extractor's
accuracy is a measured number, not a vibe.

    python evals/run_eval.py            # offline: score the committed samples/
    python evals/run_eval.py --live     # re-run the pipeline against live sites

Definitions (per gold item):
  produced   = the pipeline asserted a value for this field
  correct    = that value matches the gold truth
  coverage   = produced / total            (did we attempt it)
  precision  = correct  / produced         (of what we asserted, how much was right)
  recall     = correct  / total            (of the truth, how much we recovered)
  fabrication= (produced & wrong) / produced   (asserted-but-wrong rate; grounding aims for ~0)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from unidata.schema import UniversityData  # noqa: E402

# Accept either an abbreviation or the full state name on both sides.
_STATE_ALIASES = {
    "pa": {"pa", "pennsylvania"},
    "md": {"md", "maryland"},
    "dc": {"dc", "district of columbia", "washington", "washington dc"},
}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _state_match(got: str | None, expected: str) -> bool:
    g, e = _norm(got), _norm(expected)
    if g == e:
        return True
    for variants in _STATE_ALIASES.values():
        if g in variants and e in variants:
            return True
    return False


def _checks(data: UniversityData, gold: dict) -> list[tuple[str, str, bool, bool]]:
    """Return (field, kind, produced, correct) for every gold item.

    kind="value"  → a single asserted value (drives precision / fabrication)
    kind="recall" → a known item that should appear (drives recall)
    """
    ov = data.overview
    name = ov.university_name if ov else None
    loc = ov.location if ov else None
    con = ov.contact if ov else None
    costs = {t.cost for t in data.tuition_breakdown}
    types = {d.deadline_type.value for d in data.admission_deadlines if d.deadline_type}

    out: list[tuple[str, str, bool, bool]] = []
    out.append(("university_name", "value", name is not None, _norm(name) == _norm(gold["university_name"])))
    out.append(("state", "value", (loc and loc.state) is not None, _state_match(loc.state if loc else None, gold["state"])))
    out.append(("phone", "value", (con and con.phone) is not None, _digits(con.phone if con else None) == _digits(gold["phone"])))
    out.append(("has_tuition", "value", True, bool(data.tuition_breakdown) == gold["has_tuition"]))
    for c in gold.get("expected_costs", []):
        out.append((f"cost:{c}", "recall", bool(data.tuition_breakdown), c in costs))
    for t in gold.get("deadline_types", []):
        out.append((f"deadline:{t}", "recall", bool(data.admission_deadlines), t in types))
    return out


def _load(domain_slug: str, samples_dir: Path, live: bool, gold: dict) -> UniversityData:
    if live:
        from unidata.pipeline import run

        return run(gold["domain"]).data
    return UniversityData.model_validate(json.loads((samples_dir / f"{domain_slug}.json").read_text()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Field-level extraction eval against a gold set.")
    ap.add_argument("--live", action="store_true", help="Re-run the pipeline instead of scoring samples/")
    ap.add_argument("--samples-dir", default="samples", help="Where to read <slug>.json from (offline mode)")
    ap.add_argument("--gold-dir", default="evals/gold", help="Gold-label directory")
    args = ap.parse_args(argv)

    samples_dir = ROOT / args.samples_dir
    gold_files = sorted(glob.glob(str(ROOT / args.gold_dir / "*.json")))
    if not gold_files:
        print("No gold files found.", file=sys.stderr)
        return 1

    # value-field tallies drive precision/fabrication; recall targets drive recall
    v_total = v_prod = v_corr = 0
    r_total = r_corr = 0
    print(f"\nEvaluation ({'live' if args.live else 'offline: ' + args.samples_dir})\n" + "=" * 60)
    for gf in gold_files:
        gold = json.loads(Path(gf).read_text())
        slug = Path(gf).stem
        data = _load(slug, samples_dir, args.live, gold)
        checks = _checks(data, gold)
        c_corr = sum(ok for *_, ok in checks)
        print(f"\n{gold['domain']}  ({c_corr}/{len(checks)} correct)")
        for fieldname, kind, p, ok in checks:
            mark = "PASS" if ok else ("MISS" if not p else "WRONG")
            print(f"  [{mark:5}] {fieldname}")
            if kind == "value":
                v_total += 1
                v_prod += p
                v_corr += ok
            else:
                r_total += 1
                r_corr += ok

    total = v_total + r_total
    correct = v_corr + r_corr
    accuracy = correct / total if total else 0
    coverage = v_prod / v_total if v_total else 0
    precision = v_corr / v_prod if v_prod else 0
    fabrication = (v_prod - v_corr) / v_prod if v_prod else 0
    recall = r_corr / r_total if r_total else 0
    print("\n" + "=" * 60)
    print("AGGREGATE")
    print(f"  gold items     : {total}  ({correct} correct → {accuracy:.1%} accuracy)")
    print(f"  coverage       : {coverage:5.1%}   (value fields with a non-null answer)")
    print(f"  precision      : {precision:5.1%}   (asserted values that are correct)")
    print(f"  fabrication    : {fabrication:5.1%}   (asserted-but-wrong — grounding aims for 0%)")
    print(f"  recall@targets : {recall:5.1%}   (known costs/deadline-types recovered)")
    print()

    # Non-zero exit if overall accuracy regresses below a floor, so CI can gate.
    floor = float(os.environ.get("EVAL_MIN_ACCURACY", "0.8"))
    return 0 if accuracy >= floor else 2


if __name__ == "__main__":
    raise SystemExit(main())
