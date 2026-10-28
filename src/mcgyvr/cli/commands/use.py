"""`mcgyvr use NAME`: switch the use case a setup serves, and nothing else.

The setup is the one `--config` names, else the one a run would read
(`MCGYVR_CONFIG`, then the live fleet folder). In a setup folder the
`use_case:` line of `policy.yaml` is rewritten, or added at the end when the
policy names none; a setup written as one document has its own top-level line
rewritten. Every other byte of the file stays as it was. The command says the
use case before and after, the file it wrote, and what that turns on or off:
the stages `mcgyvr-code` runs, or that a raw use case runs none and the contract
verbs refuse. `coding` and any other name that is not a use case are refused
with nothing written.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.cli.common import add_config
from mcgyvr.config import (
    FLEET_FILENAME,
    MCGYVR_CODE,
    POLICY_FILENAME,
    RELIEF_FILENAME,
    RETIRED_USE_CASES,
    USE_CASES,
    Config,
    ConfigError,
    config_path,
    parse,
    stages,
)
from mcgyvr.exits import Exit

#: The top-level `use_case:` line: its key (after a byte-order mark on the first
#: line), its value (bare, quoted or empty) and whatever follows the value on the
#: line, a comment and a CR included.
_LINE = re.compile(
    r"^(?P<key>\ufeff?use_case:[ \t]*)"
    r"(?P<value>\"[^\"\n]*\"|'[^'\n]*'|[^\s#]*)"
    r"(?P<rest>[^\n]*)$",
    re.MULTILINE,
)


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    """Register `use NAME [--config PATH]`; its `func` is `_use`."""
    use = sub.add_parser(
        "use",
        help="switch the use case a setup serves: " + ", ".join(USE_CASES),
        description=(
            "Rewrite the use_case line of the setup's policy and say what it "
            "turns on or off. mcgyvr-code opts in to every stage between the "
            "model and you, each under its own switch; code, chat and agent "
            "serve the model raw, and PROMPT and direct refuse under them."
        ),
    )
    use.add_argument("name", metavar="NAME", help=" | ".join(USE_CASES))
    add_config(use, what="setup whose use case to switch")
    use.set_defaults(func=_use)
    return use


def _use(args: argparse.Namespace) -> int:
    name = str(args.name)
    refused = _refusal(name)
    if refused is not None:
        print(f"error: {refused}", file=sys.stderr)
        return Exit.USAGE
    named = getattr(args, "config", None)
    try:
        setup = Path(named) if named is not None else config_path()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if not setup.is_file() and not (setup / FLEET_FILENAME).is_file():
        print(
            f"error: no setup at {setup}: it holds no {FLEET_FILENAME}", file=sys.stderr
        )
        return Exit.ERROR
    target = setup if setup.is_file() else setup / POLICY_FILENAME
    try:
        # Bytes, not text: the line endings come back exactly as they were.
        text = target.read_bytes().decode("utf-8") if target.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {target}: {exc}", file=sys.stderr)
        return Exit.ERROR

    found = _LINE.search(text)
    before = found.group("value").strip("'\"") if found is not None else None
    if before == name:
        print(f"use case: already {name} in {target}; nothing changed")
        return Exit.OK
    if found is not None:
        rewritten = (
            text[: found.start()]
            + f"{_spaced(found.group('key'))}{name}{found.group('rest')}"
            + text[found.end() :]
        )
    else:
        newline = "\r\n" if "\r\n" in text else "\n"
        tail = "" if not text or text.endswith("\n") else newline
        rewritten = f"{text}{tail}use_case: {name}{newline}"
    # The setup is read as it would be with the line switched, before anything
    # is written: a setup that would not load is left exactly as it was.
    try:
        config = _switched(setup, target, rewritten)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {setup}: {exc}", file=sys.stderr)
        return Exit.ERROR
    except ConfigError as exc:
        print(
            f"error: {setup} would not load with use_case: {name}, so nothing was "
            f"written: {exc}",
            file=sys.stderr,
        )
        return Exit.ERROR
    try:
        mode = target.stat().st_mode & 0o7777 if target.exists() else None
        atomic.write(target, rewritten.encode("utf-8"))
        if mode is not None:
            os.chmod(target, mode)
    except OSError as exc:
        print(f"error: cannot write {target}: {exc}", file=sys.stderr)
        return Exit.ERROR

    shown = before if before else f"{MCGYVR_CODE} (unset)"
    print(f"use case: {shown} -> {name} in {target}")
    ran = stages(config)
    if config.is_raw:
        print(
            f"{name} serves its model raw: no stage runs, and `mcgyvr PROMPT` and "
            f"`mcgyvr direct` refuse."
        )
    else:
        print("stages on: " + (", ".join(s for s, on in ran.items() if on) or "none"))
        off = [s for s, on in ran.items() if not on]
        if off:
            print("stages off (switched off or unbound): " + ", ".join(off))
    return Exit.OK


def _spaced(key: str) -> str:
    """`key` with the space YAML needs before a value, when it has none."""
    return key if key.endswith((" ", "\t")) else f"{key} "


def _switched(setup: Path, target: Path, rewritten: str) -> Config:
    """The setup at `setup` as it loads with `target` holding `rewritten`."""
    if setup.is_file():
        return parse(rewritten, path=setup.resolve().parent)
    relief = setup / RELIEF_FILENAME
    return parse(
        (setup / FLEET_FILENAME).read_text(encoding="utf-8"),
        rewritten,
        path=setup,
        relief_text=relief.read_text(encoding="utf-8") if relief.exists() else "",
    )


def _refusal(name: str) -> str | None:
    """Why `name` is not a use case `use` switches to, or None when it is."""
    if name in USE_CASES:
        return None
    retired = RETIRED_USE_CASES.get(name)
    if retired is not None:
        return retired
    offered = ", ".join(USE_CASES[:-1]) + f" or {USE_CASES[-1]}"
    return f"`{name}` is not a use case: pick {offered}"
