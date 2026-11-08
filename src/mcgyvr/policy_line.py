"""Rewrite one top-level key of a setup's policy, every other byte kept.

`mcgyvr use NAME` switches `use_case:` with it, and `mcgyvr rig rungs sync
--ride-scope` sets `ride_scope:`. In a setup folder the key's line of
`policy.yaml` is rewritten, or added at the end when the policy names none; a
setup written as one document has its own top-level line rewritten. The setup
is loaded with the rewritten text (`loads_with`) before anything is written
(`write`), so a setup that would not load is left exactly as it was.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.config import (
    CREW_FILENAME,
    FLEET_FILENAME,
    POLICY_FILENAME,
    RELIEF_FILENAME,
    Config,
    parse,
)


def _line(key: str) -> re.Pattern[str]:
    """The top-level `key:` line: its key (after a byte-order mark on the first
    line), its value (bare, quoted or empty) and whatever follows the value on
    the line, a comment and a CR included."""
    return re.compile(
        rf"^(?P<key>\ufeff?{re.escape(key)}:[ \t]*)"
        r"(?P<value>\"[^\"\n]*\"|'[^'\n]*'|[^\s#]*)"
        r"(?P<rest>[^\n]*)$",
        re.MULTILINE,
    )


@dataclass(frozen=True)
class Rewrite:
    """One key's line rewritten in `target`, the file of `setup` holding it."""

    setup: Path
    target: Path
    #: The value the line held, None when the policy names none.
    before: str | None
    #: The file's whole text with the line rewritten (or added).
    text: str


def target_of(setup: Path) -> Path:
    """The file of `setup` holding its policy: the setup itself when it is
    one document, else its folder's `policy.yaml`."""
    return setup if setup.is_file() else setup / POLICY_FILENAME


def rewrite(setup: Path, key: str, value: str) -> Rewrite:
    """`setup`'s policy text with `key: value` in place of its `key:` line.

    Raises OSError or UnicodeDecodeError when the file cannot be read."""
    target = target_of(setup)
    # Bytes, not text: the line endings come back exactly as they were.
    text = target.read_bytes().decode("utf-8") if target.exists() else ""
    found = _line(key).search(text)
    before = found.group("value").strip("'\"") if found is not None else None
    if found is not None:
        rewritten = (
            text[: found.start()]
            + f"{_spaced(found.group('key'))}{value}{found.group('rest')}"
            + text[found.end() :]
        )
    else:
        newline = "\r\n" if "\r\n" in text else "\n"
        tail = "" if not text or text.endswith("\n") else newline
        rewritten = f"{text}{tail}{key}: {value}{newline}"
    return Rewrite(setup=setup, target=target, before=before, text=rewritten)


def loads_with(change: Rewrite, *, relief_kept: bool = True) -> Config:
    """The setup as it loads with the rewritten text (without `relief.yaml`
    when not `relief_kept`: a sync rewrites it). Raises `ConfigError` when it
    would not, and OSError or UnicodeDecodeError on a file that cannot be
    read."""
    setup = change.setup
    if setup.is_file():
        return parse(change.text, path=setup.resolve().parent)
    relief = setup / RELIEF_FILENAME if relief_kept else None
    crew = setup / CREW_FILENAME
    return parse(
        (setup / FLEET_FILENAME).read_text(encoding="utf-8"),
        change.text,
        path=setup,
        relief_text=(
            relief.read_text(encoding="utf-8")
            if relief is not None and relief.exists()
            else ""
        ),
        crew_text=crew.read_text(encoding="utf-8") if crew.exists() else "",
    )


def write(change: Rewrite) -> None:
    """Write the rewritten text, keeping the file's mode. Raises OSError."""
    target = change.target
    mode = target.stat().st_mode & 0o7777 if target.exists() else None
    atomic.write(target, change.text.encode("utf-8"))
    if mode is not None:
        os.chmod(target, mode)


def _spaced(key: str) -> str:
    """`key` with the space YAML needs before a value, when it has none."""
    return key if key.endswith((" ", "\t")) else f"{key} "
