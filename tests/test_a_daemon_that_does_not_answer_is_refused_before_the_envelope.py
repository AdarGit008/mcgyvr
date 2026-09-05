"""Gate 3: the daemon a tag is resolved through must answer now, not inside the step.

Gate 3's contract says the daemon "must be reachable now"; the first cut
checked only that a docker CLI was on PATH. With the CLI installed and the
daemon stopped, gates 1-5 passed, the envelope was made, ``RUN_ID`` minted,
and the first ``image_digest`` failure landed inside the step — after
``start_stamp``/``round_stamp`` — so the artifact carried WORKLOAD/START/ROUND
and then REFUSED rows whose reason was the daemon, filed against the arm.

So gate 3 (``03-image.py``) asks ``docker info`` — the ``docker`` on the
door's PATH, which lands on the rig's daemon — and refuses with exit 2 when
it fails, before gate 4, the envelope and the step.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario


def test_a_docker_cli_with_no_daemon_is_exit_2_with_nothing_written(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    onedoor.docker_stub(onedoor.stubs_dir(root), daemon_down=True)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "gate 3" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert not onedoor.envelope(root, "alpha").exists()
    assert not (tmp_path / "e").exists(), (
        "the step ran with no daemon to resolve a tag through"
    )
    assert any(line.startswith("info") for line in onedoor.docker_log(root)), (
        "the door never asked the daemon"
    )
