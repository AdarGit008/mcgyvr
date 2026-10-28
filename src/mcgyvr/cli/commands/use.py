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
import re
import sys
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.cli.common import add_config
from mcgyvr.config import (
    FLEET_FILENAME,
    MCGYVR_CODE,
    POLICY_FILENAME,
    RETIRED_USE_CASES,
    USE_CASES,
    ConfigError,
    config_path,
    load,
    stages,
)
from mcgyvr.exits import Exit

#: The top-level `use_case:` line: its key, its value (bare or quoted) and
#: whatever follows the value on the line, a comment included.
_LINE = re.compile(
    r"^(?P<key>use_case:[ \t]*)"
    r"(?P<value>\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)"
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
            "serve the model raw, and run and delegate refuse under them."
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
        text = target.read_text(encoding="utf-8") if target.exists() else ""
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
            + f"{found.group('key')}{name}{found.group('rest')}"
            + text[found.end() :]
        )
    else:
        tail = "" if not text or text.endswith("\n") else "\n"
        rewritten = f"{text}{tail}use_case: {name}\n"
    try:
        atomic.write(target, rewritten)
    except OSError as exc:
        print(f"error: cannot write {target}: {exc}", file=sys.stderr)
        return Exit.ERROR

    print(f"use case: {before or MCGYVR_CODE + ' (unset)'} -> {name} in {target}")
    try:
        config = load(setup)
    except ConfigError as exc:
        print(
            f"error: the setup does not load after the switch: {exc}", file=sys.stderr
        )
        return Exit.ERROR
    ran = stages(config)
    if config.is_raw:
        print(
            f"{name} serves its model raw: no stage runs, and `mcgyvr run` and "
            f"`mcgyvr delegate` refuse."
        )
    else:
        print("stages on: " + (", ".join(s for s, on in ran.items() if on) or "none"))
        off = [s for s, on in ran.items() if not on]
        if off:
            print("stages off by the policy: " + ", ".join(off))
    return Exit.OK


def _refusal(name: str) -> str | None:
    """Why `name` is not a use case `use` switches to, or None when it is."""
    if name in USE_CASES:
        return None
    retired = RETIRED_USE_CASES.get(name)
    if retired is not None:
        return retired
    offered = ", ".join(USE_CASES[:-1]) + f" or {USE_CASES[-1]}"
    return f"`{name}` is not a use case: pick {offered}"
