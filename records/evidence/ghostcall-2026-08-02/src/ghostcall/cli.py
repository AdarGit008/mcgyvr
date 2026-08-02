"""ghostcall CLI entry point."""

import sys
from pathlib import Path
from typing import Optional

import rich_click as click

from ghostcall import __version__
from ghostcall.checker import HALLUCINATED, check
from ghostcall.markdown import extract_python
from ghostcall.output import render_json, render_terminal
from ghostcall.parser import parse


@click.command()
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
)
@click.option(
    "--md",
    "is_markdown",
    is_flag=True,
    help="Treat input as markdown and check Python fenced code blocks.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output results as JSON for machine consumption.",
)
@click.version_option(__version__)
def main(file: Optional[Path], is_markdown: bool, as_json: bool) -> None:
    """Detect hallucinated API calls in LLM-generated Python code.

    Reads from FILE, or stdin if no file is given. Use --md to extract
    Python from markdown fenced code blocks (e.g., LLM chat exports).
    """
    if file is None:
        source = sys.stdin.read()
        source_name = "<stdin>"
    else:
        source = file.read_text()
        source_name = str(file)

    if is_markdown:
        source = extract_python(source)

    if not source.strip():
        if as_json:
            render_json(source_name, [])
        else:
            click.echo(f"\u2713 No Python code found in {source_name}")
        sys.exit(0)

    try:
        parsed = parse(source)
    except SyntaxError as e:
        click.echo(
            f"Syntax error in {source_name}: {e.msg} at line {e.lineno}",
            err=True,
        )
        sys.exit(2)

    results = [check(c) for c in parsed.calls]

    if as_json:
        render_json(source_name, results)
    else:
        render_terminal(source_name, results)

    has_hallucinations = any(r.status == HALLUCINATED for r in results)
    sys.exit(1 if has_hallucinations else 0)
