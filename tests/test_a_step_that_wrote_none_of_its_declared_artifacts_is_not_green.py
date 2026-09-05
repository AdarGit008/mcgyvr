"""Gate 8, the other half: a declared artifact that is not there is not checked.

The door reads back every declared artifact before it returns 0 (gate 8,
``08-parse.py``). The first cut treated an absent file as a note on stderr and
went on to print a green line: a step that wrote nowhere (``--dry-run``, every
real step's "write no file" mode) was reported as done, and a ``RUN_REWRITES``
file that gate 5 had just moved aside was left vacated under that green line —
the pass-1 evidence gone from its name under exit 0.

So an artifact declared under ``RUN_ARTIFACTS`` or ``RUN_REWRITES`` that is
absent after a step that exited 0 is exit 1 naming it: a run that measured
nothing is not green. A superseded file whose successor was never written is
put back under its own name (nothing recorded is lost, and the name still
resolves). What the door itself filed before the step — ``scan.json``,
``geometry.json``, ``placement.json``, the rig's and the checkpoint's own
account of themselves — stays: those were read, and a reading is not undone
because the step after it wrote nothing.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

DRY = (
    'case "${1:-}" in --dry-run) echo "probe: dry run, writing nothing"; exit 0;; '
    "esac\n"
)


def _writes_nothing(env_file: Path, *, directive: str = "RUN_ARTIFACTS") -> str:
    """The probe step, honouring ``--dry-run`` the way every real step does."""
    body = onedoor.probe_step(env_file, directive=directive)
    return body.replace(
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n', DRY + 'out="${RUN_OUT_DIR:?}/probe.tsv"\n'
    )


def test_a_declared_artifact_that_was_not_written_is_exit_1_and_named(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", _writes_nothing(tmp_path / "e"))
    result = onedoor.door(
        root, Scenario("alpha", "1-probe.sh", step_args=("--dry-run",))
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert onedoor.filed_by_steps(root) == [], onedoor.written_under_records(root)


def test_a_rewriting_pass_that_wrote_nothing_puts_the_earlier_pass_back(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _writes_nothing(tmp_path / "e", directive="RUN_REWRITES"),
    )
    first = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert first.returncode == 0, (first.stdout, first.stderr)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    pass1 = artifact.read_text(encoding="utf-8")

    second = onedoor.door(
        root,
        Scenario("alpha", "1-probe.sh", suffix="pass2", step_args=("--dry-run",)),
    )
    assert second.returncode == 1, (second.stdout, second.stderr)
    assert "probe.tsv" in second.stderr, second.stderr
    assert artifact.is_file(), onedoor.written_under_records(root)
    assert artifact.read_text(encoding="utf-8") == pass1, (
        "the pass-1 file did not come back under its own name byte for byte"
    )
    assert onedoor.filed_by_steps(root) == [str(artifact.relative_to(root))], (
        "a superseded copy was left beside a name that was never rewritten"
    )
