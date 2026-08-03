"""Format check results for the terminal (rich) or for machines (JSON)."""

import json as _json
import sys

from rich.console import Console
from rich.text import Text

from ghostcall.checker import DYNAMIC, HALLUCINATED, MODULE_MISSING, OK, CheckResult


def render_terminal(source_name: str, results: list[CheckResult]) -> None:
    """Pretty-print results to the current sys.stdout using rich."""
    console = Console(file=sys.stdout)
    findings = [r for r in results if r.status == HALLUCINATED]

    if not findings:
        console.print(f"[green]\u2713[/green] No hallucinations found in [bold]{source_name}[/bold]")
        return

    console.print(f"[bold]{source_name}[/bold]")
    console.print()

    for r in findings:
        line = Text()
        line.append("  \u26a0 ", style="bold yellow")
        line.append(f"{r.call.display}()", style="bold red")
        line.append(" does not exist", style="dim")
        console.print(line)

        loc = Text()
        loc.append(f"    line {r.call.lineno}", style="dim cyan")
        if r.suggestions:
            loc.append("  \u2192  Did you mean ", style="dim")
            loc.append(", ".join(r.suggestions), style="green")
            loc.append("?", style="dim")
        console.print(loc)
        console.print()

    plural = "s" if len(findings) != 1 else ""
    console.print(
        f"[bold red]\u2717[/bold red] Found [bold]{len(findings)}[/bold] hallucinated call{plural}"
    )


def render_json(source_name: str, results: list[CheckResult]) -> None:
    """Print results as JSON to the current sys.stdout."""
    findings = []
    counts = {HALLUCINATED: 0, MODULE_MISSING: 0, DYNAMIC: 0, OK: 0}

    for r in results:
        counts[r.status] += 1
        if r.status == HALLUCINATED:
            findings.append({
                "type": HALLUCINATED,
                "line": r.call.lineno,
                "col": r.call.col_offset,
                "call": r.call.display,
                "resolved": r.call.resolved_display,
                "missing_attr": r.missing_attr,
                "parent": r.parent_display,
                "suggestions": r.suggestions,
            })

    payload = {
        "source": source_name,
        "summary": {
            "total_calls_checked": len(results),
            "hallucinations_found": counts[HALLUCINATED],
            "module_missing": counts[MODULE_MISSING],
            "dynamic_skipped": counts[DYNAMIC],
            "ok": counts[OK],
        },
        "findings": findings,
    }
    _json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
