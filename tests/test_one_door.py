"""One door, ``python -m mcgyvr.serving.run`` — and the tree is scanned to prove it.

Four live entry points reached srv1/srv2 on 2026-09-02 and only one of them
stamped rig state, workload digest and build identity. The three root drivers
printed byte-compatible TSV rows with no stamps at all; ``tools/bench/serving/
sweep.py`` hardwired the 11-token prompt the repo had already ruled 2.4x
misleading; the parser ran only in CI, post-hoc, over one hard-coded
directory. A design that says "one door" and never looks is the K9 defect
again: true of an afternoon, not of the instrument.

The door is ``src/mcgyvr/serving/run.py``. It reaches no rig itself: it runs
the gate scripts in order, on a PATH whose ``ssh`` and ``docker`` are the
shims under ``gate-scripts/bin``, and the one rule — a rig is reached under
the door, and only to the host the door was opened for — lives in
``gatelib.ssh`` and in the shims, which call it. So the complete set of
places a rig is touched from is small, and it is declared HERE, each with a
reason, so a new way to reach a rig has to be argued in a diff rather than
slipped in as a file.

The tripwires, each a scan over the tree:

1. An ssh (or scp/rsync/sftp, a paramiko/fabric/asyncssh import, ``/usr/bin/
   ssh``, ``command -p ssh``) or a ``docker run`` appears in a code line only
   behind the door.
2. Nothing under ``tools/`` or ``src/`` names its own daemon: no
   ``DOCKER_HOST``, no ``docker -H``/``--host``/``--context``, no ``-H ssh://``
   outside the shim, and no ``env -u``/``env -i`` that would strip the
   door's vocabulary.
3. No driver or campaign step measures ``localhost``: the container runs on
   the rig, and a client that polls this machine's loopback measures nothing.
4. The archived door's seam variables are gone from src, tools and tests.
5. The serving harness run bare — outside the door — exits 2 naming the door.
6. The workload (``PROMPT_DECILES``) is defined once, in
   ``tools/runs/workload.py``.
7. Every started artifact under ``records/evidence`` parses with
   ``tools.runs.rows.read``, and one that names a ``run_id`` also names its
   round.
8. Every host that wrote a row has a declared ``rig`` block in
   ``tools/runs/hosts.json``.
9. The retired entry points are gone.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import types
from fnmatch import fnmatch
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"
HOSTS = REPO / "tools" / "runs" / "hosts.json"
WORKLOAD = "tools/runs/workload.py"
DOOR = "python -m mcgyvr.serving.run"
SERVING_RUN = REPO / "tools" / "bench" / "serving" / "run.py"

#: Directories never scanned. ``records/`` and ``archive/`` are history and hold
#: the drivers as they ran; the rest is not this repository's code.
NOT_SCANNED = {"records", "archive", ".git", ".venv", "node_modules", "__pycache__"}

#: An ssh SPAWN, not a mention. The shell form wants an argument shaped like
#: one ssh takes — an option, a variable, ``user@host``, one of the rigs — so
#: prose such as "an ssh timeout" in a string is not a hit; scp, rsync and
#: sftp take a path first and are matched on any argument. The list form
#: (``["ssh", ...]``, ``["/usr/bin/ssh", ...]``) is what a subprocess argv
#: looks like: added 2026-09-05 because the shell pattern alone could not see
#: one, so a Python file could open an ssh to a rig and never appear here.
SSH_SPAWN = re.compile(
    r"(?<![\w./-])(?:/usr/bin/)?ssh\s+(?:-[A-Za-z]|[\"']?\$|\{|[\w.-]+@|srv\d\b)"
    r"|(?<![\w./-])(?:scp|rsync|sftp)\s+(?=[\w$\"'{@./-])"
    r"|(?<![\w./-])/usr/bin/ssh\b"
    r"|(?<![\w./-])command\s+-p\s+ssh\b"
    r"|[\"'](?:/usr/bin/)?(?:ssh|scp|rsync|sftp)[\"']\s*,"
    r"|^\s*(?:import|from)\s+(?:paramiko|fabric|asyncssh)\b"
)
#: A container start: ``docker run ...`` in shell form, or the list form.
DOCKER_RUN = re.compile(
    r"(?<![\w./-])docker\s+run\s+(?=[\w$\"'{@.-])"
    r"|[\"']docker[\"']\s*,\s*[\"'](?:run|create|start)[\"']"
)
#: Naming a daemon of one's own, or stripping the door's environment.
DAEMON_OVERRIDE = re.compile(
    r"\bDOCKER_HOST\b"
    r"|\bdocker\s+(?:-H|--host|--context)\b"
    r"|-H[= ]+ssh://"
    r"|\benv\s+-[ui]\b"
)
LOOPBACK = re.compile(r"\blocalhost\b|\b127\.0\.0\.1\b")
RETIRED_SEAMS = re.compile(r"\bRUN_DOCKER\b|\bRUN_SSH\b|\bRUN_RIG_SNAPSHOT_CMD\b")

#: The door and what stands behind it. Path glob -> why it may reach a rig.
#: ``fnmatch`` semantics: ``*`` crosses ``/``. ``run.py`` itself is NOT here
#: and must not be: it reaches no rig, it only runs the gate scripts in
#: order, which is what makes this list the complete set of places a rig is
#: touched from. Nor is ``tools/bench/serving/*`` allowed an ssh of its own:
#: the harness reaches a rig through ``contract.ssh``, which is
#: ``gatelib.ssh`` — see ``test_the_serving_harness_spawns_no_ssh_of_its_own``.
ALLOWED: dict[str, str] = {
    "src/mcgyvr/serving/gatelib.py": (
        "the ONLY ssh spawn in src/ and tools/: gatelib.ssh refuses outside the "
        "door and to any host but the door's; gate 2, gate 7, the geometry read, "
        "`mcgyvr scan` and the serving harness (contract.ssh) all go through it"
    ),
    "src/mcgyvr/serving/gate-scripts/bin/ssh": (
        "the `ssh` on the PATH the door exports: admits the door's host through "
        "gatelib, then execs the next ssh on PATH with BatchMode and a connect "
        "timeout"
    ),
    "src/mcgyvr/serving/gate-scripts/bin/docker": (
        "the `docker` on the PATH the door exports: admits the door through "
        "gatelib, then execs the next docker on PATH at -H ssh://RUN_HOST"
    ),
    "src/mcgyvr/serving/gate-scripts/rig-snapshot.sh": (
        "the reader itself: it RUNS ON the rig, piped in on stdin by gate 2, "
        "and opens nothing of its own"
    ),
    "src/mcgyvr/serving/gate-scripts/default-step.sh": (
        "the shipped step: its plain `ssh` and `docker` are the shims under the "
        "door, which is the only way it is started"
    ),
    "tools/runs/_common.sh": (
        "the emitter every campaign step sources: rig_snapshot over the `ssh` "
        "on PATH, image_digest over the `docker` on PATH — the shims under the "
        "door, and it refuses without the RUN_* only the door exports"
    ),
    "tools/runs/drivers/*.py": (
        "the sweep drivers; their plain `ssh`/`docker` are the shims under the "
        "door, and they refuse without RUN_ID and RUN_HOST, which only the door "
        "exports"
    ),
    "tools/runs/campaigns/**/*.sh": (
        "campaign steps; their plain `ssh`/`docker` are the shims under the "
        "door, and they refuse without RUN_ID, which only the door exports"
    ),
    "tools/bench/serving/backends/*.py": (
        "a `docker run` command LINE the serving backends ship to the rig over "
        "contract.ssh -> gatelib.ssh; nothing here spawns a process of its own"
    ),
    "tools/bench/serving/knobs.py": (
        "a `docker run --help` command line shipped the same way, for the knob "
        "census; spawns nothing locally"
    ),
    "src/mcgyvr/sandbox/docker.py": (
        "the local sandbox — a container on this machine, not a rig"
    ),
    "tests/onedoor.py": (
        "the door tests' stubs: the `ssh` and `docker` a fixture stands behind "
        "the shims; the argv the list-form pattern sees is the stub's own name"
    ),
    "tests/test_one_door.py": "this file names the patterns it scans for",
    "tests/test_cross_rig_claim.py": (
        "monkeypatches contract.ssh with a stub; reaches no rig"
    ),
    "tests/test_breadth_rig.py": (
        "monkeypatches gatelib.ssh with a stub that raises; reaches no rig"
    ),
    "tests/test_card_samples.py": "stubs contract.ssh, and the ssh binary being gone",
    "tests/test_serving.py": "stubs a dead ssh and asserts its message is kept",
    "tests/test_serving_memory_declaration.py": (
        "asserts the shape of a launch line against a stub"
    ),
    "tests/test_sink_conformance.py": "counts ssh calls into a stub",
    "tests/test_serving_gatelib.py": (
        "drives gatelib.ssh under a fake door against an ssh stub"
    ),
    "tests/test_serving_door_cli.py": (
        "drives the shims under a fake door against ssh and docker stubs"
    ),
    "tests/test_default_step.py": (
        "drives the shipped step against ssh and docker stubs on PATH"
    ),
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


def _is_source(path: Path) -> bool:
    """``*.py``, ``*.sh``, and a suffix-less executable (the shims)."""
    if path.suffix in (".py", ".sh"):
        return True
    return not path.suffix and path.is_file() and bool(path.stat().st_mode & 0o111)


def _sources(roots: tuple[str, ...], root_files: bool) -> list[Path]:
    """Every source file under ``roots`` (recursive), plus the repo root."""
    found: list[Path] = []
    for top in roots:
        for path in (REPO / top).rglob("*"):
            if not _is_source(path):
                continue
            if NOT_SCANNED & set(path.relative_to(REPO).parts):
                continue
            found.append(path)
    if root_files:
        found += [p for p in REPO.iterdir() if p.suffix in (".py", ".sh")]
    return sorted(found)


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _allowed(rel: str) -> bool:
    return any(fnmatch(rel, pattern) for pattern in ALLOWED)


def _hits(
    pattern: re.Pattern[str], roots: tuple[str, ...], *, root_files: bool = False
) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for path in _sources(roots, root_files=root_files):
        lines = [
            line[:100]
            for line in _code_lines(path.read_text(encoding="utf-8", errors="replace"))
            if pattern.search(line)
        ]
        if lines:
            hits[_rel(path)] = lines
    return hits


def _rows() -> types.ModuleType:
    """``tools/runs/rows.py`` — the parser, at the home the door reads it from."""
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
# 1. an ssh or a docker run appears only behind the door
# --------------------------------------------------------------------------


def test_an_ssh_or_a_docker_run_appears_only_behind_the_door() -> None:
    hits = _hits(SSH_SPAWN, ("src", "tools", "tests"), root_files=True)
    for rel, lines in _hits(
        DOCKER_RUN, ("src", "tools", "tests"), root_files=True
    ).items():
        hits.setdefault(rel, []).extend(lines)
    assert hits, "the scan found no invocation at all — the pattern is broken"
    strays = {rel: lines for rel, lines in hits.items() if not _allowed(rel)}
    assert not strays, (
        f"{len(strays)} file(s) reach a rig outside {DOOR} — each is "
        "(path, invocations) and a new one is argued into ALLOWED with a reason "
        f"or removed: {strays}"
    )


def test_every_allowed_entry_names_a_file_that_exists() -> None:
    """A stale allowance is a hole waiting for a file of that name."""
    present = [_rel(p) for p in _sources(("src", "tools", "tests"), root_files=False)]
    stale = [
        pattern
        for pattern in ALLOWED
        if not any(fnmatch(rel, pattern) for rel in present)
    ]
    assert not stale, f"ALLOWED names files that do not exist: {stale}"


def test_the_serving_harness_spawns_no_ssh_of_its_own() -> None:
    """``tools/bench/serving/*`` reaches a rig only through ``contract.ssh``,
    which is ``gatelib.ssh``; the `docker run` lines it carries are command
    text shipped over that ssh. No ssh spawn of its own, in any form."""
    hits = _hits(SSH_SPAWN, ("tools/bench/serving",))
    assert not hits, f"the serving harness spawns an ssh outside gatelib: {hits}"


# --------------------------------------------------------------------------
# 2. nothing names its own daemon; 3. nothing measures loopback; 4. no seams
# --------------------------------------------------------------------------


def test_nothing_under_tools_or_src_names_its_own_daemon() -> None:
    hits = _hits(DAEMON_OVERRIDE, ("src", "tools"))
    # The shim's own implementation is where -H ssh://RUN_HOST is set and
    # --context is refused; everything else takes the daemon the door names.
    hits.pop("src/mcgyvr/serving/gatelib.py", None)
    assert not hits, (
        "a daemon of its own, or the door's environment stripped — under the "
        f"door `docker` reaches ssh://RUN_HOST and nothing else: {hits}"
    )


def test_no_driver_or_campaign_step_measures_loopback() -> None:
    hits = _hits(LOOPBACK, ("tools/runs/drivers", "tools/runs/campaigns"))
    assert not hits, (
        "the container runs on the rig (the door's `docker` lands there), so a "
        f"client polling this machine's loopback measures nothing: {hits}"
    )


#: Files that must spell the retired names: the guard, this file, and the
#: door's CLI test, which asserts the seam is gone from the door's vocabulary.
SPELLS_THE_SEAMS = (
    "tests/test_no_retired_door_names.py",
    "tests/test_one_door.py",
    "tests/test_serving_door_cli.py",
)


def test_the_archived_doors_seam_variables_are_gone() -> None:
    hits = {
        rel: lines
        for rel, lines in _hits(RETIRED_SEAMS, ("src", "tools", "tests")).items()
        if rel not in SPELLS_THE_SEAMS
    }
    assert not hits, (
        "a variable that replaces a reading is a variable that skips one; the "
        f"door has no seam and neither does anything under it: {hits}"
    )


# --------------------------------------------------------------------------
# 5. the serving harness run bare exits 2 naming the door
# --------------------------------------------------------------------------


def test_the_serving_harness_run_bare_exits_2_naming_the_door(tmp_path: Path) -> None:
    """``tests/test_serving_gatelib.py`` pins ``gatelib.ssh``'s refusal and
    ``tests/test_serving_door_cli.py`` the shims' and the gates'; this is the
    harness as an operator would run it by hand, from the outside."""
    config = tmp_path / "min.json"
    config.write_text(
        json.dumps({"hosts": ["h"], "backends": [], "models": []}), encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUN_", "DOCKER_"))}
    done = subprocess.run(
        [
            sys.executable,
            str(SERVING_RUN),
            "--config",
            str(config),
            "--out",
            str(tmp_path / "survey.jsonl"),
        ],
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 2, (done.returncode, done.stdout[-400:], done.stderr)
    assert DOOR in done.stderr, done.stderr[-600:]
    assert "not started by the door" in done.stderr, done.stderr[-600:]


# --------------------------------------------------------------------------
# 6. one workload
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
# 7. every started artifact parses; a run_id brings its round
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
# 8. every host that wrote a row is declared
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
# 9. the retired entry points are gone
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
        "tools/runs/run.sh",
        "tools/runs/campaigns/srv1-kernel-arms/PLAN.md",
        # The readers moved into the product with the door (round r3).
        "tools/bench/serving/ggufscan.py",
        "tools/bench/serving/vramfit.py",
    ],
)
def test_the_retired_entry_point_is_gone(pattern: str) -> None:
    present = sorted(_rel(p) for p in REPO.glob(pattern))
    assert not present, f"{present} still exist(s); {DOOR} is the only door"
