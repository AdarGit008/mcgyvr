"""``step --out-root DIR`` files the run under ``DIR/<date>-<campaign>/``.

Owner, 2026-10-08 (design 2b): the lab keeps its evidence layout, one
``<date>-<campaign>/`` folder per run under its evidence folder, by naming
that folder as the step run's out-root; a user's run with none is filed in
the door's log. The folder exists, or the run is refused before any gate:
the door never makes the folder a run is filed under. And a step's own
output flag still cannot leave the envelope.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests import onedoor, usermode


def _step(
    tmp_path: Path, *extra: str, step_args: tuple[str, ...] = ()
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    record = tmp_path / "record.txt"
    script = usermode.step_script(tmp_path, record)
    done = usermode.door(
        usermode.step(script, extra=extra, step_args=step_args),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )
    return done, stubs, record


def test_a_users_step_with_an_out_root_is_filed_there_by_date_and_campaign(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "evidence"
    out_root.mkdir()

    done, _, record = _step(tmp_path, "--out-root", str(out_root))

    assert done.returncode == 0, done.stdout + done.stderr
    envelope = out_root / f"{usermode.RUN_DATE}-{usermode.CAMPAIGN}"
    run_id = f"{usermode.RUN_DATE}-{usermode.CAMPAIGN}-my-step"
    seen = usermode.recorded(record)
    assert Path(seen["RUN_OUT_DIR"]) == envelope
    assert seen["RUN_OUT_ROOT"] == str(out_root.resolve())
    assert json.loads((envelope / "result.json").read_text("utf-8")) == {
        "run_id": run_id
    }
    assert (envelope / f"{run_id}.run.json").is_file()
    assert usermode.door_logs(usermode.home()) == []


def test_an_out_root_named_relative_to_the_working_folder_is_read_from_there(
    tmp_path: Path,
) -> None:
    (tmp_path / "evidence").mkdir()

    done, _, record = _step(tmp_path, "--out-root", "evidence")

    assert done.returncode == 0, done.stdout + done.stderr
    seen = usermode.recorded(record)
    assert Path(seen["RUN_OUT_DIR"]) == (
        tmp_path / "evidence" / f"{usermode.RUN_DATE}-{usermode.CAMPAIGN}"
    )


def test_an_out_root_that_is_not_a_folder_is_refused_before_any_gate(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "no-such-folder"

    done, stubs, record = _step(tmp_path, "--out-root", str(missing))

    assert done.returncode == 2, done.stdout + done.stderr
    assert "--out-root" in done.stderr
    assert not missing.exists(), "the door made the folder it was refused"
    assert onedoor.ssh_log(stubs) == []
    assert not record.exists()


def test_a_step_output_flag_outside_the_out_root_envelope_is_refused(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "evidence"
    out_root.mkdir()
    elsewhere = tmp_path / "elsewhere.json"

    done, stubs, _ = _step(
        tmp_path, "--out-root", str(out_root), step_args=("--out", str(elsewhere))
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert "outside the envelope" in done.stderr
    assert onedoor.ssh_log(stubs) == []


def test_a_step_output_flag_inside_the_out_root_envelope_is_admitted(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "evidence"
    out_root.mkdir()
    inside = out_root / f"{usermode.RUN_DATE}-{usermode.CAMPAIGN}" / "x.json"

    done, _, record = _step(
        tmp_path, "--out-root", str(out_root), step_args=("--out", str(inside))
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert usermode.recorded(record)["ARGS"] == f"--out {inside}"
