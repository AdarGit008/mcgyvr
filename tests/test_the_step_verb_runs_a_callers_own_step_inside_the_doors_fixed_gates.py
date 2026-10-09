"""``step`` runs one script of the caller's own, inside the door's fixed gates.

Owner, 2026-10-08 (design 2b, Option A): the door gets a ``step`` verb, the
generic half of the campaign run: the profile, the rig's lease and reading,
its daemon, the envelope, then the caller's step, then teardown and parse,
whatever the step did, and the lease released last. A caller's gates
(``--gates``) run inside that order, by phase, as on ``serve``. The verb is
visible to users, and ``--help`` names it as an advanced command.

The seal holds under it as under every verb: the step reaches the rig only
through the door's shims, which admit the door's host alone, and the lease is
the run's while it runs. That the shims refuse a process the door did not
start is ``tests/test_serving_gatelib.py``'s, whatever verb opened the door.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
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
        ["step", "--host", usermode.RIG, *argv],
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert onedoor.ssh_log(stubs) == []
    assert usermode.door_logs(usermode.home()) == []


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


#: A caller's ``after`` gate of the shape the lab's serving-markers gate is:
#: run by the door's Python, it loads the door's gate library, reads the tree
#: and the campaign the run names, and refuses through the library when the
#: campaign's folder under its root says so.
CAMPAIGN_GATE = """\
#!/usr/bin/env python3
import os
from mcgyvr.serving import gatelib

where = gatelib.root()
name = os.environ.get("RUN_CAMPAIGN", "")
with open(os.environ["SEEN"], "a", encoding="utf-8") as out:
    out.write(f"root={where} campaign={name} host={os.environ.get('RUN_HOST')}\\n")
if (where / "campaigns" / name / "refuse").exists():
    gatelib.refuse(f"campaign {name} is refused by the caller's own rule")
"""


@pytest.mark.parametrize("refuses", [False, True])
def test_a_callers_after_gate_reads_the_campaign_the_step_run_names(
    tmp_path: Path, refuses: bool
) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    record = tmp_path / "record.txt"
    script = usermode.step_script(tmp_path, record)
    lab = tmp_path / "callers-tree"
    cg.executable(lab / "gates" / "campaign.py", CAMPAIGN_GATE)
    (lab / "campaigns" / usermode.CAMPAIGN).mkdir(parents=True)
    if refuses:
        (lab / "campaigns" / usermode.CAMPAIGN / "refuse").touch()
    listed = cg.write_list(
        tmp_path / "step.json", str(lab), [cg.entry("gates/campaign.py", "after")]
    )
    seen = tmp_path / "seen.txt"

    done = usermode.door(
        usermode.step(script, extra=("--gates", str(listed))),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={
            "MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path)),
            "SEEN": str(seen),
        },
    )

    said = done.stdout + done.stderr
    assert seen.read_text(encoding="utf-8").split() == [
        f"root={lab.resolve()}",
        f"campaign={usermode.CAMPAIGN}",
        f"host={usermode.RIG}",
    ]
    if refuses:
        assert done.returncode == 2, said
        assert "refused by the caller's own rule" in said
        assert not record.exists()
    else:
        assert done.returncode == 0, said
        assert record.exists()
    assert onedoor.read_lease(tmp_path) is None


#: The four serving flags of a step run and the variable each is exported as.
SERVING = {
    "--model": ("RUN_MODEL", "/models/x.gguf"),
    "--parallel": ("RUN_PARALLEL", "4"),
    "--ctx-per-slot": ("RUN_CTX_PER_SLOT", "2048"),
    "--ubatch": ("RUN_UBATCH", "256"),
}


@pytest.mark.parametrize("given", [False, True])
def test_a_step_exports_a_serving_flag_only_when_it_is_given(
    tmp_path: Path, given: bool
) -> None:
    """Owner, on mcgyvr#633: a step run has no defaults for these four; the
    campaign run keeps its own."""
    usermode.save_rig()
    stubs = usermode.machine(tmp_path, pending=())
    record = tmp_path / "record.txt"
    script = usermode.step_script(tmp_path, record)
    extra = [part for flag, (_, value) in SERVING.items() for part in (flag, value)]

    done = usermode.door(
        usermode.step(script, extra=tuple(extra) if given else ()),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )

    assert done.returncode == 0, done.stdout + done.stderr
    seen = usermode.recorded(record)
    for name, value in SERVING.values():
        assert seen[name] == (value if given else "UNSET"), name


def test_a_step_refuses_an_inherited_run_variable_before_any_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    monkeypatch.setenv("RUN_OUT_ROOT", str(tmp_path))

    assert run.main(cg.step_argv(tmp_path)) == 2
    assert _order(log) == []
