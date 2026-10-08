"""A staged setup runs its sample through the door, then is judged and stamped.

Owner, Round 4 (FLEET FLOW TWEAK): confirm = run the sample; green = stamped.
Plan section 8.1 (P7b): the confirmed plan is staged, its units are started
through the serving door in user mode, the sample runs, and the door's own
reads (``read --fleet F --probe U --load WxN``) are what P7a judges and the
stamp locks. Owner, option A (2026-10-08): the staged ids are provisional
until one plain ``read --fleet F`` has read the rig; ``rig-`` is pinned from
its snapshot and ``unt-`` from the launch, the image Id the door read (a
caller's gate on that read, ``docker image inspect`` through the door's own
shims) and the cards' compute capability, before any unit is probed. A swap
(Round 8) is measured both ways: the partners stop and the strong rung starts
from F-strong's launch spec, then back.

Every door call goes through :func:`mcgyvr.wake.spawn_door`, the one seam a
product caller opens the door by, and here it is a fake rig: it keeps which
containers are up, answers a read by filing rows with the product's own
:func:`mcgyvr.fleet.read.record`, and runs the image gate with a stand-in
``docker`` on its PATH. The use case's task is the product's
``mcgyvr run`` seam, answered with a result file. Nothing reaches a machine.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import sample_fleet as fx
from tests import staged_plans as sp

IMAGE_ID = "sha256:" + "e" * 64
SNAPSHOT = {**fx.SNAPSHOT, "hostname": sp.RIG, "gpu_vram_mib": str(sp.CARD_TOTAL_MIB)}
WARM = 40.0


def _container_id(name: str) -> str:
    return (name.encode("utf-8").hex() * 4)[:12]


def _docker_stub(where: Path, *, answers: bool) -> Path:
    """A ``docker`` that answers ``image inspect`` with one image Id, or fails."""
    where.mkdir(parents=True, exist_ok=True)
    stub = where / "docker"
    body = f'echo "{IMAGE_ID}"' if answers else 'echo "no such image" >&2; exit 1'
    stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return where


@dataclass
class FakeRig:
    """The rig behind the door: containers up, reads filed, gates run."""

    bin_dir: Path
    serve_fails: bool = False
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    envs: list[dict[str, str]] = field(default_factory=list)
    up: set[str] = field(default_factory=set)
    pinned_at_probe: list[bool] = field(default_factory=list)

    def __call__(self, argv: Any, **kwargs: Any) -> int:
        from mcgyvr.serving.gatelib import DOOR_MODULE

        args = list(argv)
        env = dict(kwargs.get("env") or {})
        self.envs.append(env)
        verb = args[args.index(DOOR_MODULE) + 1 :]
        if verb[0] == "serve":
            return self._serve(verb[1], verb[2:])
        assert verb[0] == "read", args
        return self._read(verb[1:], Path(env["MCGYVR_CONFIG"]))

    def _serve(self, direction: str, rest: list[str]) -> int:
        parser = argparse.ArgumentParser()
        for flag in ("--mode", "--host", "--compose", "--suffix"):
            parser.add_argument(flag)
        parser.add_argument("--unit", action="append", default=[])
        opts = parser.parse_args(rest)
        compose = Path(opts.compose)
        self.calls.append(("serve", direction, opts.host, compose.name, *opts.unit))
        if self.serve_fails:
            return 1
        services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
        named = set(opts.unit) or {s["container_name"] for s in services.values()}
        if direction == "up":
            self.up |= named
        else:
            self.up -= named
        return 0

    def _read(self, rest: list[str], setup: Path) -> int:
        from mcgyvr.fleet import alerts, read

        parser = argparse.ArgumentParser()
        for flag in ("--mode", "--host", "--fleet", "--run-id", "--load", "--gates"):
            parser.add_argument(flag)
        parser.add_argument("--probe", nargs="+", default=[])
        opts = parser.parse_args(rest)
        self.calls.append(
            ("read", opts.host, opts.fleet, tuple(opts.probe), opts.load, bool(opts.gates))
        )
        doc = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
        if opts.probe:
            self.pinned_at_probe.append(
                all(not u["unit_id"].startswith("unt-provisional") for u in doc["units"].values())
                and not doc["rigs"][opts.host]["rig_id"].startswith("rig-provisional")
            )
        try:
            read.record(
                opts.host,
                self._reader(doc, opts.fleet, opts.host),
                run_id=opts.run_id,
                profile="dev",
                probe=tuple(opts.probe),
                measure=self._measure(doc),
                load=opts.load,
                fleet_name=opts.fleet,
                setup=setup,
            )
        except alerts.AlertError:
            return 1
        if opts.gates:
            self._gates(Path(opts.gates))
        return 0

    def _reader(self, doc: dict[str, Any], fleet: str, rig: str) -> str:
        lines = "".join(f"{k}={v}\n" for k, v in SNAPSHOT.items())
        for slot in doc["fleets"][fleet]["layout"][rig]:
            if slot is None:
                continue
            unit = doc["units"][slot[0]]
            if unit["container"] not in self.up:
                continue
            cid = _container_id(unit["container"])
            port = int(unit["address"].rsplit(":", 1)[1])
            page = base64.b64encode(fx.slots_page().encode()).decode()
            lines += f"container={unit['container']},{cid},mcgyvr,0\n"
            lines += f"gpu_app=4{port},{unit['room_mib'] - 300},{cid},llama-server\n"
            lines += f"status={port},{page}\n"
        return lines

    def _measure(self, doc: dict[str, Any]) -> Any:
        def measure(name: str, spec: str) -> str:
            unit = doc["units"][name]
            cid = _container_id(unit["container"])
            if json.loads(spec).get("mode") == "load":
                return json.dumps(
                    {
                        "load": {
                            "prompt_tokens": 100,
                            "max_tokens": 64,
                            "completed": 1,
                            "errors": [],
                            "started_at": "2026-10-05T10:00:05",
                            "finished_at": "2026-10-05T10:00:40",
                            "samples": [
                                f"gpu_app=1,{unit['room_mib'] - 200},{cid},llama-server\n"
                            ],
                            "restarts_before": "0",
                            "restarts_after": "0",
                            "after_page": fx.slots_page(),
                        }
                    }
                )
            return json.dumps(
                {
                    "figures": {"warm_decode_tok_s": WARM, "prefill_tok_s": 800.0},
                    "after_page": fx.slots_page(),
                }
            )

        return measure

    def _gates(self, listed: Path) -> None:
        gates = json.loads(listed.read_text(encoding="utf-8"))
        root = Path(gates["root"])
        for gate in gates["gates"]:
            assert gate["phase"] == "after", gate
            script = root / gate["path"]
            env = {**os.environ, "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}"}
            subprocess.run([sys.executable, str(script)], cwd=root, env=env, check=True)


def _result(argv: list[str], *, outcome: str, rung: str) -> int:
    where = Path(argv[argv.index("--result") + 1])
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(
        json.dumps(
            {
                "outcome": outcome,
                "attempts": [
                    {
                        "rung": rung,
                        "attempt": 1,
                        "verdict": outcome,
                        "detail": "" if outcome == "accepted" else "2 of 2 failed",
                        "findings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return 0 if outcome == "accepted" else 1


@pytest.fixture
def world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    """An invented rig with its rig file, a coding plan with a swap, and the door."""
    from mcgyvr import wake
    from mcgyvr.fleet import sampler
    from mcgyvr.serving import rigfile

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path / "root"))
    (tmp_path / "root").mkdir()
    plan, scans = sp.coding_plan(monkeypatch, capsys)
    rigfile.write(
        rigfile.Rig(
            rig=sp.RIG,
            read_at="2026-10-05T09:59:00Z",
            hostname=sp.RIG,
            machine_id=SNAPSHOT["os_machine_id"],
            cards=(rigfile.Card(index=0, name="Example Card S", total_mib=sp.CARD_TOTAL_MIB),),
            ram_total_gb=68.0,
            disk_path="/weights",
            disk_free_gb=500.0,
            docker=SNAPSHOT["docker"],
        )
    )
    rig = FakeRig(_docker_stub(tmp_path / "bin", answers=True))
    monkeypatch.setattr(wake, "spawn_door", rig)
    ran: list[list[str]] = []

    def run_contract(argv: list[str]) -> int:
        ran.append(list(argv))
        return _result(argv, outcome="accepted", rung=plan["ladder"][0])

    monkeypatch.setattr(sampler, "run_contract", run_contract)
    return {"plan": plan, "scans": scans, "rig": rig, "ran": ran, "folder": tmp_path / "sample"}


def _run(world: dict[str, Any]) -> Any:
    from mcgyvr.fleet import sampler

    return sampler.run(
        world["plan"], world["scans"], world["folder"], models=sp.library().models
    )


def test_a_green_sample_is_stamped_and_its_swap_is_both_fleets(
    world: dict[str, Any],
) -> None:
    from mcgyvr.fleet.roots import fleets_dir, live_file
    from mcgyvr.fleet.staged import strong_name

    done = _run(world)

    assert done.stamp.green, "\n".join(done.lines())
    plan = world["plan"]
    fleet, strong = plan["fleet"], strong_name(plan["fleet"])
    promoted = sorted(p.name.split("@")[0] for p in fleets_dir().iterdir())
    assert promoted == sorted([fleet, strong])
    live = json.loads(live_file().read_text(encoding="utf-8"))["fleet"]
    assert live.split("@")[0] == fleet
    (contract_run,) = world["ran"]
    assert contract_run[0] == "run" and "--config" in contract_run
    assert contract_run[contract_run.index("--config") + 1] == str(done.setup)


def test_every_door_call_is_the_sample_in_order_under_the_staged_setup(
    world: dict[str, Any],
) -> None:
    from mcgyvr.fleet.staged import strong_name

    done = _run(world)

    plan = world["plan"]
    rig: FakeRig = world["rig"]
    fleet, strong = plan["fleet"], strong_name(plan["fleet"])
    units = sp.units(plan)
    doc = yaml.safe_load((done.setup / "fleet.yaml").read_text(encoding="utf-8"))
    (sleeper,) = [n for n, u in units.items() if u["role"] == "sleeps-until-needed"]
    awake = [n for n in plan["ladder"] if n != sleeper]
    container = {n: doc["units"][n]["container"] for n in units}
    f_spec, s_spec = (f"compose.{sp.RIG}.{name}.yml" for name in (fleet, strong))

    assert rig.calls == [
        ("serve", "up", sp.RIG, f_spec),
        ("read", sp.RIG, fleet, (), None, True),
        *(
            (
                "read",
                sp.RIG,
                fleet,
                (name,),
                f"{units[name]['slots']}x{units[name]['ctx_per_slot']}",
                False,
            )
            for name in awake
        ),
        ("read", sp.RIG, fleet, (), None, False),
        ("serve", "down", sp.RIG, f_spec, *sorted(container[n] for n in awake)),
        ("serve", "up", sp.RIG, s_spec, container[sleeper]),
        (
            "read",
            sp.RIG,
            strong,
            (sleeper,),
            f"{units[sleeper]['slots']}x{units[sleeper]['ctx_per_slot']}",
            False,
        ),
        ("read", sp.RIG, strong, (), None, False),
        ("serve", "down", sp.RIG, s_spec, container[sleeper]),
        ("serve", "up", sp.RIG, f_spec, *sorted(container[n] for n in awake)),
    ]
    assert all(env.get("MCGYVR_CONFIG") == str(done.setup) for env in rig.envs)
    assert not any(k.startswith("RUN_") for env in rig.envs for k in env), (
        "the door refuses a RUN_ name it did not mint"
    )
    assert rig.pinned_at_probe and all(rig.pinned_at_probe), (
        "every unit is probed under its pinned id, never a provisional one"
    )


def test_the_ids_are_pinned_from_what_the_first_read_read(
    world: dict[str, Any],
) -> None:
    from mcgyvr.fleet import ids

    done = _run(world)

    doc = yaml.safe_load((done.setup / "fleet.yaml").read_text(encoding="utf-8"))
    assert doc["rigs"][sp.RIG]["rig_id"] == ids.rig_id(SNAPSHOT)
    for unit in doc["units"].values():
        launch = unit["launch"]
        assert unit["unit_id"] == ids.digest(
            "unt-",
            {
                "engine": unit["engine"],
                "image": IMAGE_ID,
                "weights_sha256": launch["weights_sha256"],
                "argv": launch["argv"],
                "env": launch["env"],
                "gpu_cc": [SNAPSHOT["gpu_cc"]],
            },
        )


def test_a_unit_that_does_not_start_is_no_stamp_and_nothing_is_read(
    world: dict[str, Any],
) -> None:
    from mcgyvr.fleet.roots import fleets_dir

    world["rig"].serve_fails = True

    done = _run(world)

    assert not done.stamp.green
    said = "\n".join(done.lines())
    assert "serve up" in said and sp.RIG in said, said
    assert "serve down" in said, "the units it may have left up are named"
    assert [c for c in world["rig"].calls if c[0] == "read"] == []
    assert not fleets_dir().exists() or list(fleets_dir().iterdir()) == []


def test_an_image_the_door_could_not_read_is_no_stamp_and_no_unit_is_probed(
    world: dict[str, Any], tmp_path: Path
) -> None:
    world["rig"].bin_dir = _docker_stub(tmp_path / "bin-broken", answers=False)

    done = _run(world)

    assert not done.stamp.green
    said = "\n".join(done.lines())
    assert "image" in said, said
    assert not [c for c in world["rig"].calls if c[0] == "read" and c[3]], (
        "nothing is probed under a provisional id"
    )


def test_a_coding_task_the_gate_rejects_is_no_stamp_by_the_gates_reason(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sampler

    plan = world["plan"]
    monkeypatch.setattr(
        sampler,
        "run_contract",
        lambda argv: _result(argv, outcome="ladder_spent", rung=plan["ladder"][-1]),
    )

    done = _run(world)

    assert not done.stamp.green
    said = "\n".join(done.lines())
    assert "gate" in said and "ladder_spent" in said, said


def test_the_image_gate_reads_each_image_id_through_docker(tmp_path: Path) -> None:
    from mcgyvr.fleet import sampler

    listed = sampler.image_gate(tmp_path / "gate", ["example/llama:tag"])
    gates = json.loads(listed.read_text(encoding="utf-8"))
    (gate,) = gates["gates"]
    assert gate["phase"] == "after" and gate["why"]
    script = Path(gates["root"]) / gate["path"]
    assert os.access(script, os.X_OK)

    for answers, expected in ((True, {"example/llama:tag": IMAGE_ID}), (False, {})):
        stub = _docker_stub(tmp_path / f"bin-{answers}", answers=answers)
        env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        subprocess.run([sys.executable, str(script)], env=env, check=True)
        assert sampler.image_ids(tmp_path / "gate") == expected
