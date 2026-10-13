"""Prove a delete, or leave it unproved. Never agree one.

A test was marked for deletion twice over by two careful passes reading it,
and twice the reason given was a sentence: "the same setup and a subset of
the asserts in X". Two readers finding the same sentence persuasive is
agreement, not proof, and a test deleted on agreement is a test nobody can
get back the argument for.

So each claim is put to a measurement, and the claim stands or does not:

``dead``
    The claim is that the test says nothing about the product as it is. It
    is proved when the thing the test names is absent from the product's
    source **and** running the test produces no passing assertion about
    behaviour -- every outcome is an expected failure or a skip.

``redundant``
    The claim is that another test already says it. It is proved when every
    line of the product that the candidate runs is also run by the keeper
    (so the keeper exercises everything the candidate does) **and** every
    assertion the candidate makes appears, normalised, among the keeper's
    (so the keeper asks for everything the candidate asks for). Lines are
    counted with sys.settrace, which is in the standard library, so this
    tool needs nothing installed.

``gone-redundant``
    The same claim about a test that has already been deleted -- on the
    agreement this tool exists to replace, before it existed. The file is
    recovered from the commit that removed it, and the assertion half of
    the proof is taken from that. The line half cannot be taken without
    putting the test back, and the verdict says so rather than implying a
    whole proof. git keeps the file, so the claim stays answerable; a
    delete is not a thing that stops being checkable.

Containment is one-way on purpose: the keeper may do more. What would make
the claim false is the candidate running a line, or asking a question, that
the keeper does not.

    uv run --no-sync python tests/prove_delete.py            # show verdicts
    uv run --no-sync python tests/prove_delete.py --write    # record them
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

LEDGER = Path("tests/DELETES.tsv")
COLUMNS = ("path", "kind", "keeper", "verdict", "evidence")


def root() -> Path:
    """The checkout, by marker, never by a count of parents."""
    here = Path(__file__).resolve()
    for folder in here.parents:
        if all((folder / m).exists() for m in ("Makefile", "pyproject.toml")):
            return folder
    raise RuntimeError(f"no Makefile + pyproject.toml above {here}")


#: Where the code under test lives: this repository's own package.
WATCHED = ("src",)


def sources(repo: Path) -> set[Path]:
    """The source files a test is measured against."""
    found: set[Path] = set()
    for where in WATCHED:
        folder = repo / where
        if folder.is_dir():
            found |= {path.resolve() for path in folder.rglob("*.py")}
    return found


def trace_one(test: str, watched: set[Path], *, collect_only: bool) -> set[str]:
    """Trace one pytest run in **this** interpreter and return `file:line`.

    Called only in the fresh subprocess :func:`lines_run` starts, because a
    second run in one interpreter imports nothing again: every module is
    already in ``sys.modules``, and the import-time lines that must be told
    apart from the run's own would go unseen.
    """
    import pytest

    seen: set[str] = set()
    names = {str(path) for path in watched}

    def trace(frame, event, arg):  # type: ignore[no-untyped-def]
        if event == "line":
            name = frame.f_code.co_filename
            if name in names:
                seen.add(f"{name}:{frame.f_lineno}")
        return trace

    argv = ["-o", "addopts=", "-p", "no:cacheprovider", "-p", "no:xdist", "-q", test]
    if collect_only:
        argv.append("--collect-only")
    was = sys.gettrace()
    sys.settrace(trace)
    try:
        pytest.main(argv)
    finally:
        sys.settrace(was)
    return seen


def lines_run(
    repo: Path, test: str, *, collect_only: bool = False
) -> set[tuple[str, int]]:
    """Every watched line that running `test` reaches, in a fresh process."""
    done = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--trace",
            test,
            *(["--collect-only"] if collect_only else []),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    found: set[tuple[str, int]] = set()
    for line in done.stdout.splitlines():
        if not line.startswith("LINE "):
            continue
        name, _, number = line[5:].rpartition(":")
        found.add((str(Path(name).relative_to(repo)), int(number)))
    return found


def lines_of_the_run(repo: Path, test: str) -> set[tuple[str, int]]:
    """The lines the test's own running reaches, import time taken out.

    Importing a test module runs the top level of everything it imports --
    thousands of lines that say nothing about what the test exercises, and
    that differ between two tests only because they import different
    modules. Collecting without running, in its own process, gives exactly
    those lines; what is left is the test's own work.
    """
    whole = lines_run(repo, test)
    importing = lines_run(repo, test, collect_only=True)
    return whole - importing


def asserts_of(path: Path) -> set[str]:
    """Each assertion the file makes, written one way."""
    return asserts_in(path.read_text(encoding="utf-8"), str(path))


def asserts_in(text: str, name: str) -> set[str]:
    """Each assertion the text makes, written one way.

    Normalised through the syntax tree so that whitespace, a renamed local
    and a different quote do not make two readings of one question.
    """
    found: set[str] = set()
    tree = ast.parse(text, filename=name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            found.add(ast.unparse(node.test))
        elif isinstance(node, ast.Call):
            named = node.func
            name = (
                named.attr
                if isinstance(named, ast.Attribute)
                else getattr(named, "id", "")
            )
            if name in ("raises", "warns", "fail", "xfail", "skip"):
                found.add(ast.unparse(node))
    return found


def verdict_line(said: str) -> str:
    """pytest's own summary line, which is the one that says what happened."""
    for line in reversed(said.strip().splitlines()):
        if re.search(r"\d+ (passed|failed|xfailed|xpassed|skipped|error)", line):
            return line.strip()[:90]
    return "nothing it summarised"


def outcome(repo: Path, test: str) -> tuple[int, str]:
    """What pytest says about the test, run on its own."""
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:xdist",
            "-q",
            "-rA",
            test,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return done.returncode, done.stdout + done.stderr


def where_it_would_be(repo: Path, dotted: str) -> list[Path]:
    """The files a dotted name would live in, if it existed.

    A substring search is no good here: looking for `propose` finds
    `propose.py`, `capacity.py` and anything else that happens to say the
    word, and would call a claim false that is true. The name is resolved
    the way an import resolves it -- a module of that path, or the module
    above it declaring it at the top level.
    """
    parts = dotted.split(".")
    found: list[Path] = []
    for where in WATCHED:
        root = repo / where
        if not root.is_dir():
            continue
        module = root.joinpath(*parts)
        for candidate in (module.with_suffix(".py"), module / "__init__.py"):
            if candidate.exists():
                found.append(candidate)
        above = root.joinpath(*parts[:-1])
        for candidate in (above.with_suffix(".py"), above / "__init__.py"):
            if not candidate.exists():
                continue
            tree = ast.parse(candidate.read_text(encoding="utf-8"))
            if parts[-1] in {name for node in tree.body for name in bound_at_top(node)}:
                found.append(candidate)
    return found


def bound_at_top(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def prove_dead(repo: Path, claim: dict[str, str]) -> tuple[str, str]:
    _, said = outcome(repo, claim["path"])
    names = claim["keeper"]  # for a dead claim: the absent thing it names
    present = where_it_would_be(repo, names)
    last = verdict_line(said)
    passed = " passed" in said and "xfailed" not in said
    if present:
        return (
            "unproved",
            f"{names} resolves to {[str(f.relative_to(repo)) for f in present]}, "
            f"so it is not absent; pytest said {last}",
        )
    if passed:
        return (
            "unproved",
            f"{names} is in no source file, but the test passes, so it "
            f"asserts something that holds: {last}",
        )
    return (
        "proved",
        f"{names} resolves to no module or declaration under "
        f"{', '.join(WATCHED)}; pytest said {last}",
    )


def deleted_in(repo: Path, path: str) -> str | None:
    """The commit that removed `path`, if one did."""
    done = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--diff-filter=D", "--", path],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() or None


def as_it_was(repo: Path, path: str, commit: str) -> str:
    """The file's text as the commit that deleted it found it."""
    done = subprocess.run(
        ["git", "show", f"{commit}^:{path}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def prove_gone(repo: Path, claim: dict[str, str]) -> tuple[str, str]:
    """The assertion half, for a test already deleted."""
    path = claim["path"]
    if (repo / path).exists():
        return "unproved", f"{path} is still here; the claim is not about a delete"
    commit = deleted_in(repo, path)
    if commit is None:
        return "unproved", f"no commit in this history removed {path}"
    text = as_it_was(repo, path, commit)
    mine = asserts_in(text, path)
    keeper = repo / claim["keeper"]
    if not keeper.exists():
        return "unproved", f"the keeper {claim['keeper']} is not here either"
    theirs = asserts_in(keeper.read_text(encoding="utf-8"), str(keeper))
    unasked = mine - theirs
    if unasked:
        return (
            "unproved",
            f"recovered from {commit[:9]}^: {len(unasked)} of {len(mine)} "
            f"assertions are the deleted test's alone, e.g. {sorted(unasked)[:2]}",
        )
    return (
        "proved-in-part",
        f"recovered from {commit[:9]}^: all {len(mine)} assertions are also "
        "asked by the keeper. The line half cannot be taken without putting "
        "the test back, so this is the assertion half alone",
    )


def prove_redundant(repo: Path, claim: dict[str, str]) -> tuple[str, str]:
    candidate = lines_of_the_run(repo, claim["path"])
    keeper = lines_of_the_run(repo, claim["keeper"])
    only = candidate - keeper
    mine = asserts_of(repo / claim["path"])
    theirs = asserts_of(repo / claim["keeper"])
    unasked = mine - theirs
    if not candidate:
        return (
            "unproved",
            "0 lines of the product ran in this process. A test that drives "
            "the product's own command line -- directly or through a helper "
            "-- runs it in another interpreter, which this trace cannot "
            "follow, so the line half of the claim cannot be answered this "
            "way at all.",
        )
    if only:
        shown = sorted(f"{f}:{n}" for f, n in only)[:3]
        return (
            "unproved",
            f"{len(only)} of {len(candidate)} lines are run by the candidate "
            f"and not the keeper, e.g. {shown}",
        )
    if unasked:
        return (
            "unproved",
            f"{len(unasked)} assertions are the candidate's alone, e.g. "
            f"{sorted(unasked)[:2]}",
        )
    return (
        "proved",
        f"{len(candidate)} lines run, every one also run by the keeper; "
        f"{len(mine)} assertions, every one also asked by the keeper",
    )


def read_ledger(path: Path) -> list[dict[str, str]]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    head = tuple(lines[0].split("\t"))
    assert head == COLUMNS, f"{path} columns are {head}, expected {COLUMNS}"
    return [dict(zip(COLUMNS, line.split("\t"), strict=True)) for line in lines[1:]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="record the verdicts")
    parser.add_argument("--trace", metavar="TEST", help=argparse.SUPPRESS)
    parser.add_argument("--collect-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    repo = root()
    if args.trace is not None:  # the fresh process lines_run starts
        for line in sorted(
            trace_one(args.trace, sources(repo), collect_only=args.collect_only)
        ):
            print(f"LINE {line}")
        return 0
    claims = read_ledger(repo / LEDGER)
    out: list[dict[str, str]] = []
    worst = 0
    for claim in claims:
        if claim["kind"] == "dead":
            verdict, evidence = prove_dead(repo, claim)
        elif claim["kind"] == "gone-redundant":
            verdict, evidence = prove_gone(repo, claim)
        elif claim["kind"] == "redundant":
            verdict, evidence = prove_redundant(repo, claim)
        else:
            verdict, evidence = "unproved", f"no proof defined for {claim['kind']}"
        print(f"{verdict:9s} {claim['path']}\n          {evidence}")
        worst = max(worst, not verdict.startswith("proved"))
        out.append({**claim, "verdict": verdict, "evidence": evidence})
    if args.write:
        head = (repo / LEDGER).read_text(encoding="utf-8").split("\t".join(COLUMNS))[0]
        (repo / LEDGER).write_text(
            head
            + "\t".join(COLUMNS)
            + "\n"
            + "".join("\t".join(c[k] for k in COLUMNS) + "\n" for c in out),
            encoding="utf-8",
        )
        print(f"wrote {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
