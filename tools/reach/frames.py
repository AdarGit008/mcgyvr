#!/usr/bin/env python3
"""Shared machinery for #129's three counts over the pinned reach corpus.

``enumerate.py`` fixed the denominator; this fixes how the numerators are
produced. Three things are shared and none of them are obvious, so they live
here rather than being written three times:

**Added lines, not added-line counts.** ``corpus.json`` stores how many source
lines each change added, which was all Count 2 and the corpus check needed. The
reach count needs *which* lines, because a line number is only meaningful in the
tree that contains it. :func:`added_lines` recomputes them from the same diff
``enumerate.py`` counted, and every caller asserts the recomputed total equals
the pinned one — that assertion is what makes "re-runs to the same number" a
property of the code rather than a hope.

**A container, always.** ADR-0005 and ADR-0010 put target code inside a
container, and CLM-0006 turned that from a preference into a constraint: the
resolver Count 3 measures imports the target's own modules, and Count 1 runs
the target's test suite, which is arbitrary code by construction. Nothing here
runs a target's code on the host. Host-side work is git metadata only, which is
the same line ``enumerate.py`` draws.

**The declared check is the repository's, not ours.** Each frame's command comes
from ``corpus.json``'s ``declared_check``, so the measurement runs what the
repository declared rather than what a detector guessed about it. That is why
this does not reuse :mod:`mcgyvr.sandbox`: ``detect_stack`` infers an install
command from the manifests it finds, and substituting mcgyvr's inference for the
repository's own declaration is precisely the error ADR-0006 names. The sandbox
is also built around a per-task workspace with a git base commit to diff a
worker's change against, and there is no worker here. What is borrowed is its
discipline — a per-frame container, no host environment inherited, torn down
after — not its code.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO / "records" / "corpora" / "reach-2026-08-02"
CORPUS = CORPUS_DIR / "corpus.json"

CLONE_DEPTH = 120
REMOTES = {
    "pallets/click": "https://github.com/pallets/click.git",
    "immerjs/immer": "https://github.com/immerjs/immer.git",
}

# `@@ -old,count +new,count @@`. With -U0 there is no context, so a hunk's
# new-side range is exactly the lines the change added.
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


class ReachError(RuntimeError):
    """A frame could not be prepared or measured."""


# --- corpus ---------------------------------------------------------------


def load_corpus() -> dict[str, Any]:
    corpus: dict[str, Any] = json.loads(CORPUS.read_text(encoding="utf-8"))
    return corpus


def matches(path: str, glob: str) -> bool:
    """``src/**/*.py`` — the corpus's only glob shape, matched as enumerate does.

    Kept identical to ``enumerate.py`` on purpose: if the two disagreed about
    which paths are source, the numerator and the denominator would be counting
    different populations.
    """
    prefix, _, suffix = glob.partition("**/*")
    return path.startswith(prefix) and path.endswith(suffix)


def parent_of(commit: str, unit: str) -> str:
    """The revision a change is diffed against, per the frame's unit."""
    return f"{commit}^1" if unit.startswith("first-parent") else f"{commit}^"


# --- git (host-side, metadata only) ---------------------------------------


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise ReachError(f"git {' '.join(args)} in {cwd}: {proc.stderr.strip()}")
    return proc.stdout


def added_lines(
    clone: Path, commit: str, unit: str, glob: str
) -> dict[str, frozenset[int]]:
    """Which lines each source file gained in ``commit``, by path.

    Line numbers are 1-based in the *new* side, the same quantity
    ``ChangeSet.detect`` attributes as ``added_lines`` — so what is measured
    here is what the gate would filter on, not a near neighbour of it.
    """
    diff = git(
        clone,
        "diff",
        "-U0",
        "--no-color",
        "--no-renames",
        parent_of(commit, unit),
        commit,
    )
    out: dict[str, set[int]] = {}
    path: str | None = None
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else target[2:]  # strip "b/"
            continue
        if not line.startswith("@@") or path is None or not matches(path, glob):
            continue
        hunk = _HUNK.match(line)
        if hunk is None:
            continue
        count = int(hunk.group("count") or 1)
        if count:
            start = int(hunk.group("start"))
            out.setdefault(path, set()).update(range(start, start + count))
    return {p: frozenset(v) for p, v in out.items() if v}


def prepare_clone(frame: Mapping[str, Any], workdir: Path) -> Path:
    """Materialise a frame at its pinned commit, checkout-able commit by commit.

    The self frame is cloned rather than used in place: the measurement checks
    out 20 historical commits and must not touch the working tree it is run
    from.
    """
    dest = workdir / str(frame["repo"]).replace("/", "_")
    if dest.exists():
        return dest
    dest.mkdir(parents=True)
    sha = str(frame["pinned_commit"])
    if frame["role"] == "self":
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", str(REPO), str(dest)],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(["git", "init", "--quiet", str(dest)], check=True)
        git(dest, "remote", "add", "origin", REMOTES[frame["repo"]])
        print(f"  fetching {frame['repo']} at {sha[:8]} ...", file=sys.stderr)
        git(dest, "fetch", "--quiet", "--depth", str(CLONE_DEPTH), "origin", sha)
    git(dest, "checkout", "--quiet", "--detach", sha)
    return dest


def checkout(clone: Path, commit: str, keep: Sequence[str]) -> None:
    """Move the clone to ``commit``, keeping provisioned directories in place.

    ``keep`` names untracked trees that are expensive to rebuild (``node_modules``,
    ``.venv``) and are not part of any commit, so preserving them across
    checkouts changes nothing that is measured and saves a reinstall per commit.
    """
    git(clone, "checkout", "--quiet", "--detach", commit)
    args = ["clean", "-qfdx"]
    for name in keep:
        args += ["-e", name]
    git(clone, *args)


def changed_paths(clone: Path, commit: str, unit: str) -> frozenset[str]:
    """Every path a commit touched — used to decide when to re-provision."""
    out = git(
        clone,
        "diff",
        "--name-only",
        "--no-renames",
        parent_of(commit, unit),
        commit,
    )
    return frozenset(p for p in out.split("\n") if p)


# --- containers -----------------------------------------------------------


@dataclass(frozen=True)
class FrameRuntime:
    """How one frame is provisioned and how its declared check is instrumented.

    ``dockerfile`` bakes the toolchain in as root so the container itself can
    run as the host user: everything the run writes lands in a bind mount, and
    root-owned build output in a mounted tree is a cleanup problem rather than a
    measurement. ``provision`` installs the repository's dependencies and reruns
    only when a commit touches ``manifests``. ``instrument`` is the declared
    check with a coverage instrument around it; ``report_cmd`` must then leave a
    report at ``/out/coverage.json`` in the format ``report_kind`` names.
    """

    dockerfile: str
    provision: str
    manifests: tuple[str, ...]
    instrument: str
    report_cmd: str
    report_kind: str  # "coverage.py" | "istanbul"
    keep: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict[str, Any])


# A cache and a HOME that are writable by the host user and outside the clone,
# so no toolchain scratch file is ever mistaken for repository content.
_CACHE = "/cache"
_CACHE_ENV = {
    "HOME": _CACHE,
    "XDG_CACHE_HOME": _CACHE,
    "UV_CACHE_DIR": _CACHE + "/uv",
    # Bound the build's own parallelism rather than relying on the PID ceiling
    # to bound it, so a busy host cannot turn a build into a missing row.
    "RAYON_NUM_THREADS": "4",
    "UV_CONCURRENT_BUILDS": "1",
}

_PY_IMAGE = """FROM python:3.12-slim
RUN apt-get update -qq && apt-get install -y -qq git >/dev/null \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -q uv coverage
WORKDIR /work
"""

_NODE_IMAGE = """FROM node:22-slim
RUN apt-get update -qq && apt-get install -y -qq git >/dev/null \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
"""

FRAME_RUNTIME: dict[str, FrameRuntime] = {
    # Coverage is IMPOSED here: mcgyvr declares `uv run pytest` and no
    # coverage configuration, so `--source=src` is this harness's choice and
    # the result has to say so. `--with coverage` puts the instrument in the
    # project environment without editing the project's dependencies.
    "AdarGit008/mcgyvr": FrameRuntime(
        dockerfile=_PY_IMAGE,
        provision="uv sync --frozen -q",
        manifests=("pyproject.toml", "uv.lock"),
        instrument=(
            "uv run --with coverage coverage run --source=src "
            "-m pytest -q -p no:randomly"
        ),
        report_cmd="uv run --with coverage coverage json -q -o /out/coverage.json",
        report_kind="coverage.py",
        keep=(".venv",),
        env=_CACHE_ENV,
    ),
    # Coverage is DECLARED: `[tool.coverage.run]` sets branch and source, and a
    # bare `coverage run` reads it — no `--source` is passed here, unlike the
    # frame above. The environment comes from click's own `uv.lock`, whose
    # `[tool.uv] default-groups` already includes its `tests` group, so the
    # suite runs against the dependency set the repository pinned rather than
    # one this harness resolved.
    "pallets/click": FrameRuntime(
        dockerfile=_PY_IMAGE,
        provision="uv sync --frozen -q",
        manifests=("pyproject.toml", "uv.lock"),
        instrument="uv run --with coverage coverage run -m pytest -q -p no:randomly",
        report_cmd="uv run --with coverage coverage json -q -o /out/coverage.json",
        report_kind="coverage.py",
        keep=(".venv",),
        env=_CACHE_ENV,
    ),
    # Coverage is DECLARED: `scripts.coverage` is `vitest run --coverage`, and
    # @vitest/coverage-v8 is a declared devDependency. Only the reporter and
    # its destination are added, so the run stays the repository's own.
    "immerjs/immer": FrameRuntime(
        dockerfile=_NODE_IMAGE,
        provision="yarn install --frozen-lockfile --silent",
        manifests=("package.json", "yarn.lock"),
        instrument=(
            "npx vitest run --coverage --coverage.reporter=json "
            "--coverage.reportsDirectory=/out/cov"
        ),
        report_cmd="cp /out/cov/coverage-final.json /out/coverage.json",
        report_kind="istanbul",
        keep=("node_modules",),
        env=_CACHE_ENV,
    ),
}


def build_image(runtime: FrameRuntime, tag: str) -> None:
    proc = subprocess.run(
        ["docker", "build", "-q", "-t", tag, "-"],
        input=runtime.dockerfile,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ReachError(f"could not build {tag}: {proc.stderr.strip()}")


class FrameContainer:
    """One long-lived container per frame, driven by ``docker exec``.

    One container for a frame rather than one per commit, for the same reason
    :class:`~mcgyvr.sandbox.docker.DockerSandbox` keeps one per task: the
    dependency install is the expensive part and it is valid for every commit
    that does not touch a manifest. The clone is bind-mounted, so the host
    moves between commits with git and the container only ever runs commands.
    """

    def __init__(self, tag: str, clone: Path, out: Path, cache: Path) -> None:
        self._tag = tag
        self._clone = clone
        self._out = out
        self._cache = cache
        self._name = f"reach-{uuid.uuid4().hex[:10]}"

    def __enter__(self) -> FrameContainer:
        import os

        self._out.mkdir(parents=True, exist_ok=True)
        self._cache.mkdir(parents=True, exist_ok=True)
        args = [
            "docker",
            "run",
            "--detach",
            "--name",
            self._name,
            "--workdir",
            "/work",
            "--volume",
            f"{self._clone}:/work",
            "--volume",
            f"{self._out}:/out",
            "--volume",
            f"{self._cache}:{_CACHE}",
            "--memory",
            "4g",
            # Generous on purpose. A tighter ceiling is not a safety property
            # here — the ceiling that matters is the container boundary — and
            # 1024 was low enough that uv's rayon pool failed to spawn threads
            # (EAGAIN) on exactly the commits where it had to build, losing
            # seven of mcgyvr's twenty changes to a rig defect that looked like
            # a target failure.
            "--pids-limit",
            "8192",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            self._tag,
            "sleep",
            "infinity",
        ]
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ReachError(f"could not start container: {proc.stderr.strip()}")
        return self

    def __exit__(self, *exc: object) -> None:
        subprocess.run(
            ["docker", "rm", "--force", self._name],
            capture_output=True,
            check=False,
        )

    def run(
        self, script: str, env: Mapping[str, str], timeout: float = 1800
    ) -> tuple[int, str]:
        """Run a shell script in the container, returning (exit code, output)."""
        args = ["docker", "exec", "--workdir", "/work"]
        for key, value in sorted(env.items()):
            args += ["--env", f"{key}={value}"]
        args += [self._name, "bash", "-lc", script]
        try:
            done = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return -1, f"timed out after {timeout}s"
        return done.returncode, (done.stdout + done.stderr)[-4000:]


# --- coverage reports -----------------------------------------------------


@dataclass(frozen=True)
class FileCoverage:
    """Which lines an instrument found executable, and which of those it ran.

    The two instruments do not agree on what an executable line is — coverage.py
    reports every statement line, istanbul reports one entry per statement and
    is read here at its start line. That difference is why the counts are
    reported per frame and a pooled figure has to carry the split.
    """

    executed: frozenset[int]
    executable: frozenset[int]


def parse_coverage_py(report: Mapping[str, Any]) -> dict[str, FileCoverage]:
    out = {}
    for path, data in report.get("files", {}).items():
        executed = frozenset(data.get("executed_lines", []))
        missing = frozenset(data.get("missing_lines", []))
        out[_normalise(path)] = FileCoverage(executed, executed | missing)
    return out


def parse_istanbul(report: Mapping[str, Any]) -> dict[str, FileCoverage]:
    out = {}
    for path, data in report.items():
        statements = data.get("statementMap", {})
        counts = data.get("s", {})
        executed: set[int] = set()
        executable: set[int] = set()
        for index, span in statements.items():
            line = span.get("start", {}).get("line")
            if line is None:
                continue
            executable.add(line)
            if counts.get(index, 0):
                executed.add(line)
        out[_normalise(path)] = FileCoverage(frozenset(executed), frozenset(executable))
    return out


def _normalise(path: str) -> str:
    """Report paths as repository-relative, however the instrument spelled them."""
    cleaned = path.replace("\\", "/")
    if cleaned.startswith("/work/"):
        cleaned = cleaned[len("/work/") :]
    return cleaned.lstrip("./")


def load_report(kind: str, path: Path) -> dict[str, FileCoverage]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if kind == "coverage.py":
        return parse_coverage_py(report)
    if kind == "istanbul":
        return parse_istanbul(report)
    raise ReachError(f"unknown report kind {kind!r}")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
