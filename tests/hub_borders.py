"""Where the hub may be known in the product, as data, and the lists that only shrink.

The product is offline and for one user. The hub — other people's cards,
brokered — is reached through the hub client, ``src/mcgyvr/rig/``, and the
``mcgyvr rig`` command in ``src/mcgyvr/cli.py``. Everything else under
``src/mcgyvr/`` is the *offline core* (:func:`in_core`). Two checks share this
module:

* ``tests/test_only_the_command_line_imports_the_hub_client.py`` holds the
  core to importing nothing of the hub client (nor the command line, which
  imports it); :data:`IMPORTS_NOT_YET_MOVED` lists the imports it still has.
* ``tests/test_the_offline_core_names_the_hub_no_more_than_it_does_today.py``
  holds the core to the hub words it holds today
  (:data:`WORDS_NOT_YET_MOVED`).

Both lists only shrink. Each check demands that the tree holds exactly its
list, so a list cannot keep slack a later change would refill. What a tree
cannot show is the list as it was, so on a pull request CI runs::

    python3 tests/hub_borders.py --compare <the base branch's copy of this file>

and it fails when a list grew (an entry added, a count raised), when a word
was dropped from :data:`HUB_WORDS` or its pattern changed, when the core
lost a place (:data:`NOT_CORE_FILES`, :data:`NOT_CORE_DIRS` gained one), when
``hub`` stopped being read in one more file (:data:`HF_HUB_FILES` gained one), or
when :data:`HUB_CLIENT` moved. The base's copy is read, never run: each value
here is a literal, and the comparison reads the literals out of the syntax
tree. The growth rule is the one the list of uninvented machines is held to
(:func:`tests.uninvented_machines.growth`). Standard library only, so the
CI job needs no install.

The words
---------
Each word is read in its three spellings — ``relief``, ``Relief``,
``RELIEF`` — where no lower-case letter is before it, so ``github`` and
``screw`` hold none and ``ReliefUnavailableError``, ``_RELIEF_ONLY`` and
``on_hub_error`` hold one each. ``hub`` is not read after ``HF_``,
``HUGGING_FACE_`` or ``GIT``. Every other ``Hub`` is read, except in the files
that name the Hugging Face Hub (:data:`HF_HUB_FILES`), where ``hub`` in any
spelling is not read and every other word is.

Not read, because they are not the hub's alone: ``ride`` (a path that rides
along a change), ``lend``/``lent`` (a llama.cpp worker lends its card to a
server of the same fleet). Their hub sense is still in the core, for
example ``escalate.py``'s ``_ride``, ``gate/preflight.py`` on a ride's reply
cap and ``drive.py`` on a ride's wire field; no pattern was found that reads
the hub sense and not the other.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "mcgyvr"

#: The hub client's package.
HUB_CLIENT = "mcgyvr.rig"

#: What is not the offline core, relative to ``src/mcgyvr/``: the command line
#: and the hub client. These may only lose an entry.
NOT_CORE_FILES = frozenset({"cli.py"})
NOT_CORE_DIRS = frozenset({"rig"})

#: The files of the core where ``hub`` is the Hugging Face Hub (its API, the
#: ``HUB`` address, ``HubFile``, the ``hub-api`` tag, the Hub downloads are
#: fetched from), relative to ``src/mcgyvr/``. The word ``hub`` is not read in
#: them, so their prose about that Hub is not held to a count; every other
#: hub word is. This may only lose an entry.
HF_HUB_FILES = frozenset(
    {
        "knowledge/__init__.py",
        "knowledge/boards.py",
        "knowledge/online.py",
        "knowledge/record.py",
        "knowledge/store.py",
        "serving/fetcher.py",
        "serving/fetchlist.py",
        "serving/gate-scripts/serve-fetch.py",
        "serving/run.py",
    }
)

#: The imports into the hub client, or into the command line, from the offline
#: core that the tree still has, as ``(importer, imported)``: a module by its
#: dotted name, a script that no import reaches by its path under
#: ``src/mcgyvr/``. Entries may only be removed, never added. It is empty: the
#: last one, the pooled session's sandbox reading the WireGuard key's shape from
#: ``rig.sessionwire``, left when that sandbox moved into ``rig/`` as
#: ``rig/pooled.py`` (borders plan, step 2d).
IMPORTS_NOT_YET_MOVED: frozenset[tuple[str, str]] = frozenset()

#: The words that name the hub or what it brokers, each with the pattern that
#: reads it (see the module docstring). ``crew`` and ``pool session`` are
#: absent from the core today and read so that they stay absent. Words may
#: not be dropped, nor a pattern changed, by a pull request.
HUB_WORDS = {
    "hub": r"(?<![a-z])(?<!HF_)(?<!HUGGING_FACE_)(?<!GIT)(?:hub|Hub|HUB)",
    "hitchhik": r"(?<![a-z])(?:hitchhik|Hitchhik|HITCHHIK)",
    "relief": r"(?<![a-z])(?:relief|Relief|RELIEF)",
    "rider": r"(?<![a-z])(?:rider|Rider|RIDER)",
    "crew": r"(?<![a-z])(?:crew|Crew|CREW)",
    "pool session": r"(?<![a-z])(?:pool|Pool|POOL)[ _.-]?(?:session|Session|SESSION)",
    "pooled": r"(?<![a-z])(?:pooled|Pooled|POOLED)",
}

#: Every file of the offline core that holds a hub word, relative to
#: ``src/mcgyvr/``, with how many of each. Entries may only be lowered or
#: removed, never added or raised.
WORDS_NOT_YET_MOVED: dict[str, dict[str, int]] = {
    "capacity.py": {"hub": 2, "relief": 10, "rider": 1},
    "config.py": {"hub": 18, "hitchhik": 3, "relief": 68, "rider": 19},
    "contract.py": {"relief": 1, "rider": 1},
    "docgen.py": {"hub": 1, "relief": 5},
    "emit.py": {"hitchhik": 1, "rider": 1},
    "escalate.py": {"hub": 5, "relief": 47, "rider": 8},
    "fleet/files.py": {"hub": 2, "hitchhik": 1, "relief": 26, "rider": 2},
    "initialize.py": {"relief": 4},
    "local_pool.py": {"hub": 4, "relief": 40, "rider": 2},
    "route.py": {"relief": 3},
    "runner.py": {"hub": 11, "hitchhik": 1, "relief": 15, "rider": 2, "pooled": 2},
    "weights.py": {"relief": 1},
    "whole.py": {"hub": 1},
}


def in_core(rel: str) -> bool:
    """Whether a path under ``src/mcgyvr/`` is in the offline core."""
    return rel not in NOT_CORE_FILES and rel.split("/", 1)[0] not in NOT_CORE_DIRS


def core_files(repo: Path = REPO) -> list[str]:
    """Every file git tracks in the offline core, relative to ``src/mcgyvr/``.
    Tracked only, so a stray file in a checkout neither fails nor passes it."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", "src/mcgyvr"],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", "surrogateescape")
    rels = (p.removeprefix("src/mcgyvr/") for p in out.split("\0") if p)
    return sorted(rel for rel in rels if in_core(rel) and (SRC / rel).is_file())


def counted(text: str) -> dict[str, int]:
    """How many of each hub word ``text`` holds, words it holds none of left out."""
    counts = {word: len(re.findall(p, text)) for word, p in HUB_WORDS.items()}
    return {word: n for word, n in counts.items() if n}


def scan_words(repo: Path = REPO) -> dict[str, dict[str, int]]:
    """Every file of the offline core that holds a hub word, with the counts;
    ``hub`` left unread in :data:`HF_HUB_FILES`."""
    found: dict[str, dict[str, int]] = {}
    for rel in core_files(repo):
        text = (repo / "src" / "mcgyvr" / rel).read_text("utf-8", errors="replace")
        counts = counted(text)
        if rel in HF_HUB_FILES:
            counts.pop("hub", None)
        if counts:
            found[rel] = counts
    return found


def as_counts(edges: frozenset[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Edges in the shape the growth rule compares: importer, imported, 1."""
    table: dict[str, dict[str, int]] = {}
    for importer, imported in edges:
        table.setdefault(importer, {})[imported] = 1
    return table


@dataclass(frozen=True)
class Borders:
    """The values a pull request may only narrow, as one copy of this file
    holds them."""

    hub_client: str
    not_core_files: frozenset[str]
    not_core_dirs: frozenset[str]
    hf_hub_files: frozenset[str]
    hub_words: dict[str, str]
    imports: frozenset[tuple[str, str]]
    words: dict[str, dict[str, int]]


def _literal(node: ast.expr) -> Any:
    """A literal, with ``frozenset({...})`` read as the set it wraps."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) <= 1
        and not node.keywords
    ):
        return frozenset(ast.literal_eval(node.args[0]) if node.args else ())
    return ast.literal_eval(node)


def read_borders(text: str, *, source: str) -> Borders:
    """The borders a copy of this file states, read from its syntax tree and
    never run."""
    values: dict[str, Any] = {}
    for node in ast.parse(text, filename=source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            try:
                values[target.id] = _literal(value)
            except ValueError:
                continue
    names = (
        "HUB_CLIENT",
        "NOT_CORE_FILES",
        "NOT_CORE_DIRS",
        "HF_HUB_FILES",
        "HUB_WORDS",
        "IMPORTS_NOT_YET_MOVED",
        "WORDS_NOT_YET_MOVED",
    )
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"{source}: no literal {', '.join(missing)}")
    return Borders(*(values[name] for name in names))


def narrowed(old: Borders, new: Borders) -> list[str]:
    """Each way ``new`` lets through what ``old`` did not."""
    from tests.uninvented_machines import growth

    found = [f"words: {line}" for line in growth(old.words, new.words)]
    found += [
        f"imports: {line}"
        for line in growth(as_counts(old.imports), as_counts(new.imports))
    ]
    for word, pattern in sorted(old.hub_words.items()):
        if word not in new.hub_words:
            found.append(f"HUB_WORDS: {word!r} was dropped")
        elif new.hub_words[word] != pattern:
            found.append(f"HUB_WORDS: the pattern of {word!r} changed")
    found += [
        f"{name}: {rel!r} left the core"
        for name, before, after in (
            ("NOT_CORE_FILES", old.not_core_files, new.not_core_files),
            ("NOT_CORE_DIRS", old.not_core_dirs, new.not_core_dirs),
        )
        for rel in sorted(after - before)
    ]
    found += [
        f"HF_HUB_FILES: 'hub' is no longer read in {rel!r}"
        for rel in sorted(new.hf_hub_files - old.hf_hub_files)
    ]
    if new.hub_client != old.hub_client:
        found.append(f"HUB_CLIENT: {old.hub_client!r} -> {new.hub_client!r}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 tests/hub_borders.py",
        description="Fail if the hub's borders let through more than OLD did.",
    )
    parser.add_argument(
        "--compare", metavar="OLD", type=Path, required=True, help="the base's copy"
    )
    args = parser.parse_args(argv)
    here = Path(__file__)
    try:
        old = read_borders(
            args.compare.read_text(encoding="utf-8"), source=str(args.compare)
        )
        new = read_borders(here.read_text(encoding="utf-8"), source=str(here))
    except (ValueError, SyntaxError) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    found = narrowed(old, new)
    for line in found:
        print(f"grew: {line}")
    print(
        "the hub's borders "
        + ("let through more than the base's" if found else "did not widen")
    )
    return 1 if found else 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))  # run by its path: import tests.uninvented_machines
    sys.exit(main())
