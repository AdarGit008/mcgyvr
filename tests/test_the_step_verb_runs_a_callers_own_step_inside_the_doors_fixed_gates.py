"""``step`` runs one script of the caller's own, inside the door's fixed gates.

Owner, 2026-10-08 (design 2b, Option A): the door gets a ``step`` verb, the
generic half of the campaign run: the profile, the rig's lease and reading,
its daemon, the envelope, then the caller's step, then teardown and parse,
whatever the step did, and the lease released last. A caller's gates
(``--gates``) run inside that order, by phase, as on ``serve``. The verb is
visible to users, and ``--help`` names it as an advanced command.

The seal holds under it as under every verb: the step reaches the rig only
through the door's shims, which admit the door's host alone and refuse a
process the door did not start, and the lease is the run's while it runs.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg
from tests import onedoor, usermode

#: The door's own entries a step run spawns, in their order.
STEP_RUN = [
    "01-round.py",
    "02-rig.py",
    "03-image.py",
    "05-envelope.py",
    "06-step.py",
    "07-teardown.py",
    "08-parse.py",
    "lease-release.py",
]


def _order(log: Path) -> list[str]:
    return [line.split()[0] for line in cg.log_lines(log)]


def test_a_step_runs_the_doors_gates_in_order_with_the_callers_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    for name in ("early", "late", "last"):
        cg.executable(root / f"{name}.py", cg.gate_text(log, f"caller:{name}"))
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [
            cg.entry("last.py", "always"),
            cg.entry("late.py", "after"),
            cg.entry("early.py", "before"),
        ],
    )

    assert run.main(cg.step_argv(tmp_path, "--gates", str(listed))) == 0

    order = _order(log)
    assert [name for name in order if name.startswith("door:")] == [
        f"door:{script}" for script in STEP_RUN
    ]
    assert order[1] == "caller:early"
    assert order.index("door:03-image.py") < order.index("caller:late")
    assert order.index("caller:late") < order.index("door:05-envelope.py")
    assert order[-2:] == ["caller:last", "door:lease-release.py"]


def test_a_step_that_fails_still_has_teardown_parse_and_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, statuses={"06-step.py": 1})

    assert run.main(cg.step_argv(tmp_path)) == 1

    assert _order(log)[-3:] == [
        "door:07-teardown.py",
        "door:08-parse.py",
        "door:lease-release.py",
    ]


def test_a_step_from_an_install_runs_under_the_seal_and_is_filed_in_the_door_log(
    tmp_path: Path,
) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    record = tmp_path / "record.txt"
    script = usermode.step_script(tmp_path, record)

    done = usermode.door(
        usermode.step(script, step_args=("--rounds", "3")),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )

    said = done.stdout + done.stderr
    assert done.returncode == 0, said
    seen = usermode.recorded(record)
    run_id = f"{usermode.RUN_DATE}-{usermode.CAMPAIGN}-my-step"
    assert seen["RUN_ID"] == run_id
    assert seen["RUN_CAMPAIGN"] == usermode.CAMPAIGN
    assert seen["RUN_MODE"] == "user"
    assert seen["ARGS"] == "--rounds 3"
    # The step reached the door's host through the shim, and held the lease
    # while it ran; the lease was released when the run ended.
    assert seen["SSH"] == "/home/user"
    assert "echo $HOME" in " ".join(onedoor.ssh_log(stubs))
    assert "lease_id=" in seen["LEASE"]
    assert onedoor.read_lease(tmp_path) is None
    # Filed in the door's log, as a user's serve run is.
    [filed] = usermode.door_logs(usermode.home())
    assert filed.name == run_id
    assert Path(seen["RUN_OUT_DIR"]) == filed
    header = json.loads((filed / f"{run_id}.run.json").read_text(encoding="utf-8"))
    assert header["mode"] == "user"
    assert header["command"].startswith("python -m mcgyvr.serving.run step ")
    end = json.loads((filed / f"{run_id}.end.json").read_text(encoding="utf-8"))
    assert end["step_exit"] == "0"
    assert json.loads((filed / "result.json").read_text("utf-8")) == {"run_id": run_id}


def test_a_step_is_refused_a_host_the_door_was_not_opened_for(tmp_path: Path) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    record = tmp_path / "record.txt"
    other = tmp_path / "other.txt"
    elsewhere = f"ssh other-box.invalid 'echo $HOME' 2> '{other}' || true"
    script = usermode.step_script(tmp_path, record, then=elsewhere)

    done = usermode.door(
        usermode.step(script),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "refused" in other.read_text(encoding="utf-8")
    assert not any("other-box" in line for line in onedoor.ssh_log(stubs))


def test_the_shims_refuse_a_process_the_door_did_not_start(tmp_path: Path) -> None:
    """``RUN_*`` typed into a shell is no door: the shim reads the parent chain."""
    stubs = usermode.machine(tmp_path, pending=())
    env = {k: v for k, v in os.environ.items() if not k.startswith("RUN_")}
    env.update(RUN_HOST=usermode.RIG, RUN_ID="typed-by-hand", RUN_MODE="user")
    env["PATH"] = f"{stubs}{os.pathsep}{env.get('PATH', os.defpath)}"

    for shim, argv in (("ssh", [usermode.RIG, "true"]), ("docker", ["ps"])):
        done = subprocess.run(
            [sys.executable, str(run.BIN / shim), *argv],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 2, done.stderr
        assert "not started by the door" in done.stderr
    assert onedoor.ssh_log(stubs) == []
    assert onedoor.docker_log(stubs) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--campaign", usermode.CAMPAIGN],
        ["--campaign", usermode.CAMPAIGN, "--step", "no-such-step.sh"],
        ["--campaign", "../elsewhere", "--step", "STEP"],
        ["--campaign", "", "--step", "STEP"],
        ["--campaign", usermode.CAMPAIGN, "--step", "STEP", "--model", "x y"],
    ],
    ids=["no-step", "missing-step", "campaign-path", "campaign-empty", "bad-model"],
)
def test_a_step_run_that_cannot_be_said_is_refused_before_any_gate(
    tmp_path: Path, argv: list[str]
) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    script = usermode.step_script(tmp_path, tmp_path / "record.txt")
    argv = [str(script) if word == "STEP" else word for word in argv]

    done = usermode.door(
        ["step", "--host", usermode.RIG, "--mode", "user", *argv],
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert onedoor.ssh_log(stubs) == []
    assert usermode.door_logs(usermode.home()) == []


def test_a_lab_step_is_held_to_the_labs_declarations_and_filed_by_campaign(
    tmp_path: Path,
) -> None:
    """Lab mode stays as it is: the step verb's lab run is the campaign run's,
    without the workload and the data scripts."""
    root = onedoor.fixture_repo(tmp_path)
    env_file = tmp_path / "step.env"
    step = onedoor.add_step(
        root, "probe-camp", "1-probe.sh", onedoor.probe_step(env_file)
    )
    argv = [sys.executable, str(root / onedoor.DOOR_REL), "step", "--mode", "lab"]
    argv += ["--host", "srv1", "--campaign", "probe-camp", "--step", str(step)]
    argv += ["--date", onedoor.RUN_DATE]

    done = subprocess.run(
        argv,
        cwd=root,
        env=onedoor.door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    said = done.stdout + done.stderr
    assert done.returncode == 0, said
    assert "04-workload" not in said and "data-10" not in said
    envelope = onedoor.envelope(root, "probe-camp")
    assert (envelope / "probe.tsv").is_file()
    seen = onedoor.read_env_file(env_file)
    assert seen["RUN_ROUND"] == onedoor.pinned(root)[0]
    assert onedoor.read_lease(root) is None


def test_the_doors_help_names_step_as_an_advanced_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        run.main(["--help"])
    assert exited.value.code == 0
    top = capsys.readouterr().out
    assert "step" in top and "advanced" in top, top

    with pytest.raises(SystemExit) as exited:
        run.main(["step", "--help"])
    assert exited.value.code == 0
    own = capsys.readouterr().out
    for flag in ("--step", "--campaign", "--out-root", "--gates", "--host"):
        assert flag in own, own
    assert "advanced" in own
    for hole in ("--skip", "--force", "--no-"):
        assert hole not in own
