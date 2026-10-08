"""A door run from an install holds the rig to the user's own rig file.

Owner, 2026-10-07 (Round 5): the serving door gets a user mode, approved as
drafted. From an install there is no lab checkout, so the round, the lab's
``hosts.json`` and its declared docker version are not asked for. What the
run is held to instead is the rig file ``<rig-file folder>/<rig>.json``, the
rig's read-only scan saved by ``mcgyvr scan --rig``: each run reads the rig
again, says what moved, and refuses only when the fleet no longer fits. The
safety gates stay: the daemon answers and is the machine that was read, the
envelope, the step, the stray-container check and the live-fleet check. Each
run is filed under ``~/.local/state/mcgyvr/door/<date>/<run_id>/``, and a
container mcgyvr did not start is reported and never touched.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile
from tests import onedoor, usermode
from tests.onedoor import STRAY_NAME


def _save_rig(scan: dict[str, object]) -> Path:
    """The rig file as `mcgyvr scan --rig` writes it, from ``scan``."""
    return rigfile.write(
        rigfile.from_scan(usermode.RIG, Scan.from_json(json.dumps(scan)))
    )


def _up(tmp_path: Path, stubs: Path, **extra: str) -> tuple[int, str]:
    compose = usermode.compose_file(tmp_path)
    done = usermode.door(
        usermode.serve("up", compose),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path)), **extra},
    )
    return done.returncode, done.stdout + done.stderr


def test_serve_up_from_an_install_runs_against_the_rig_file_and_files_its_log(
    tmp_path: Path,
) -> None:
    _save_rig(usermode.scan_payload())
    stubs = usermode.machine(tmp_path)

    code, said = _up(tmp_path, stubs)

    assert code == 0, said
    assert any(" up " in f" {line} " for line in onedoor.docker_log(stubs)), said
    # Nothing of the lab was asked for: no round, no hosts.json, no declared
    # docker version; the run root holds none of them.
    assert "hosts.json" not in said
    [run] = usermode.door_logs(usermode.home())
    assert run.parent.name == usermode.RUN_DATE
    header = json.loads((run / f"{run.name}.run.json").read_text(encoding="utf-8"))
    assert header["mode"] == "user"
    assert "serve up" in header["command"]
    assert f"--host {usermode.RIG}" in header["command"]
    assert header["rig_before"]["hostname"] == usermode.HOSTNAME
    assert usermode.UNITS[0] in header["compose"]
    end = json.loads((run / f"{run.name}.end.json").read_text(encoding="utf-8"))
    assert end["step_exit"] == "0"
    assert sorted(end["serving"]) == sorted(usermode.UNITS)
    assert end["rig_after"]["hostname"] == usermode.HOSTNAME
    up = json.loads((run / "serve-up.json").read_text(encoding="utf-8"))
    assert [row["container"] for row in up["units"]] == list(usermode.UNITS)


def test_with_no_rig_file_the_door_says_how_to_make_one_and_starts_nothing(
    tmp_path: Path,
) -> None:
    stubs = usermode.machine(tmp_path)

    code, said = _up(tmp_path, stubs)

    assert code == 2, said
    assert f"mcgyvr scan --rig {usermode.RIG}" in said
    assert onedoor.ssh_log(stubs) == [], "the rig was reached before the refusal"
    assert onedoor.docker_log(stubs) == []
    assert usermode.door_logs(usermode.home()) == []


def test_serve_up_reads_the_rig_file_from_the_named_rigs_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rigs = tmp_path / "rigs-elsewhere"
    rigs.mkdir()
    monkeypatch.setenv("MCGYVR_RIGS", str(rigs))
    _save_rig(usermode.scan_payload())
    stubs = usermode.machine(tmp_path)

    code, said = _up(tmp_path, stubs)

    assert code == 0, said
    assert not (usermode.home() / ".mcgyvr" / "rigs").exists(), said


def test_a_rig_that_moved_but_still_holds_the_fleet_is_said_and_served(
    tmp_path: Path,
) -> None:
    _save_rig(usermode.scan_payload(ram_gb=31.3, docker="26.0.0"))
    stubs = usermode.machine(tmp_path)

    code, said = _up(tmp_path, stubs)

    assert code == 0, said
    assert "moved" in said
    assert "31.3" in said and "62.7" in said, said
    assert "26.0.0" in said and usermode.DOCKER in said, said


def test_a_card_the_fleet_uses_that_shrank_is_refused_before_anything_starts(
    tmp_path: Path,
) -> None:
    _save_rig(usermode.scan_payload())
    smaller = usermode.scan_payload(cards=((0, "Invented Card 8G", 8192),))
    stubs = usermode.machine(tmp_path, scan=smaller)

    code, said = _up(tmp_path, stubs)

    assert code == 2, said
    assert "no longer fits" in said
    assert "card 0" in said
    assert not any("compose" in line for line in onedoor.docker_log(stubs)), said


def test_a_card_the_fleet_uses_that_is_gone_is_refused(tmp_path: Path) -> None:
    _save_rig(
        usermode.scan_payload(
            cards=((0, "Invented Card 16G", 16384), (1, "Invented Card 16G", 16384))
        )
    )
    stubs = usermode.machine(
        tmp_path, scan=usermode.scan_payload(cards=((1, "Invented Card 16G", 16384),))
    )

    code, said = _up(tmp_path, stubs)

    assert code == 2, said
    assert "no longer fits" in said
    assert not any("compose" in line for line in onedoor.docker_log(stubs)), said


def test_a_card_the_fleet_does_not_use_may_go_away(tmp_path: Path) -> None:
    _save_rig(
        usermode.scan_payload(
            cards=((0, "Invented Card 16G", 16384), (1, "Invented Card 16G", 16384))
        )
    )
    stubs = usermode.machine(tmp_path)

    code, said = _up(tmp_path, stubs)

    assert code == 0, said
    assert "moved" in said


def test_a_container_mcgyvr_did_not_start_is_reported_and_left_alone(
    tmp_path: Path,
) -> None:
    _save_rig(usermode.scan_payload())
    stubs = usermode.machine(
        tmp_path, containers="c0ffee000002", gpu_procs="7777,someones-app,900MiB"
    )
    flag = tmp_path / "stray-is-up"
    flag.touch()
    onedoor.docker_stub(stubs, stray_flag=flag)

    code, said = _up(tmp_path, stubs)

    assert code == 0, said
    assert "c0ffee000002" in said, "the foreign container was not reported"
    assert "someones-app" in said, "the foreign card holder was not reported"
    assert not any(line.startswith("rm") for line in onedoor.docker_log(stubs))
    assert not any(STRAY_NAME in line for line in onedoor.docker_log(stubs))


def test_the_daemon_must_be_the_rig_that_was_read(tmp_path: Path) -> None:
    _save_rig(usermode.scan_payload())
    stubs = usermode.machine(tmp_path)
    (stubs / "docker-name").write_text("box-b\n", encoding="utf-8")

    code, said = _up(tmp_path, stubs)

    assert code == 2, said
    assert "box-b" in said
    assert not any("compose" in line for line in onedoor.docker_log(stubs)), said


def test_a_live_serve_up_starts_only_units_of_the_stamped_fleet(
    tmp_path: Path,
) -> None:
    """No setup at all is the live profile, and no fleet is stamped."""
    _save_rig(usermode.scan_payload())
    stubs = usermode.machine(tmp_path)
    compose = usermode.compose_file(tmp_path)

    done = usermode.door(
        usermode.serve("up", compose),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    assert "fleet lock" in done.stderr
    assert onedoor.docker_log(stubs) == []
