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

**The bar is configuration as much as code, and both are in** (ADR-0032, #291).
The surface was code-only for its first round, and the grouping in
``identity.py`` justified filing ``round`` and ``product_sha256`` under the *bar*
on the ground that "the revision they pin includes the scorer". It included the
scorer and not the scorer's configuration, which is where half the bar actually
lives: ``score.lint_config`` derives the workspace ruff settings from
``pyproject.toml`` at call time, ``score.stage_js_toolchain`` copies
``eslint.config.mjs`` into every workspace, and the checkers themselves are
whatever ``uv.lock`` and ``package-lock.json`` resolve to. A rule flipped off in
either config file, or a checker moved by a lockfile bump, narrows what the gate
rejects — and until this change the digest did not move and no round refused.
Both lockfiles, never one: the arms are paired ts/py (ADR-0021, ADR-0025), and
pinning Python's checker while JavaScript's floats puts a language effect inside
every contrast the bench will publish.

**A directory contributes every file beneath it, whatever the extension.** It
globbed ``*.py``, so ``src/mcgyvr/prompts/*.md`` — the system prompts, the
literal text a worker is sent — sat outside the digest of the thing that sends
them. The only exclusion is a path derived from files already hashed here
(``__pycache__/``, ``*.pyc``): including those would make the pin depend on
whether the tree had been imported rather than on what it contains. Everything
else under a declared directory is in, including a file authored and not yet
committed — enumeration is the filesystem's and not ``git ls-files``', because a
new file dispatched before it is committed is exactly the unpinned code this
refusal exists to catch.

**What the surface deliberately excludes.** ``tools/bench/tasks/`` — the task set
is already pinned per run by ``tasks_sha256``, and folding it in here would close
a round every time a problem is authored, which is corpus work and not a product
change. ``data/task-catalog.json`` is a different thing and *is* in: it is the
vocabulary a contract is validated against, read by the product at run time, not
the set of problems. ``tests/`` — a test cannot change what a worker is sent or
how a candidate is scored. ``records/`` and ``archive/`` for the same reason. And
the read-time tools — ``report.py``, ``identity.py``, ``mode.py`` — which
describe runs already on disk and neither dispatch nor score; a change to how a
table is printed must not re-baseline the measurements it prints.

**Rounds are append-only.** ``rounds.json`` carries the whole history, newest
last, and the open round is the final entry. A round is closed by opening the
next one, which is the only place an adopted change may land; the new entry
names what was adopted. Editing a closed round's digest would retroactively
re-describe measurements already on disk, which is the failure mode this file
exists to make impossible, so ``open_round`` only ever appends.

**And every pending identity change lands in the same boundary** (ADR-0032,
#291). The paragraph above is true and is half the rule: it says *a* change
lands at a boundary, and a driver who reads only that concludes their own change
warrants a round of its own. It does not. Landing three identity changes
piecemeal, with runs between them, converts one re-baseline into three
incomparable ones — each round's arms measurable only against each other, and
the rig time spent three times. So the boundary is *drained*, not *taken*: every
adopted change waiting on a round goes in together, and ``--open`` refuses
without ``--adopted``, which is where the driver names the batch. That happened
for real on lane/261 on 2026-08-16, where a driver read this docstring and
recommended a round for one change; the recommendation was withdrawn only
because someone re-read a closed issue. The rule now lives in
``rounds.json``'s ``doctrine`` block — data the tool reads and prints back — so
a fourth driver cannot route around it by not knowing.

The tool **records** the batch; it cannot **verify** it. Nothing here can know
which issues are still open, and gating a judgement call on a heuristic would
teach drivers to work around the tool rather than the rule. What ``--open``
enforces is that the batch is named and the moved files are shown at the moment
the round closes, which is the one moment the rule is violable.
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
# contributes every file beneath it whatever its extension; a file contributes
# itself. This module is in the list on purpose — the digest algorithm is part
# of what the digest claims, and a change to it must move the number it
# produces.
SURFACE: tuple[str, ...] = (
    # The product: prompt assembly, the reply parser, the runner, the sandbox,
    # the contract loader, the scope matcher, the system prompts under
    # `prompts/`, and the whole of the gate.
    "src/mcgyvr",
    # The rig that dispatches, and the rig it imports by path for the bundle.
    "tools/breadth/measure.py",
    "tools/bundle/measure.py",
    # The scorer the bench wraps `Gate.run` in, and the conditions as data.
    "tools/bench/score.py",
    "tools/bench/matrix.py",
    "tools/bench/matrix.json",
    "tools/bench/product.py",
    # The bar as configuration. `score.lint_config` reads `pyproject.toml` at
    # call time and `score.stage_config` copies `eslint.config.mjs` and
    # `prettier.config.mjs` into every workspace, so a rule flipped in any of
    # them moves what the gate rejects without touching a line of scorer code.
    # ADR-0025 clause 1 makes the eslint config the *project's* standard — it
    # binds the gate, not just the bench.
    #
    # `prettier.config.mjs` joined this list in the change that created it
    # (#262, ADR-0035). Until then the JS/TS format bar was prettier's built-in
    # defaults, pinned only through `package-lock.json` — the version was
    # covered and the settings were not, because there were none to cover. A
    # declared config that the pin did not hold would be this list's own defect
    # restated: the round would cover the scorer and not the scorer's
    # configuration, which is what ADR-0032 closed.
    "pyproject.toml",
    "eslint.config.mjs",
    "prettier.config.mjs",
    # The bar as implementation. `uv.lock` decides which ruff resolves under
    # `uv run` (250 rules as this project selects — the 328 that stood here was
    # a string-prefix count that swept in ten unselected linters, corrected on
    # #262) and `package-lock.json` decides which eslint, typescript-eslint and
    # prettier the workspace's linked `node_modules` supplies (66 enabled rules
    # for a `.ts` target). ADR-0025's consequence is explicit: pinning the
    # toolchain makes the checker version part of the instrument.
    "uv.lock",
    "package-lock.json",
    # The vocabulary a contract is validated against (`src/mcgyvr/catalog.py`,
    # `src/mcgyvr/contract.py`): what each task type means and which evidence
    # kinds it must carry. Not the task *set* — that is `tasks_sha256`.
    "data/task-catalog.json",
)

# The only paths a declared directory does not contribute: artifacts derived
# from files already in the digest. Including them would make the pin depend on
# whether the tree had been imported rather than on what it holds. This is the
# whole exclusion list, deliberately — every other curation this module could
# do is the curation it exists to refuse.
DERIVED_DIR = "__pycache__"
DERIVED_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")


class ProductError(Exception):
    """The surface cannot be read, or the tree does not match the open round."""


def _is_derived(path: Path) -> bool:
    """Whether this path is generated from a file already in the digest."""
    return DERIVED_DIR in path.parts or path.suffix in DERIVED_SUFFIXES


def surface_files(repo: Path = REPO, surface: tuple[str, ...] = SURFACE) -> list[Path]:
    """Every file in the declared surface, sorted by repo-relative path.

    ``surface`` defaults to the product's. The serving harness pins itself with
    the same shape over ``tools/bench/serving/`` (#325): it is not product, so
    it is not in :data:`SURFACE`, and a second digest algorithm for it would be
    a second thing to keep true. One algorithm, two declared surfaces.

    A declared entry that does not exist raises rather than contributing
    nothing: a rig file deleted or renamed would otherwise shrink the surface
    silently, and a smaller surface is a weaker pin that looks identical from
    the outside.

    A directory contributes **every** file beneath it, not every ``*.py``. The
    extension glob was how ``src/mcgyvr/prompts/*.md`` — the system prompts the
    worker is literally sent — stayed outside the digest of the code that sends
    them, and an extension is not a statement about whether a file can change a
    verdict. Only :func:`_is_derived` paths are dropped, and they are dropped
    because they are outputs of files already hashed here.
    """
    found: list[Path] = []
    for entry in surface:
        path = repo / entry
        if path.is_dir():
            found.extend(
                sorted(p for p in path.rglob("*") if p.is_file() and not _is_derived(p))
            )
        elif path.is_file():
            found.append(path)
        else:
            raise ProductError(
                f"the declared product surface names {entry}, which is not a "
                "file or a directory in this tree; a surface entry that has "
                "moved must be re-declared, not dropped"
            )
    return sorted(found, key=lambda p: p.relative_to(repo).as_posix())


def _lines(repo: Path, surface: tuple[str, ...] = SURFACE) -> Iterator[str]:
    for path in surface_files(repo, surface):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        yield f"{path.relative_to(repo).as_posix()} {digest}"


def digest(repo: Path = REPO, surface: tuple[str, ...] = SURFACE) -> str:
    """The product revision: one digest over path-and-content of the surface.

    Paths are in the hashed text, not just contents, so a rename or a deletion
    moves the digest even when every byte of every surviving file is unchanged.
    """
    body = "\n".join(_lines(repo, surface)) + "\n"
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


def load_doctrine(path: Path = ROUNDS_FILE) -> dict[str, Any]:
    """The rules a driver opening a round is bound by, as data (ADR-0032, #291).

    Doctrine lives in ``rounds.json`` rather than only in this docstring because
    the failure it prevents is a driver who did not read the docstring. A
    ``clause`` here is printed back at ``--open`` time, which is the one moment
    the rule can be broken, and a clause added to the file is a clause the tool
    starts stating without anyone touching this module.

    A file with no doctrine block yields an empty one rather than raising: the
    doctrine constrains the *judgement* a driver makes, and a round opened
    against an older file is still a round.
    """
    if not path.is_file():
        raise ProductError(f"{path} does not exist; no round has been opened")
    data = json.loads(path.read_text(encoding="utf-8"))
    doctrine = data.get("doctrine")
    return doctrine if isinstance(doctrine, dict) else {}


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
            '--opened <YYYY-MM-DD> --why "what this boundary is for" '
            '--adopted "#N what landed"\n'
            "Opening a round re-baselines: arms measured under the old one are "
            "not comparable with arms measured under the new one, so every "
            "identity change waiting on a boundary lands in this one rather "
            "than in a round of its own (ADR-0032).\n"
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
    # Read from the module globals rather than from each function's default
    # argument. A default is bound at definition time, so `load_rounds()` and
    # `digest()` would read the real repository while `_lines(REPO)` read a
    # substituted one — harmless in production, where they are the same paths,
    # and enough to write a round whose digest and file map describe two
    # different trees under any caller that redirects them.
    repo, rounds_file = REPO, ROUNDS_FILE
    rounds = load_rounds(rounds_file) if rounds_file.is_file() else []
    doctrine = load_doctrine(rounds_file) if rounds_file.is_file() else {}
    if any(r.get("id") == args.open for r in rounds):
        raise ProductError(
            f"round `{args.open}` already exists; rounds are append-only"
        )

    # The batching rule made operational (ADR-0032). The tool cannot know which
    # identity changes are still open, so it does not pretend to check — it
    # refuses to close a round the driver has not said the contents of, prints
    # the doctrine it is bound by, and prints what actually moved. A named batch
    # is a claim someone can be held to; a silent append is not.
    if not args.adopted:
        raise ProductError(
            "--open needs --adopted (repeatable), naming each change this "
            "boundary carries. A round boundary is drained, not taken: every "
            "identity change waiting on one lands in the same round, or one "
            "re-baseline becomes several incomparable ones (ADR-0032, ADR-0018 "
            "Q3). Name them:\n"
            '  --adopted "#291 the round pin covers the bar\'s configuration"\n'
            "If the batch is one change, say so — the refusal is that nobody "
            "said."
        )
    for clause in doctrine.get("clauses", []):
        print(f"doctrine: {clause}")
    if rounds:
        print(f"moved since `{rounds[-1].get('id')}`:")
        for path in _moved(repo, rounds[-1]) or ["(nothing this round recorded)"]:
            print(f"  {path}")

    entry: dict[str, Any] = {
        "id": args.open,
        "opened": args.opened,
        "issue": args.issue,
        "product_sha256": digest(repo),
        "why": args.why,
        "adopted": list(args.adopted),
        "files": {line.split(" ")[0]: line.split(" ")[1] for line in _lines(repo)},
    }
    payload: dict[str, Any] = {}
    if doctrine:
        payload["doctrine"] = doctrine
    payload["rounds"] = [*rounds, entry]
    rounds_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"opened round `{entry['id']}` at {entry['product_sha256']}")
    print(f"{len(entry['files'])} files in the surface")
    print(f"{len(entry['adopted'])} change(s) adopted at this boundary")
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
        "--adopted",
        action="append",
        default=[],
        metavar="CHANGE",
        help="one change this boundary carries; repeat for each. Required by "
        "--open: a boundary is drained of every pending identity change, not "
        "taken by one (ADR-0032)",
    )
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
