"""Gate 7 names a leftover container and exits 1; it does not reach for ``rm -f``.

Gate 7 (``07-teardown.py``): ``docker ps --filter "name=^<RUN_ID>-"``, any
line -> stderr names it, exit 1. The first cut also ``rm -f``'d every match,
silently. Docker's name filter is an unanchored regex, ``RUN_ID`` is
``<date>-<campaign>-<step>[-<suffix>]`` and both step names and suffixes carry
dashes, so a no-suffix run's filter ``^…-probe-`` also matches
``…-probe-pass2-lcps`` (a ``--suffix pass2`` run of the same step) and
``…-probe-again-vsweep`` (a step named ``probe-again``): a run tearing down
could kill a neighbouring run's container, and say nothing.

So the door names what it found and stops there; killing is the operator's
call, with the name in hand.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario


def test_a_leftover_is_named_on_stderr_and_no_rm_is_issued(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    onedoor.docker_stub(onedoor.stubs_dir(root), leftover_flag=flag)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"{run_id}-lcps" in result.stderr, result.stderr
    log = onedoor.docker_log(root)
    assert any(line.startswith("ps") for line in log), log
    assert not any(line.startswith("rm") for line in log), (
        f"the door removed a container it only had a prefix match on: {log}"
    )
