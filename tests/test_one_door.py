"""One door, ``python -m mcgyvr.serving.run`` — and the tree is scanned to prove it.

A design that says "one door" and never looks is true of an afternoon, not of the
instrument. The door is ``src/mcgyvr/serving/run.py``. It reaches no rig itself: it runs
the gate scripts in order, on a PATH whose ``ssh`` and ``docker`` are the shims under
``gate-scripts/bin``, and the one rule — a rig is reached under the door, and only to
the host the door was opened for — lives in ``gatelib.ssh`` and in the shims, which call
it. So the complete set of places a rig is touched from is small, and it is declared
HERE, each with a reason, so a new way to reach a rig has to be argued in a diff rather
than slipped in as a file.

THE ACCEPTED LIMIT, in one sentence: the proof every gate, step and driver
applies is an ancestor's command line plus RUN_HOST, both of which an
operator can forge with ``bash -c ... x/mcgyvr/serving/run.py``, so the seal
is against every code path in this repository and not against an operator
impersonating the door.

The tripwires, each a scan over the tree:

1. An ssh (or scp/rsync/sftp, a paramiko/fabric/asyncssh import, ``/usr/bin/
   ssh``, ``command -p ssh``) or a ``docker run`` appears in a code line only
   behind the door. A SPAWN, not the seam's name: a test that substitutes
   ``servelib.ssh``, and the stdlib result record a stub hands back, are the
   opposite of reaching a rig, and the scan reads those two spellings for
   what they are (``SEAM_MENTION``) instead of taking the bare word — while
   still scanning the whole of the rest of every such line.
2. Nothing under ``tools/`` or ``src/`` names its own daemon: no
   ``DOCKER_HOST``, no ``docker -H``/``--host``/``--context``, no ``-H ssh://``
   outside the shim, and no ``env -u``/``env -i`` that would strip the
   door's vocabulary.
3. The archived door's seam variables are gone from src, tools and tests.
4. A hand-set ``RUN_*`` environment admits nothing: every gate script and the
   default step, given every variable the door would export and no door
   ancestor, exit 2 naming the door before an ``ssh`` or ``docker`` stub sees
   a line.
5. No Python file sits at the repository root.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

import pytest

from mcgyvr.serving.run import EXPORTED

REPO = Path(__file__).resolve().parent.parent
DOOR = "python -m mcgyvr.serving.run"

#: Directories never scanned. ``records/`` and ``archive/`` are history and hold
#: the drivers as they ran; the rest is not this repository's code.
NOT_SCANNED = {"records", "archive", ".git", ".venv", "node_modules", "__pycache__"}

#: An ssh SPAWN, not a mention. The shell form wants an argument shaped like
#: one ssh takes — an option, a variable, ``user@host``, one of the rigs — so
#: prose such as "an ssh timeout" in a string is not a hit; scp, rsync and
#: sftp take a path first and are matched on any argument. The list form
#: (``["ssh", ...]``, ``["/usr/bin/ssh", ...]``) is what a subprocess argv
#: looks like: the shell pattern alone cannot see one, so without it a Python
#: file could open an ssh to a rig and never appear here.
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
RETIRED_SEAMS = re.compile(r"\bRUN_DOCKER\b|\bRUN_SSH\b|\bRUN_RIG_SNAPSHOT_CMD\b")

#: Two spellings in which the seam's NAME provably starts no process, erased from a line
#: before the spawn patterns read it. The list form above sees ``"ssh",`` and cannot
#: tell ``subprocess.run(["ssh", host])`` from a test taking that very call OUT of the
#: path. Both here are the second kind, and each is anchored on the construct that makes
#: it so:
#:
#: 1. ``monkeypatch.setattr(<module>, "ssh", fake)`` — pytest's fixture,
#:    REPLACING the seam. The opposite of reaching a rig, and the reason a
#:    probe test can substitute ``servelib.ssh`` and touch no machine.
#: 2. ``CompletedProcess(args=["ssh", host], returncode=..., ...)`` — the
#:    stdlib's RESULT record, which a stub hands back in place of a call that
#:    was never made. It is a plain container; running one is not among the
#:    things it can do. Two anchors, either of which settles it on its own:
#:    the constructor named on the line, or a ``returncode=`` beside the argv,
#:    which no spawning API in the stdlib accepts — ``subprocess.run`` and
#:    ``Popen`` both raise ``TypeError`` on it. So the second reads the
#:    constructor wrapped over two lines, which is how black formats it.
#:
#: Only the matched text is erased, never the file's text around it — deleting
#: more would hide a real spawn written the same way — and the whole of the rest
#: of the line is still scanned. An argv, a command string or a
#: second seam anywhere else on the line survives the erasure and is still a
#: hit, INCLUDING inside the substitute itself:
#: ``monkeypatch.setattr(servelib, "ssh", lambda h: run(["ssh", h]))`` is
#: caught on its second ``"ssh",``. Neither spelling can be reached by
#: accident either: a bare ``setattr`` is not exempt, only ``monkeypatch.``'s,
#: and both require the seam to be the FIRST element of the argv, so
#: ``run(args=["env", "ssh", h])`` is untouched. The substitution is
#: deliberately single-line: one wrapped over two leaves ``servelib, "ssh",
#: rig`` alone on one of them and is a hit, which is the safe way to fail.
SEAM_MENTION = re.compile(
    r"\bmonkeypatch\.setattr\(\s*[A-Za-z_][\w.]*\s*,\s*"
    r"[\"'](?:/usr/bin/)?(?:ssh|scp|rsync|sftp)[\"']\s*,"
    r"|(?<![\w.])(?:subprocess\.)?CompletedProcess\(\s*args\s*=\s*\[\s*"
    r"[\"'](?:/usr/bin/)?(?:ssh|scp|rsync|sftp)[\"']\s*,"
    r"|\bargs\s*=\s*\[\s*[\"'](?:/usr/bin/)?(?:ssh|scp|rsync|sftp)[\"']\s*,"
    r"(?=[^()]*\breturncode\s*=)"
)


def _scanned(line: str) -> str:
    """The line as every pattern here reads it: a :data:`SEAM_MENTION` erased,
    and nothing else on the line touched."""
    return SEAM_MENTION.sub(" <seam mention> ", line)


#: The door and what stands behind it. Path glob -> why it may reach a rig.
#: ``fnmatch`` semantics: ``*`` crosses ``/``. ``run.py`` itself is NOT here
#: and must not be: it reaches no rig, it only runs the gate scripts in
#: order, which is what makes this list the complete set of places a rig is
#: touched from. Nor is ``tools/bench/serving/*`` allowed an ssh of its own:
#: the harness reaches a rig through ``contract.ssh``, which is
#: ``gatelib.ssh`` — see ``test_the_serving_harness_spawns_no_ssh_of_its_own``.
ALLOWED: dict[str, str] = {
    "src/mcgyvr/serving/gatelib.py": (
        "the ssh spawns in src/ and tools/: gatelib.ssh, which refuses outside "
        "the door and to any host but the door's — gate 2, gate 7, the geometry "
        "read and the serving harness (contract.ssh) all go through it — the "
        "shims' own lease check, which admits the same way, and "
        "gatelib.ssh_read_only, the sanctioned read-only detection path "
        "(the shipped rig scan, the `*.gguf` discovery, and the "
        "shipped-reader header read `mcgyvr recommend` runs) that admits "
        "nothing else"
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
        "the shipped step: it proves the door (gatelib.under_door) first, then "
        "runs the shims BY PATH under RUN_BIN, never an ssh or docker from PATH"
    ),
    "tools/runs/_common.sh": (
        "the emitter every campaign step sources: rig_snapshot and image_digest "
        "prove the door, then run the shims by path under RUN_BIN; "
        "door_required refuses without the RUN_* only the door exports AND "
        "without the door itself"
    ),
    "tools/runs/drivers/*.py": (
        "the sweep drivers: gatelib.door_required at startup, their ssh through "
        "gatelib.ssh, and their plain `docker` the shim under the door"
    ),
    "tools/runs/campaigns/**/*.sh": (
        "campaign steps; their plain `ssh`/`docker` are the shims under the "
        "door, and they refuse without RUN_ID, which only the door exports"
    ),
    "tools/bench/serving/backends/*.py": (
        "a `docker run` command LINE the serving backends ship to the rig over "
        "contract.ssh -> gatelib.ssh; nothing here spawns a process of its own"
    ),
    "tests/red_port/test_dod_rig_lease.py": (
        "`docker run` and `ssh` LINES inside steps a test runs under the door: "
        "the ssh asks the stub rig what its lease says, and the launch proves "
        "the shim refuses it once the run's lease is gone — the test asserts it "
        "never reached the daemon"
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
    "tests/test_serving_gatelib.py": (
        "drives gatelib.ssh under a fake door against an ssh stub"
    ),
    "tests/test_serving_door_cli.py": (
        "drives the shims under a fake door against ssh and docker stubs"
    ),
}


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


def _matching(pattern: re.Pattern[str], text: str) -> list[str]:
    """Every code line of ``text`` the pattern hits, seam mentions erased.

    The whole decision, in one place, so the test that pins it below is asking
    the same question of the same code the tree-wide scans ask.
    """
    return [line[:100] for line in _code_lines(text) if pattern.search(_scanned(line))]


def _hits(
    pattern: re.Pattern[str], roots: tuple[str, ...], *, root_files: bool = False
) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for path in _sources(roots, root_files=root_files):
        lines = _matching(pattern, path.read_text(encoding="utf-8", errors="replace"))
        if lines:
            hits[_rel(path)] = lines
    return hits


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


#: Lines that must NOT read as a spawn: the seam's name, in the two spellings
#: that provably start nothing. Every one of these reaches no machine.
A_SEAM_MENTION = (
    'monkeypatch.setattr(servelib, "ssh", rig)',
    'monkeypatch.setattr(gatelib, "ssh", fake_ssh)',
    'monkeypatch.setattr(mcgyvr.serving.servelib, "ssh", rig)',
    'return subprocess.CompletedProcess(args=["ssh", HOST], returncode=0, stdout="")',
    'CompletedProcess(args=["scp", HOST], returncode=1, stdout="")',
    # The constructor as black wraps it: the argv line stands alone, and the
    # ``returncode=`` beside it is the anchor.
    'args=["ssh", HOST], returncode=code, stdout=stdout, stderr=""',
)

#: Lines that must STILL read as a spawn, with the erasure in force. The first
#: is the plain argv the guard has always caught; the rest are the ``SEAM``
#: trick attempted against a call that really does reach a rig, in each shape
#: the erasure could have been hoped to cover. If any of these stops being a
#: hit, the guard has been made weaker and not smarter.
STILL_A_SPAWN = (
    'subprocess.run(["ssh", host, "nvidia-smi"])',
    'monkeypatch.setattr(servelib, "ssh", lambda h, c: subprocess.run(["ssh", h, c]))',
    'monkeypatch.setattr(servelib, "ssh", lambda h, c: os.system(f"ssh {h} {c}"))',
    'monkeypatch.setattr(servelib, "ssh", fake); subprocess.run(["ssh", host])',
    # A bare ``setattr`` is not pytest's fixture and is not exempt.
    'setattr(servelib, "ssh", fake)',
    # The seam is not the first element, so nothing is erased: a real spawn by
    # keyword cannot dress itself as a result record.
    'subprocess.run(args=["env", "ssh", host])',
    # No ``returncode=`` and no constructor: a spawn by keyword is not a record.
    'subprocess.run(args=["ssh", host])',
    'subprocess.run(args=["ssh", host], check=True, capture_output=True)',
    'run(f"ssh srv1 nvidia-smi")',
)


def test_replacing_the_seam_is_not_a_spawn_and_hides_no_spawn() -> None:
    """The scanner tells ``replacing ssh`` from ``calling ssh``.

    ``tests/test_a_sleeping_unit_does_not_read_as_serving.py`` substitutes
    ``servelib.ssh`` in order to touch NO machine, which is the opposite of
    what tripwire 1 looks for, and the list-form pattern could not see the
    difference. That test worked around it by binding the name to a constant —
    and a workaround that lives in the scanned file is one anybody can apply to
    a test that really does reach a rig, because it makes the guard pass by
    changing the text rather than the situation.

    So the erasure is the narrowest thing that settles it: the mention itself
    and not one character more, with the rest of the line still scanned. The
    second half of this test is the part that matters — the same trick, done to
    a real spawn, and still caught.
    """
    for line in A_SEAM_MENTION:
        assert not _matching(SSH_SPAWN, line), f"a substitution read as a spawn: {line}"
    for line in STILL_A_SPAWN:
        assert _matching(SSH_SPAWN, line), (
            f"a spawn slipped through the erasure: {line}"
        )


def test_no_shipped_file_is_exempted_by_the_seam_erasure() -> None:
    """The erasure is a test-suite affordance and must stay one.

    ``monkeypatch`` is pytest's, and a product that hands back a result record
    it did not get from a subprocess is not a thing this repo does. So no line
    under ``src/`` or ``tools/`` — the code that ships, and the code that runs
    a campaign — is read short by it. A first one is argued into a diff here
    rather than absorbed silently, which is the same rule ``ALLOWED`` keeps.
    """
    exempted = {
        _rel(path): lines
        for path in _sources(("src", "tools"), root_files=False)
        if (
            lines := [
                line[:100]
                for line in _code_lines(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                if SEAM_MENTION.search(line)
            ]
        )
    }
    assert not exempted, (
        "a shipped file spells a seam mention, so a line of it is no longer "
        f"scanned whole: {exempted}"
    )


# --------------------------------------------------------------------------
# 2. nothing names its own daemon; 3. no seams
# --------------------------------------------------------------------------


#: Files that spell a daemon override in order to REFUSE it. Path -> why.
REFUSES_A_DAEMON: dict[str, str] = {
    "src/mcgyvr/serving/gatelib.py": (
        "the shim's own implementation: -H ssh://RUN_HOST is set here and a "
        "caller's --context is refused"
    ),
    "src/mcgyvr/sandbox/image.py": (
        "the sandbox's one docker runner names DOCKER_HOST and DOCKER_CONTEXT "
        "to refuse under either: a container the product starts lands on this "
        "machine's daemon or nowhere"
    ),
}


def test_nothing_under_tools_or_src_names_its_own_daemon() -> None:
    hits = _hits(DAEMON_OVERRIDE, ("src", "tools"))
    for rel in REFUSES_A_DAEMON:
        assert (REPO / rel).is_file(), f"{rel} is allowed a mention and does not exist"
        hits.pop(rel, None)
    assert not hits, (
        "a daemon of its own, or the door's environment stripped — under the "
        f"door `docker` reaches ssh://RUN_HOST and nothing else: {hits}"
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
# 4. a hand-set RUN_* environment admits nothing
# --------------------------------------------------------------------------

GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"
DEFAULT_STEP = GATE_SCRIPTS / "default-step.sh"


def _stubs(where: Path) -> Path:
    """An ``ssh`` and a ``docker`` that log every argv and fail. Nothing in
    this section may reach either; the absence of a log is the evidence."""
    where.mkdir(parents=True, exist_ok=True)
    for name in ("ssh", "docker"):
        path = where / name
        path.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> '{where / (name + '.log')}'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
    return where


def _reached(stubs: Path) -> list[str]:
    return sorted(
        f"{p.name}: {p.read_text(encoding='utf-8')}" for p in stubs.glob("*.log")
    )


def _hand_set(stubs: Path, tmp_path: Path, **only: str) -> dict[str, str]:
    """Every ``RUN_*`` the door would export, typed in by hand — or just
    ``only`` — with the stubs first on PATH and the test interpreter next, so
    a bash proof finds a python3 that CAN import gatelib and still says no."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUN_", "DOCKER_"))}
    parts = [str(stubs), str(Path(sys.executable).parent)]
    parts += (env.get("PATH") or os.defpath).split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts)
    if only:
        env.update(only)
        return env
    out_dir = tmp_path / "envelope"
    out_dir.mkdir(exist_ok=True)
    env.update(dict.fromkeys(EXPORTED, "x"))
    env.update(
        RUN_ROOT=str(REPO),
        RUN_BIN=str(REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "bin"),
        RUN_REPO=str(REPO),
        RUN_HOST="srv1",
        RUN_ID="2026-09-05-srv1-kernel-arms-kernel-arms",
        RUN_OUT_DIR=str(out_dir),
        RUN_ROUND="r3-05-09-2026",
        RUN_PRODUCT_SHA256="0" * 64,
        RUN_STEP="kernel-arms",
        RUN_CAMPAIGN="srv1-kernel-arms",
        RUN_MODEL="/models/x.gguf",
        RUN_STEP_FILE=str(DEFAULT_STEP),
        RUN_PARALLEL="1",
        RUN_CTX_PER_SLOT="4096",
        RUN_UBATCH="512",
        RUN_DATE="2026-09-05",
        RUN_SUFFIX="",
        RUN_EXPORT_FD="1",
        RUN_SCAN_JSON=str(out_dir / "scan.json"),
        RUN_GEOMETRY_JSON=str(out_dir / "geometry.json"),
        RUN_PLACEMENT_JSON=str(out_dir / "placement.json"),
    )
    return env


def _outside(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` with no door anywhere above it."""
    return subprocess.run(
        argv,
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _refused_naming_the_door(
    done: subprocess.CompletedProcess[str], stubs: Path, what: str
) -> None:
    assert done.returncode == 2, (
        what,
        done.returncode,
        done.stdout[-400:],
        done.stderr,
    )
    assert DOOR in done.stderr, (what, done.stderr[-800:])
    assert _reached(stubs) == [], f"{what} reached a stub outside the door"


@pytest.mark.parametrize("script", sorted(p.name for p in GATE_SCRIPTS.glob("*.py")))
def test_a_gate_with_every_run_variable_typed_in_is_refused_before_any_subprocess(
    tmp_path: Path, script: str
) -> None:
    """Gate 7 once ran ``docker ps`` on the ambient daemon before refusing."""
    stubs = _stubs(tmp_path / "stubs")
    done = _outside(
        [sys.executable, str(GATE_SCRIPTS / script)], _hand_set(stubs, tmp_path)
    )
    _refused_naming_the_door(done, stubs, script)


def test_the_default_step_with_every_run_variable_typed_in_is_refused_outside_the_door(
    tmp_path: Path,
) -> None:
    stubs = _stubs(tmp_path / "stubs")
    done = _outside(["bash", str(DEFAULT_STEP)], _hand_set(stubs, tmp_path))
    _refused_naming_the_door(done, stubs, "default-step.sh")


# --------------------------------------------------------------------------
# 5. no Python sits at the repository root
# --------------------------------------------------------------------------


def test_no_python_sits_at_the_repo_root() -> None:
    loose = sorted(p.name for p in REPO.glob("*.py"))
    assert not loose, (
        f"{loose} at the repo root: a driver that can be run bare prints "
        "unstamped rows. Drivers live in tools/runs/drivers/ and refuse without RUN_ID."
    )
