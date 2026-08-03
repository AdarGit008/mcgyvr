"""The environment-resolved semantic rung (#123), driven for real.

The temp-directory sandbox runs commands on the host in a real git workspace,
so these exercise the whole rung — stage the engine, resolve against a live
interpreter, map the report back into findings — without a Docker daemon,
which is how the acceptance rung and the sandbox suite are already tested.
"The environment this code will run in" is this interpreter and its stdlib
here; in production it is the per-repo image. The mechanism is identical.

The issue's three acceptance criteria are pinned directly: an unresolvable
call on an added line is reported, a resolvable one is not, and a finding
outside ``added_lines`` never appears. Beyond them, the cases #129 measured
are pinned as regressions — every distinct false positive that measurement
produced was correct platform-conditional code, and each of those four sites
has a test here shaped like the code that produced it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.gate.semantic import (
    CHECK,
    ENGINE_COMMIT,
    ENGINE_DIGESTS,
    STAGING_DIR,
    SemanticCheck,
    SemanticReport,
    engine_dir,
    verify_engine,
)
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "records"
    / "evidence"
    / "ghostcall-2026-08-02"
    / "MANIFEST.json"
)


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed git repository with one boring module as its base."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _run(repo: Path, files: dict[str, str], **kwargs: object) -> SemanticReport:
    """Write ``files`` into a sandbox of ``repo``, then run the rung over them.

    Writing *inside* the sandbox is what makes the written lines added lines:
    the workspace's base commit is the repository as it stood, so the change
    set attributes exactly what the fake worker just wrote.
    """
    with TempDirSandbox(repo) as sandbox:
        for name, text in files.items():
            path = sandbox.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        check = SemanticCheck(sandbox, **kwargs)  # type: ignore[arg-type]
        report = check.run(changeset)
        assert not (sandbox.workspace / STAGING_DIR).exists(), (
            "the rung must leave nothing behind — the gate judges the worker's "
            "diff, and a staged file would be part of what delivery commits"
        )
    return report


def _reported(report: SemanticReport) -> tuple[object, ...]:
    """Whatever the rung said about the change, blocking or not."""
    return report.findings + report.observations


# --- the three acceptance criteria ---------------------------------------


def test_a_call_no_installed_package_defines_is_reported(repo: Path) -> None:
    """Acceptance criterion 1, and the coverage `tests_pass` cannot give."""
    report = _run(
        repo,
        {
            "worker.py": (
                "import json\n"
                "\n"
                "\n"
                "def dump(value):\n"
                "    return json.dumps_everything(value)\n"
            )
        },
    )
    assert len(report.observations) == 1
    finding = report.observations[0]
    assert finding.check == CHECK
    assert finding.code == "unresolved"
    assert finding.path == "worker.py"
    assert finding.line == 5
    assert "dumps_everything" in finding.message
    assert report.environment_issues == ()


def test_a_call_resolving_against_an_installed_package_is_not_reported(
    repo: Path,
) -> None:
    """Acceptance criterion 2. `json.dumps` exists, so there is nothing to say."""
    report = _run(
        repo,
        {"worker.py": "import json\n\n\ndef d(value):\n    return json.dumps(value)\n"},
    )
    assert _reported(report) == ()
    assert report.environment_issues == ()
    assert report.resolved == 1


def test_a_call_outside_the_added_lines_is_not_reported(repo: Path) -> None:
    """Acceptance criterion 3: pre-existing state never fails a worker's change."""
    existing = "import json\n\n\ndef old():\n    return json.dumps_everything(1)\n"
    (repo / "worker.py").write_text(existing, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "the bad call was already there")

    report = _run(repo, {"worker.py": existing + "\n\ndef fresh():\n    return 2\n"})
    assert _reported(report) == ()


# --- the false positives #129 measured, each pinned as a regression -------


def test_platform_guarded_code_is_not_flagged(repo: Path) -> None:
    """`os.startfile` under a platform test — two of the four observed sites."""
    report = _run(
        repo,
        {
            "worker.py": (
                "import os\n"
                "import sys\n"
                "\n"
                "\n"
                "def open_it(path):\n"
                "    if sys.platform == 'win32':\n"
                "        return os.startfile(path)\n"
                "    return os.system('open ' + path)\n"
            )
        },
    )
    assert _reported(report) == ()
    # Two, not one: the resolver's unit is a dotted chain rooted at an import,
    # so the guard's own `sys.platform` is suppressed along with the call it
    # guards. Both sit inside the branch that carries no verdict.
    assert dict(report.suppressed) == {"platform-guarded": 2}


def test_a_platform_constant_reached_by_relative_import_is_followed(
    repo: Path,
) -> None:
    """`from ._compat import WIN` then `if WIN:` — the shape click actually has.

    This is why a rule that only reads the file it is checking is not enough:
    the guard is a name, and what makes it a platform test lives one module
    away. Both of the `os.startfile` sites the measurement produced were
    guarded exactly like this.
    """
    report = _run(
        repo,
        {
            "pkg/__init__.py": "",
            "pkg/_compat.py": "import sys\n\nWIN = sys.platform.startswith('win')\n",
            "pkg/term.py": (
                "import os\n"
                "\n"
                "from ._compat import WIN\n"
                "\n"
                "\n"
                "def open_it(path):\n"
                "    if WIN:\n"
                "        return os.startfile(path)\n"
                "    return None\n"
            ),
        },
    )
    assert _reported(report) == ()
    assert dict(report.suppressed) == {"platform-guarded": 1}


def test_an_attribute_on_a_runtime_rebound_stream_is_not_flagged(repo: Path) -> None:
    """`sys.stdout._original_fd` — click's own test shim, the other two sites."""
    report = _run(
        repo,
        {
            "worker.py": (
                "import sys\n\n\ndef fd():\n    return sys.stdout._original_fd\n"
            )
        },
    )
    assert _reported(report) == ()
    assert dict(report.suppressed) == {"runtime-rebound-root": 1}


def test_an_import_guarded_block_is_not_flagged(repo: Path) -> None:
    """A module the code already knows may be absent carries no verdict."""
    report = _run(
        repo,
        {
            "worker.py": (
                "def probe():\n"
                "    try:\n"
                "        import json\n"
                "\n"
                "        return json.no_such_helper()\n"
                "    except ImportError:\n"
                "        return None\n"
            )
        },
    )
    assert _reported(report) == ()
    assert dict(report.suppressed) == {"import-guarded": 1}


def test_a_type_checking_block_is_not_flagged(repo: Path) -> None:
    """`if TYPE_CHECKING:` never executes, so the live interpreter has no view."""
    report = _run(
        repo,
        {
            "worker.py": (
                "from typing import TYPE_CHECKING\n"
                "\n"
                "import json\n"
                "\n"
                "if TYPE_CHECKING:\n"
                "    Alias = json.NotAThing()\n"
            )
        },
    )
    assert _reported(report) == ()
    assert dict(report.suppressed) == {"type-checking-only": 1}


# --- degraded environments are never a rejection --------------------------


def test_an_unimportable_root_is_an_environment_issue_never_a_finding(
    repo: Path,
) -> None:
    """The failure mode that makes the rung vacuous is the one it says loudest."""
    report = _run(
        repo,
        {
            "worker.py": (
                "import definitely_not_installed_42\n"
                "\n"
                "\n"
                "def go():\n"
                "    return definitely_not_installed_42.anything()\n"
            )
        },
    )
    assert _reported(report) == ()  # the worker is not blamed
    assert len(report.environment_issues) == 1
    issue = report.environment_issues[0]
    assert "definitely_not_installed_42" in issue
    assert "not a rejected change" in issue
    assert "blind here, not satisfied" in issue  # nothing resolved at all


def test_an_interpreter_that_cannot_run_is_an_environment_issue(repo: Path) -> None:
    report = _run(
        repo,
        {"worker.py": "import json\n\n\ndef go():\n    return json.nope()\n"},
        interpreter=("this-interpreter-does-not-exist-42",),
    )
    assert _reported(report) == ()
    assert len(report.environment_issues) == 1
    assert "no semantic check ran" in report.environment_issues[0]


def test_a_file_that_does_not_parse_is_not_this_rungs_verdict(repo: Path) -> None:
    """The syntax rung owns unparseable files; this one reports and moves on."""
    report = _run(repo, {"worker.py": "def broken(:\n"})
    assert _reported(report) == ()
    assert len(report.environment_issues) == 1
    assert "was not resolved" in report.environment_issues[0]


def test_a_change_with_no_python_is_a_no_op(repo: Path) -> None:
    """JS/TS inherits a no-op until an equivalent resolver exists there (#133)."""
    report = _run(repo, {"app.js": "export const x = 1;\n"})
    assert report == SemanticReport()


# --- policy: report by default, block by decision -------------------------


def test_blocking_is_off_by_default_and_a_report_does_not_reject(repo: Path) -> None:
    """#129 bounds the false-positive rate under ~0.8%, on 358 chains. Thin."""
    report = _run(
        repo,
        {"worker.py": "import json\n\n\ndef go():\n    return json.nope()\n"},
    )
    assert report.findings == ()
    assert len(report.observations) == 1


def test_the_blocking_policy_turns_the_same_report_into_a_rejection(
    repo: Path,
) -> None:
    report = _run(
        repo,
        {"worker.py": "import json\n\n\ndef go():\n    return json.nope()\n"},
        blocking=True,
    )
    assert report.observations == ()
    assert len(report.findings) == 1


# --- the engine pin -------------------------------------------------------


def test_the_pinned_digests_match_the_vendored_evidence(tmp_path: Path) -> None:
    """The pin in the code and the pin in the record are the same pin.

    Two copies of a hash are two chances to drift. This is the test that makes
    re-pinning the resolver a deliberate act rather than something a stray edit
    can do quietly — which is the whole of the version policy #123 asked for.
    """
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["source_commit"] == ENGINE_COMMIT
    recorded = {
        entry["path"].rsplit("/", 1)[-1]: entry["sha256"]
        for entry in manifest["files"]
        if entry["path"].startswith("src/ghostcall/")
    }
    for name, digest in ENGINE_DIGESTS.items():
        assert recorded[name] == digest


def test_the_vendored_engine_satisfies_its_own_pin() -> None:
    """The bytes on disk are the bytes the measurement was taken against."""
    assert verify_engine(engine_dir()) is None


def test_a_tampered_engine_refuses_to_run_and_blames_no_worker(
    tmp_path: Path,
) -> None:
    """Fail-closed means *not running*, not rejecting."""
    fake = tmp_path / "engine"
    fake.mkdir()
    source = engine_dir()
    for name in ENGINE_DIGESTS:
        (fake / name).write_bytes((source / name).read_bytes())
    (fake / "checker.py").write_bytes(b"# tampered\n")

    issue = verify_engine(fake)
    assert issue is not None
    assert "does not match the digest pinned" in issue
    assert "was not run" in issue


def test_a_tampered_engine_stops_the_rung_before_it_stages(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "engine"
    fake.mkdir()
    source = engine_dir()
    for name in ENGINE_DIGESTS:
        (fake / name).write_bytes((source / name).read_bytes())
    (fake / "parser.py").write_bytes(b"# tampered\n")
    monkeypatch.setattr("mcgyvr.gate.semantic.engine_dir", lambda: fake)

    report = _run(
        repo, {"worker.py": "import json\n\n\ndef go():\n    return json.nope()\n"}
    )
    assert _reported(report) == ()
    assert len(report.environment_issues) == 1
    assert "does not match the digest pinned" in report.environment_issues[0]


def test_the_wheel_ships_exactly_the_engine_files_that_are_pinned() -> None:
    """The packaged set and the pinned set are the same set, both ways.

    A file shipped but unpinned would be unreviewed code reaching the sandbox;
    a file pinned but unshipped would be a check with nothing behind it in an
    installed mcgyvr — and a checkout would not notice, because there the
    engine is read out of `records/` where the *whole* vendored project sits,
    presentation modules and their three third-party dependencies included.
    Only these four are stdlib-only (CLM-0006), and only these four ship.
    """
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]
    packaged = {
        Path(target).name
        for target in force_include.values()
        if "gate/_engine/ghostcall" in target and target.endswith(".py")
    }
    assert packaged == set(ENGINE_DIGESTS)


def test_only_the_stdlib_only_engine_files_are_staged(repo: Path) -> None:
    """The presentation modules never enter the sandbox — they pull in deps."""
    staged: set[str] = set()

    class _Peeking(SemanticCheck):
        def run(self, changeset: ChangeSet) -> SemanticReport:
            original = self.sandbox.run

            def peek(command: Sequence[str], **kwargs: object) -> object:
                root = self.sandbox.workspace / STAGING_DIR / "engine" / "ghostcall"
                staged.update(p.name for p in root.iterdir())
                return original(command, **kwargs)  # type: ignore[arg-type]

            object.__setattr__(self.sandbox, "run", peek)
            try:
                return super().run(changeset)
            finally:
                object.__setattr__(self.sandbox, "run", original)

    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "worker.py").write_text(
            "import json\n\n\ndef go():\n    return json.dumps(1)\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        _Peeking(sandbox).run(changeset)

    assert staged == set(ENGINE_DIGESTS)


# --- ordering and the gate ------------------------------------------------


def test_the_gate_reports_observations_without_rejecting(repo: Path) -> None:
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "worker.py").write_text(
            "import json\n\n\ndef go():\n    return json.nope()\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        result = Gate().run(changeset, semantic=SemanticCheck(sandbox))

    assert result.accepted  # an observation is not a rejection
    assert len(result.observations) == 1
    assert result.observations[0].check == CHECK


def test_the_semantic_rung_runs_before_acceptance(repo: Path) -> None:
    """ADR-0010's ordering: a sub-second pass does not queue behind a suite."""
    order: list[str] = []

    class _Recording(Acceptance):
        def run(self) -> object:  # type: ignore[override]
            order.append("acceptance")
            return super().run()

    class _RecordingSemantic(SemanticCheck):
        def run(self, changeset: ChangeSet) -> SemanticReport:
            order.append("semantic")
            return super().run(changeset)

    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "worker.py").write_text(
            "import json\n\n\ndef go():\n    return json.dumps(1)\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        Gate().run(
            changeset,
            semantic=_RecordingSemantic(sandbox),
            acceptance=_Recording(sandbox, (("sh", "-c", "exit 0"),)),
        )

    assert order == ["semantic", "acceptance"]


def test_a_blocking_semantic_finding_stops_the_expensive_rung(repo: Path) -> None:
    """Cheap-before-expensive is only worth anything if the cheap one can stop."""
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "worker.py").write_text(
            "import json\n\n\ndef go():\n    return json.nope()\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        result = Gate().run(
            changeset,
            semantic=SemanticCheck(sandbox, blocking=True),
            acceptance=Acceptance(sandbox, (("sh", "-c", "touch ran.marker"),)),
        )
        assert not (sandbox.workspace / "ran.marker").exists()

    assert not result.accepted
    assert [f.check for f in result.findings] == [CHECK]


# --- what the rung stages -------------------------------------------------


def test_the_staged_engine_is_a_faithful_copy(repo: Path) -> None:
    """What runs in the sandbox is byte-for-byte what the digests pin.

    Asserted from inside the run, because the staging directory is removed
    when it ends — the property being checked is what the *interpreter* saw.
    """
    seen: dict[str, str] = {}

    class _Peeking(SemanticCheck):
        def run(self, changeset: ChangeSet) -> SemanticReport:
            original = self.sandbox.run

            def peek(command: Sequence[str], **kwargs: object) -> object:
                staged = self.sandbox.workspace / STAGING_DIR / "engine" / "ghostcall"
                for path in staged.glob("*.py"):
                    seen[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                return original(command, **kwargs)  # type: ignore[arg-type]

            object.__setattr__(self.sandbox, "run", peek)
            try:
                return super().run(changeset)
            finally:
                object.__setattr__(self.sandbox, "run", original)

    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "worker.py").write_text(
            "import json\n\n\ndef go():\n    return json.dumps(1)\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        _Peeking(sandbox).run(changeset)

    assert seen == dict(ENGINE_DIGESTS)
