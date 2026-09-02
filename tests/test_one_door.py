"""run.sh is the only door to the rigs — and the tree is scanned to prove it.

Four live entry points reached srv1/srv2 on 2026-09-02 and only one of them
(``tools/runs/srv1-*.sh`` over ``_common.sh``) stamped rig state, workload
digest and build identity. The three root drivers printed byte-compatible TSV
rows with no stamps at all; ``tools/bench/serving/sweep.py`` hardwired the
11-token prompt the repo had already ruled 2.4x misleading; the parser ran only
in CI, post-hoc, over one hard-coded directory (BRIEF.md, "The problem being
solved"). A design that says "one door" and never looks is the K9 defect again:
true of an afternoon, not of the instrument.

So five tripwires, each a scan over the tree. Every exception is an entry in an
allowlist declared HERE with a reason, so a new way to reach a rig has to be
argued in a diff rather than slipped in as a file.

1. ``docker run`` / ``ssh <word>`` appear only behind the door.
2. The workload (``PROMPT_DECILES``) is defined once, in ``tools/runs/workload.py``.
3. Every started artifact under ``records/evidence`` parses with
   ``tools.runs.rows.read``, and one that names a ``run_id`` also names its round.
4. Every host that wrote a row has a declared ``rig`` block in
   ``tools/runs/hosts.json``.
5. The retired entry points are gone: nothing under ``records/`` is executable,
   no ``*.py`` sits at the repo root, ``run-with-bench-prompts/`` and
   ``serving/sweep.py`` are deleted, the plan moved in with its campaign.
"""

from __future__ import annotations

import importlib
import json
import re
import types
from fnmatch import fnmatch
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"
HOSTS = REPO / "tools" / "runs" / "hosts.json"
WORKLOAD = "tools/runs/workload.py"

#: Directories never scanned. ``records/`` and ``archive/`` are history and hold
#: the drivers as they ran; the rest is not this repository's code.
NOT_SCANNED = {"records", "archive", ".git", ".venv", "node_modules", "__pycache__"}

#: An invocation, not a mention: ``docker run`` or ``ssh`` followed by an
#: argument, in a code line. Comments and docstrings are dropped first
#: (``launch.code_lines``' argument: a record saying what a thing used to do
#: is the opposite of the defect looked for).
INVOCATION = re.compile(r"(?<![\w./-])(docker\s+run|ssh)\s+(?=[\w$\"'{@.-])")

#: The door and what stands behind it. Path glob -> why it may reach a rig.
#: ``fnmatch`` semantics: ``*`` crosses ``/``. The three root drivers and
#: ``tools/bench/serving/sweep.py`` are NOT here, on purpose — they are the
#: entry points this file exists to retire.
ALLOWED: dict[str, str] = {
    "tools/runs/run.sh": (
        "the door — the one executable that opens an ssh or starts a container"
    ),
    "tools/runs/_common.sh": (
        "the emitter run.sh sources: rig_snapshot over ssh, image_digest over docker"
    ),
    "tools/runs/drivers/*.py": (
        "the sweep drivers; they refuse without RUN_ID, so only run.sh reaches them"
    ),
    "tools/runs/campaigns/**/*.sh": (
        "campaign steps; they refuse without RUN_ID, so only run.sh reaches them"
    ),
    "tools/bench/serving/backends/*.py": (
        "the serving backends run.sh calls: docker run on the rig"
    ),
    "tools/bench/serving/run.py": "serving survey library, called by run.sh",
    "tools/bench/serving/calibrate.py": "serving calibration library, called by run.sh",
    "tools/bench/serving/knobs.py": "serving knob census, called by run.sh",
    "tools/bench/serving/pin.py": "serving pin, called by run.sh",
    "tools/bench/serving/contract.py": (
        "the serving contract; names ssh in a provenance note, opens none"
    ),
    "src/mcgyvr/sandbox/docker.py": (
        "the local sandbox — a container on this machine, not a rig"
    ),
    "src/mcgyvr/scan.py": (
        "product feature: `mcgyvr scan` over ssh is what the user asked for"
    ),
    "tests/test_card_samples.py": "stubs the ssh binary being gone",
    "tests/test_serving.py": "stubs a dead ssh and asserts its message is kept",
    "tests/test_serving_memory_declaration.py": (
        "asserts the shape of a launch line against a stub"
    ),
    "tests/test_sink_conformance.py": "counts ssh calls into a stub",
    "tests/onedoor.py": "the door tests' seam stubs; the ssh stand-in names itself",
    "tests/test_one_door.py": "this file names the patterns it scans for",
}

DECILES = re.compile(r"^\s*PROMPT_DECILES\s*=")


def _code_lines(text: str) -> list[str]:
    """Line-oriented, deliberately crude: drop comment and docstring lines."""
    out: list[str] = []
    in_doc = False
    for raw in text.splitlines():
        line = raw.strip()
        fences = line.count('"""') + line.count("'''")
        if in_doc:
            if fences:
                in_doc = False
            continue
        if line.startswith("#"):
            continue
        if fences == 1:
            in_doc = True
            continue
        out.append(line)
    return out


def _sources(roots: tuple[str, ...], root_files: bool) -> list[Path]:
    """Every ``*.py`` / ``*.sh`` under ``roots`` (recursive), plus the repo root."""
    found: list[Path] = []
    for top in roots:
        for path in (REPO / top).rglob("*"):
            if path.suffix in (".py", ".sh") and not (
                NOT_SCANNED & set(path.relative_to(REPO).parts)
            ):
                found.append(path)
    if root_files:
        found += [p for p in REPO.iterdir() if p.suffix in (".py", ".sh")]
    return sorted(found)


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _allowed(rel: str) -> bool:
    return any(fnmatch(rel, pattern) for pattern in ALLOWED)


def _rows() -> types.ModuleType:
    """``tools/runs/rows.py`` — the parser, at the home the door reads it from.

    Imported by name at call time rather than at the top of the file, so this
    module type-checks while the parser is still ``tests/sweeprows.py``; the
    ImportError is then the test's failure, not the suite's.
    """
    return importlib.import_module("tools.runs.rows")


def _started() -> list[Path]:
    """Every artifact that carries a ``### START`` line."""
    return [
        path
        for path in sorted(EVIDENCE.rglob("*.tsv"))
        if any(
            line.startswith("### START")
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]


# --------------------------------------------------------------------------
# 1. docker run / ssh appear only behind the door
# --------------------------------------------------------------------------


def test_docker_run_and_ssh_appear_only_behind_the_door() -> None:
    hits: dict[str, list[str]] = {}
    for path in _sources(("src", "tools", "tests"), root_files=True):
        lines = [
            line[:100]
            for line in _code_lines(path.read_text(encoding="utf-8"))
            if INVOCATION.search(line)
        ]
        if lines:
            hits[_rel(path)] = lines
    assert hits, "the scan found no invocation at all — the pattern is broken"
    strays = {rel: lines for rel, lines in hits.items() if not _allowed(rel)}
    assert not strays, (
        f"{len(strays)} file(s) reach a rig outside tools/runs/run.sh — each is "
        "(path, invocations) and a new one is argued into ALLOWED with a reason "
        f"or removed: {strays}"
    )


# --------------------------------------------------------------------------
# 2. one workload
# --------------------------------------------------------------------------


def test_the_workload_is_defined_once_in_workload_py() -> None:
    definitions = sorted(
        _rel(path)
        for path in _sources(("src", "tools", "tests", "okf", "data"), root_files=True)
        if any(DECILES.search(line) for line in _code_lines(path.read_text("utf-8")))
    )
    assert definitions == [WORKLOAD], (
        f"PROMPT_DECILES is defined in {definitions}; the one definition is "
        f"{WORKLOAD}, which every driver imports. A second copy is a second "
        "workload that will drift — the 2f2bb793 digest is over generated prompts "
        "precisely so no copy can be equal by accident."
    )


# --------------------------------------------------------------------------
# 3. every started artifact parses; a run_id brings its round
# --------------------------------------------------------------------------


def test_every_started_artifact_parses_and_a_run_id_names_its_round() -> None:
    rows = _rows()
    started = _started()
    assert started, f"no artifact under {EVIDENCE} carries a ### START line"
    problems: list[str] = []
    for path in started:
        rel = _rel(path)
        try:
            sweep = rows.read(path)
        except ValueError as error:
            problems.append(f"{rel}: does not parse — {error}")
            continue
        starts = [
            line
            for _, line in sweep.markers
            if line.removeprefix("###").split()[:1] == ["START"]
        ]
        if not any("run_id=" in line for line in starts):
            continue  # pre-door artifact: no run_id, no round is owed
        try:
            start, round_ = sweep.stamp("START"), sweep.stamp("ROUND")
        except ValueError as error:
            problems.append(f"{rel}: a stamp does not parse — {error}")
            continue
        if not start.get("run_id"):
            problems.append(f"{rel}: START names run_id= but it is empty")
        if not (round_.get("id") and round_.get("product_sha256")):
            problems.append(
                f"{rel}: START carries run_id={start.get('run_id')!r} but no "
                "`### ROUND id= product_sha256=` — a run the door started stamps "
                "the product round it measured (gate 1)"
            )
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------
# 4. every host that wrote a row is declared
# --------------------------------------------------------------------------


def test_every_host_that_wrote_a_row_has_a_declared_rig() -> None:
    rows = _rows()
    hosts = sorted({row.host for path in _started() for row in rows.read(path).rows})
    assert hosts, "no artifact carries a row, so no host is on record"
    declared = json.loads(HOSTS.read_text(encoding="utf-8"))
    gaps: list[str] = []
    for host in hosts:
        rig = (declared.get(host) or {}).get("rig")
        if not isinstance(rig, dict):
            gaps.append(
                f"{host}: no `rig` block under {HOSTS.relative_to(REPO)}[{host!r}]"
            )
            continue
        missing = [f for f in rows.RIG_FIELDS if not str(rig.get(f, "")).strip()]
        if missing:
            gaps.append(f"{host}: rig block lacks {missing}")
        if not str(declared[host].get("read_on", "")).strip():
            gaps.append(f"{host}: no read_on beside the rig block — read when?")
    assert not gaps, (
        "gate 2 compares the live rig with its declaration, so every host that "
        f"ever wrote a row must be declared: {gaps}"
    )


# --------------------------------------------------------------------------
# 5. the retired entry points are gone
# --------------------------------------------------------------------------


def test_nothing_under_records_is_executable() -> None:
    executable = sorted(
        _rel(path)
        for path in (REPO / "records").rglob("*")
        if path.is_file() and path.stat().st_mode & 0o111
    )
    assert not executable, (
        f"{len(executable)} file(s) under records/ carry the exec bit — a record "
        f"is evidence, not an entry point: {executable}"
    )


def test_no_python_sits_at_the_repo_root() -> None:
    loose = sorted(p.name for p in REPO.glob("*.py"))
    assert not loose, (
        f"{loose} at the repo root: a driver that can be run bare prints "
        "unstamped rows. Drivers live in tools/runs/drivers/ and refuse without RUN_ID."
    )


@pytest.mark.parametrize(
    "pattern",
    [
        "run-with-bench-prompts",
        "tools/bench/serving/sweep.py",
        "lcp-vllm-3-arm-run.md",
        "tools/runs/srv1-*.sh",
    ],
)
def test_the_retired_entry_point_is_gone(pattern: str) -> None:
    present = sorted(_rel(p) for p in REPO.glob(pattern))
    assert not present, f"{present} still exist(s); run.sh is the only door"


def test_the_plan_moved_in_with_its_campaign() -> None:
    plan = REPO / "tools" / "runs" / "campaigns" / "srv1-kernel-arms" / "PLAN.md"
    assert plan.is_file(), f"{plan.relative_to(REPO)} does not exist"
    first = plan.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("# lcp/vllm arm run — srv1 kernel attribution"), (
        f"PLAN.md opens {first!r}; a move keeps the plan's own heading"
    )
