"""The product revision under test, pinned as a digest, and the round it belongs to.

Issue: `#231 <https://github.com/AdarGit008/mcgyvr/issues/231>`_, check 3.
ADR-0018: *"Every arm in a round runs against one product revision; an adopted
change lands at the round boundary, never mid-flight. Without this a winning arm
silently re-baselines its own siblings and comparability — the entire point of
one bench — is lost."*

**What was missing.** The bench pinned its *tasks* (``tasks_sha256``) and its
system prompt (``bundle_sha256``, which hashes ``prompt.system`` and nothing
else). Everything between those two — the user-message render, the reply parser,
the runner, and the whole of ``Gate.run`` that decides pass or fail — was
unpinned. Two arms measured a week apart could therefore be scored by two
different bars and laid in one table, and no manifest on disk would say so.

**Why a content digest and not the git SHA.** A commit id describes a tree, not
a working directory, and every measurement in this project is dispatched from a
working directory. ``git rev-parse HEAD`` on a dirty tree names a revision that
was not the one under test, which is worse than naming none. The digest below is
over file *contents*, so it is true of what actually ran.

**Why the surface is coarse.** The obvious alternative is a curated list of the
modules a bench dispatch touches. This project has already paid for that shape
once: ``report.COMPARABLE`` named five fields, and a manifest mutated in the
sixth produced a byte-identical report. A guard that names a subset does not
refuse what it omits — it permits it silently, which reads as having checked. So
the surface is *the product*: every module under ``src/mcgyvr``, plus the rig
files that dispatch and score. An unrelated edit closing a round is the cost
ADR-0018 admitted ("one pinned revision per round means a win waits for a
boundary"); a missed edit corrupting a contrast is the failure it exists to
prevent, and only one of those two is recoverable.

**What the surface deliberately excludes.** ``tools/bench/tasks/`` — the task set
is already pinned per run by ``tasks_sha256``, and folding it in here would close
a round every time a problem is authored, which is corpus work and not a product
change. ``tests/`` — a test cannot change what a worker is sent or how a
candidate is scored. ``records/`` and ``docs/`` for the same reason.

**Rounds are append-only.** ``rounds.json`` carries the whole history, newest
last, and the open round is the final entry. A round is closed by opening the
next one, which is the only place an adopted change may land; the new entry
names what was adopted. Editing a closed round's digest would retroactively
re-describe measurements already on disk, which is the failure mode this file
exists to make impossible, so ``open_round`` only ever appends.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ROUNDS_FILE = Path(__file__).resolve().parent / "rounds.json"

# The product under test, as paths relative to the repo root. A directory
# contributes every ``*.py`` beneath it; a file contributes itself. This module
# is in the list on purpose — the digest algorithm is part of what the digest
# claims, and a change to it must move the number it produces.
SURFACE: tuple[str, ...] = (
    # The product: prompt assembly, the reply parser, the runner, the sandbox,
    # the contract loader, the scope matcher, and the whole of the gate.
    "src/mcgyvr",
    # The rig that dispatches, and the rig it imports by path for the bundle.
    "tools/breadth/measure.py",
    "tools/bundle/measure.py",
    # The scorer the bench wraps `Gate.run` in, and the conditions as data.
    "tools/bench/score.py",
    "tools/bench/matrix.py",
    "tools/bench/matrix.json",
    "tools/bench/product.py",
)


class ProductError(Exception):
    """The surface cannot be read, or the tree does not match the open round."""


def surface_files(repo: Path = REPO) -> list[Path]:
    """Every file in the declared surface, sorted by repo-relative path.

    A declared entry that does not exist raises rather than contributing
    nothing: a rig file deleted or renamed would otherwise shrink the surface
    silently, and a smaller surface is a weaker pin that looks identical from
    the outside.
    """
    found: list[Path] = []
    for entry in SURFACE:
        path = repo / entry
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*.py") if p.is_file()))
        elif path.is_file():
            found.append(path)
        else:
            raise ProductError(
                f"the declared product surface names {entry}, which is not a "
                "file or a directory in this tree; a surface entry that has "
                "moved must be re-declared, not dropped"
            )
    return sorted(found, key=lambda p: p.relative_to(repo).as_posix())


def _lines(repo: Path) -> Iterator[str]:
    for path in surface_files(repo):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        yield f"{path.relative_to(repo).as_posix()} {digest}"


def digest(repo: Path = REPO) -> str:
    """The product revision: one digest over path-and-content of the surface.

    Paths are in the hashed text, not just contents, so a rename or a deletion
    moves the digest even when every byte of every surviving file is unchanged.
    """
    body = "\n".join(_lines(repo)) + "\n"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_rounds(path: Path = ROUNDS_FILE) -> list[dict[str, Any]]:
    """Every round ever opened, oldest first."""
    if not path.is_file():
        raise ProductError(f"{path} does not exist; no round has been opened")
    data = json.loads(path.read_text(encoding="utf-8"))
    rounds = data.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise ProductError(f"{path} declares no rounds")
    return rounds


def open_round(path: Path = ROUNDS_FILE) -> dict[str, Any]:
    """The round now accepting measurements: the last entry, always."""
    return load_rounds(path)[-1]


def require_pinned(repo: Path = REPO, path: Path = ROUNDS_FILE) -> tuple[str, str]:
    """The open round's id and digest, or a refusal naming what moved.

    This is check 3's teeth. Stamping the revision into a manifest records what
    ran; refusing to dispatch when the tree has moved off the open round is what
    makes "an adopted change lands at the round boundary, never mid-flight" a
    property of the bench rather than a promise in a document.
    """
    current = open_round(path)
    declared = current.get("product_sha256")
    measured = digest(repo)
    if declared != measured:
        raise ProductError(
            f"the product has moved off round `{current['id']}`: it pins "
            f"{declared} and this tree is {measured}. Every arm in a round runs "
            "against one revision (ADR-0018), so this dispatch would put two "
            "revisions in one table. Either restore the tree, or close the "
            "round by opening the next one:\n"
            "  uv run --no-sync python tools/bench/product.py --open <id> "
            '--why "what was adopted at this boundary"\n'
            "Opening a round re-baselines: arms measured under the old one are "
            "not comparable with arms measured under the new one.\n"
            f"Changed: {', '.join(_moved(repo, current)) or 'unknown'}"
        )
    return str(current["id"]), measured


def declare(manifest: dict[str, Any] | Any) -> str:
    """The one-line round declaration a report puts above its figures.

    A manifest with no round is described as such rather than skipped. Those
    runs exist, they are readable, and what is true of them — that nothing
    recorded the revision that produced them — is a fact a reader needs in order
    to know not to lay them beside a round's arms.
    """
    round_id = manifest.get("round")
    revision = manifest.get("product_sha256")
    if not round_id or not revision:
        return (
            "- round: **none recorded** — this run predates #231's product pin, "
            "so the revision that produced it is unknown and it cannot be laid "
            "beside an arm measured in a round"
        )
    return (
        f"- round: **`{round_id}`**, product `{revision[:12]}` — every arm in "
        "this round ran against one revision, and an adopted change lands only "
        "at the boundary (ADR-0018)"
    )


def banner(found: Any) -> str:
    """The round declaration for a figure read across several run directories.

    A mixture is named rather than refused. Unlike the mode, two revisions in
    one figure is a defect ``report.require_comparable`` already refuses where
    it matters — inside a contrast — and these tools also draw honest
    cross-round descriptions (rig health, a superseded pair kept beside its
    replacement). Saying "three revisions" is the fact; deciding whether that
    invalidates the figure is the reader's, and the tools that must not permit
    it refuse it themselves.
    """
    found = list(found)
    if not found:
        return (
            "- round: **none recorded** — no manifest was read for this figure, "
            "so nothing here names the revision under test"
        )
    pins = {(m.get("round"), m.get("product_sha256")) for m in found}
    if len(pins) == 1:
        return declare(found[0] if found else {})
    named = sorted(str(r) for r, _ in pins if r)
    return (
        f"- round: **mixed** — this figure is read across {len(pins)} product "
        f"revisions ({', '.join(named) or 'none recorded'}); a contrast between "
        "them would vary the code under test as well as the condition"
    )


def _moved(repo: Path, current: dict[str, Any]) -> list[str]:
    """Which surface files differ from the ones the open round recorded.

    Best-effort and for the error message only. A round opened before the
    per-file map existed carries none, and the refusal above still stands on the
    digest alone — the list explains a refusal, it never causes or excuses one.
    """
    recorded = current.get("files")
    if not isinstance(recorded, dict):
        return []
    now = {line.split(" ")[0]: line.split(" ")[1] for line in _lines(repo)}
    changed = [
        p for p in sorted(set(recorded) | set(now)) if recorded.get(p) != now.get(p)
    ]
    return changed


def _open_cli(args: argparse.Namespace) -> int:
    rounds = load_rounds() if ROUNDS_FILE.is_file() else []
    if any(r.get("id") == args.open for r in rounds):
        raise ProductError(
            f"round `{args.open}` already exists; rounds are append-only"
        )
    entry: dict[str, Any] = {
        "id": args.open,
        "opened": args.opened,
        "issue": args.issue,
        "product_sha256": digest(),
        "why": args.why,
        "files": {line.split(" ")[0]: line.split(" ")[1] for line in _lines(REPO)},
    }
    payload = {"rounds": [*rounds, entry]}
    ROUNDS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"opened round `{entry['id']}` at {entry['product_sha256']}")
    print(f"{len(entry['files'])} files in the surface")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--digest", action="store_true", help="print this tree's digest"
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the tree against the open round"
    )
    parser.add_argument(
        "--open", metavar="ID", help="close the open round by appending a new one"
    )
    parser.add_argument("--why", default="", help="what was adopted at this boundary")
    parser.add_argument(
        "--opened", default="", help="the date the round opened (UTC, YYYY-MM-DD)"
    )
    parser.add_argument(
        "--issue", type=int, default=None, help="the issue the round belongs to"
    )
    args = parser.parse_args(argv)

    try:
        if args.open:
            if not args.why or not args.opened:
                raise ProductError(
                    "--open needs --why and --opened; a round nobody can date "
                    "or explain is a stamp"
                )
            return _open_cli(args)
        if args.digest:
            print(digest())
            return 0
        current = open_round()
        round_id, measured = require_pinned()
    except ProductError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"round `{round_id}` — opened {current.get('opened')}, "
        f"issue #{current.get('issue')}"
    )
    print(f"product_sha256 {measured}")
    print(f"{len(surface_files())} files in the surface, and the tree matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
