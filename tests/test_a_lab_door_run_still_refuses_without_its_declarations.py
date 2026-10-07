"""A lab door run is held to the lab's declarations, and never drops to user mode.

Owner, 2026-10-07 (Round 5): the door's user mode is for a door run from an
install; the lab mode is unchanged. A run asked for as ``--mode lab`` whose
lab files are missing refuses: it does not fall back to the user's rig file,
however well that file matches the machine.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile, run
from tests import onedoor, usermode


def _with_a_matching_rig_file() -> None:
    """A user rig file that matches the stub machine exactly."""
    scan = Scan.from_json(json.dumps(usermode.scan_payload()))
    rigfile.write(rigfile.from_scan(usermode.RIG, scan))


def _down(tmp_path: Path, run_root: Path) -> tuple[int, str, Path]:
    stubs = usermode.machine(tmp_path, pending=())
    done = usermode.door(
        usermode.serve("down", usermode.compose_file(tmp_path), mode="lab"),
        stubs=stubs,
        run_root=run_root,
        cwd=tmp_path,
    )
    return done.returncode, done.stdout + done.stderr, stubs


def test_lab_mode_where_there_is_no_lab_checkout_refuses_and_reads_nothing(
    tmp_path: Path,
) -> None:
    _with_a_matching_rig_file()

    code, said, stubs = _down(tmp_path, usermode.install_root(tmp_path))

    assert code == 2, said
    assert str(run.LAB_MARK) in said
    assert onedoor.ssh_log(stubs) == []
    assert onedoor.docker_log(stubs) == []
    assert usermode.door_logs(usermode.home()) == []


def test_lab_mode_without_hosts_json_refuses_at_the_rig_gate(tmp_path: Path) -> None:
    _with_a_matching_rig_file()

    code, said, stubs = _down(tmp_path, usermode.lab_root(tmp_path))

    assert code == 2, said
    assert "hosts.json" in said
    assert "02-rig.py" in said
    assert not any("compose" in line for line in onedoor.docker_log(stubs)), said
    assert usermode.door_logs(usermode.home()) == []


def test_lab_mode_without_its_round_module_refuses_at_gate_1(tmp_path: Path) -> None:
    _with_a_matching_rig_file()
    root = usermode.lab_root(tmp_path)
    (root / run.LAB_MARK / "product.py").unlink()

    code, said, stubs = _down(tmp_path, root)

    assert code == 2, said
    assert "01-round.py" in said
    assert "product.py" in said
    assert onedoor.ssh_log(stubs) == []


def test_lab_mode_with_the_rig_undeclared_refuses_and_names_the_declared_ones(
    tmp_path: Path,
) -> None:
    _with_a_matching_rig_file()
    root = usermode.lab_root(tmp_path)
    hosts = root / run.HOSTS_FILE
    hosts.parent.mkdir(parents=True)
    hosts.write_text(
        json.dumps({"other-box.invalid": {"rig": {"docker": usermode.DOCKER}}}),
        encoding="utf-8",
    )

    code, said, stubs = _down(tmp_path, root)

    assert code == 2, said
    assert "carries no `rig` declaration" in said
    assert "other-box.invalid" in said
    assert not any("compose" in line for line in onedoor.docker_log(stubs)), said
