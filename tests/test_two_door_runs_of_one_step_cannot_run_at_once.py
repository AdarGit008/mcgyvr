"""Gate 5 claims the RUN_ID atomically; a second run under it is refused.

``RUN_ID`` is ``<date>-<campaign>-<step>[-<suffix>]``. Two door invocations of
the same step, started within the same minute, mint the same id — and both
passed gate 5's write-once, because neither had written its artifact yet when
the other looked. Two steps then ran against one rig under one id, named their
containers alike, and gate 7 of each found the other's.

So gate 5 (``05-envelope.py``) claims the id before the step: ``os.open`` of
``<RUN_OUT_DIR>/.<RUN_ID>.running`` with ``O_CREAT | O_EXCL``, which exactly
one of two concurrent runs wins. The loser exits 2 saying a run with this
RUN_ID is in progress or died without releasing it, naming the file, and
leaving the decision — wait, or remove it — to the operator. The door
(``run.py``) releases the claim after gates 7 and 8, on every exit path
including an interrupt; a claim still present after a run finished is the
signature of a door that was killed outright.
"""

from __future__ import annotations

import time
from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _waiting_step(env_file: Path, started: Path, go: Path) -> str:
    """The probe step, holding in gate 6 until ``go`` exists."""
    return onedoor.probe_step(
        env_file,
        after=(
            f"touch '{started}'\n"
            f"for i in $(seq 1 1200); do [ -e '{go}' ] && break; sleep 0.1; done\n"
        ),
    )


def test_a_second_run_under_the_same_run_id_is_refused_while_the_first_is_in_gate_6(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    started, go = tmp_path / "started", tmp_path / "go"
    onedoor.add_step(
        root, "alpha", "1-probe.sh", _waiting_step(tmp_path / "e", started, go)
    )
    first = onedoor.door_process(root, PROBE)
    try:
        deadline = time.monotonic() + 120
        while not started.exists():
            assert first.poll() is None, first.communicate()
            assert time.monotonic() < deadline, "the first run never reached its step"
            time.sleep(0.1)
        run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
        claim = onedoor.envelope(root, "alpha") / f".{run_id}.running"
        assert claim.is_file(), onedoor.written_under_records(root)
        assert onedoor.claims(root) == [str(claim.relative_to(root))]
        assert onedoor.filed_by_steps(root) == [
            str((onedoor.envelope(root, "alpha") / "probe.tsv").relative_to(root))
        ], "the claim is not a step's file"

        (tmp_path / "e").unlink()
        second = onedoor.door(root, PROBE)
        assert second.returncode == 2, (second.stdout, second.stderr)
        assert (
            f"a run with this RUN_ID ({run_id}) is in progress or died without "
            f"releasing it; wait, or remove {claim} if you know it is dead"
        ) in second.stderr, second.stderr
        assert not (tmp_path / "e").exists(), "the second step ran under the claim"
        assert claim.is_file(), "the refused run released the other run's claim"

        go.touch()
        _, stderr = first.communicate(timeout=120)
    finally:
        go.touch()
        if first.poll() is None:
            first.kill()
    assert first.returncode == 0, stderr
    assert onedoor.claims(root) == [], "the claim outlived the run that took it"
    assert not claim.exists()


def test_a_claim_left_by_a_run_that_died_is_refused_naming_the_file(
    tmp_path: Path,
) -> None:
    """The other half of the message: nothing is in progress, the file is
    simply there. The door cannot tell the two apart and says so."""
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    envelope = onedoor.envelope(root, "alpha")
    envelope.mkdir(parents=True)
    claim = envelope / f".{onedoor.RUN_DATE}-alpha-probe.running"
    claim.write_text("0\n", encoding="utf-8")
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "in progress or died without releasing it" in result.stderr, result.stderr
    assert str(claim) in result.stderr, result.stderr
    assert claim.is_file(), "the door removed a claim it did not take"
    assert not (tmp_path / "e").exists()

    claim.unlink()
    again = onedoor.door(root, PROBE)
    assert again.returncode == 0, (again.stdout, again.stderr)
    assert onedoor.claims(root) == []


def test_a_completed_run_leaves_no_claim_and_a_suffixed_rerun_takes_its_own(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", directive="RUN_REWRITES"),
    )
    first = onedoor.door(root, PROBE)
    assert first.returncode == 0, (first.stdout, first.stderr)
    assert onedoor.claims(root) == []
    second = onedoor.door(root, Scenario("alpha", "1-probe.sh", suffix="pass2"))
    assert second.returncode == 0, (second.stdout, second.stderr)
    assert onedoor.claims(root) == []
