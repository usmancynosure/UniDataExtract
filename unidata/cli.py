"""Rich command-line interface for the ETL pipeline.

    unidata bucknell.edu
    unidata bucknell.edu salisbury.edu udc.edu --out-dir samples
    unidata bucknell.edu --no-llm --render -v
    unidata bucknell.edu --json > out.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .config import CrawlSettings
from .console import banner, render_result
from .pipeline import PipelineResult, run


class _JsonLogFormatter(logging.Formatter):
    """Minimal structured (JSON-per-line) log formatter for --log-json."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )

# Accent colors for the live crawl ticker, keyed by discovered page category.
CATEGORY_STYLE = {"homepage": "white", "admissions": "cyan", "tuition": "green", "other": "dim"}


def _slug(domain: str) -> str:
    return domain.replace("https://", "").replace("http://", "").strip("/").replace(".", "_")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="unidata",
        description="Discover and extract Admissions/Tuition data from a university domain.",
    )
    p.add_argument("domains", nargs="+", help="University domain(s), e.g. bucknell.edu")
    p.add_argument("--out-dir", default=None, help="Write <domain>.json files to this directory")
    p.add_argument("--json", action="store_true", help="Print raw JSON only (machine-readable)")
    p.add_argument("--no-llm", action="store_true", help="Force the deterministic extractor")
    p.add_argument("--render", action="store_true", help="Fetch via headless Chromium (Playwright)")
    p.add_argument("--report", choices=("html", "md"), help="Also write a shareable report file")
    p.add_argument("--max-depth", type=int, default=2, help="Max crawl depth (default 2)")
    p.add_argument("--max-pages", type=int, default=30, help="Max pages fetched per site")
    p.add_argument("--log-json", action="store_true", help="Emit logs as structured JSON lines")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose crawl logging")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)

    # In JSON mode we keep stdout clean; the pretty UI goes to stderr.
    console = Console(stderr=args.json)
    level = logging.INFO if (args.verbose or args.log_json) else logging.WARNING
    handler = logging.StreamHandler()
    if args.log_json:
        handler.setFormatter(_JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level, handlers=[handler])

    settings = CrawlSettings(
        max_depth=args.max_depth, max_pages=args.max_pages, render=args.render
    )
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    if not args.json:
        console.print(banner())

    exit_code = 0
    results: list[tuple[str, PipelineResult]] = []
    for domain in args.domains:
        try:
            result = _run_one(console, domain, settings, use_llm=not args.no_llm, quiet=args.json)
        except Exception as exc:  # keep going on the remaining domains
            console.print(f"[bold red]✗[/bold red] {domain}: {exc}")
            exit_code = 1
            continue
        results.append((domain, result))

        payload = result.data.model_dump_json(indent=2)  # exactly the provided schema
        if out_dir:
            path = out_dir / f"{_slug(domain)}.json"
            path.write_text(payload + "\n")
            # Side artifact: data-quality + attribution + confidence (not in the schema).
            (out_dir / f"{_slug(domain)}.quality.json").write_text(
                json.dumps(result.quality.as_dict(), indent=2) + "\n"
            )
            console.print(f"[green]✓[/green] {domain} → {path}  [dim]({result.method})[/dim]")
        elif args.json:
            print(payload)
        else:
            render_result(console, result)

        if args.report:
            _write_report(console, result, args.report, out_dir, domain)

    if len(results) > 1 and not args.json:
        _render_batch_summary(console, results)

    return exit_code


def _render_batch_summary(console: Console, results: list[tuple[str, PipelineResult]]) -> None:
    """Execution summary across all domains processed in this run."""
    table = Table(title="Run summary", title_style="bold", header_style="dim")
    for col in ("Domain", "Method", "Fees", "Deadlines", "Confidence", "Issues", "Time"):
        table.add_column(col, justify="right" if col in {"Fees", "Deadlines", "Issues", "Time"} else "left")
    for domain, r in results:
        issues = r.quality.issue_count
        table.add_row(
            domain,
            r.method,
            str(len(r.data.tuition_breakdown)),
            str(len(r.data.admission_deadlines)),
            r.quality.confidence.get("overall", "—"),
            f"[red]{issues}[/red]" if issues else "[green]0[/green]",
            f"{r.elapsed_seconds:.1f}s",
        )
    console.print(table)


def _write_report(console, result, fmt: str, out_dir, domain: str) -> None:
    from .report import to_html, to_markdown

    if fmt == "html":
        content = to_html(result.data, domain, quality=result.quality)
    else:
        content = to_markdown(result.data, domain)
    path = (out_dir or Path(".")) / f"{_slug(domain)}.{fmt}"
    path.write_text(content)
    console.print(f"[green]✓[/green] report → {path}")


def _run_one(console: Console, domain: str, settings: CrawlSettings, use_llm: bool, quiet: bool):
    """Run the pipeline for one domain, showing a live crawl ticker unless quiet."""
    if quiet:
        return run(domain, settings=settings, use_llm=use_llm)

    spinner = Spinner("dots", text=Text(f"Discovering {domain}…", style="dim"))
    state = {"count": 0}

    with Live(spinner, console=console, refresh_per_second=12, transient=True) as live:
        def on_page(page) -> None:
            state["count"] += 1
            style = CATEGORY_STYLE.get(page.category, "white")
            line = Text.assemble(
                (f"[{state['count']:>2}] ", "dim"),
                (f"{page.category:<10}", style),
                (f"d{page.depth} ", "dim"),
                (page.result.url, "white"),
            )
            spinner.update(text=line)
            live.refresh()

        result = run(domain, settings=settings, use_llm=use_llm, on_page=on_page)

    console.print(
        f"[dim]crawled[/dim] {state['count']} [dim]pages ·[/dim] "
        f"{len(result.data.page_metadata)} [dim]sources kept[/dim]"
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
