"""``python -m mcgyvr.serving.run serve up|down``: the door's second fixed
sequence, for a ladder that is started and left running.

The campaign run refuses a rig that is not idle and names any container the
step left, and a live ladder is exactly a set of containers left up on a busy
rig. So ``serve`` is a second sequence in the same door — the same gates
that make a rig the declared rig (1, 2, 3, 5), the step, then 7 and 8 —
with gate 2 and gate 7 reading the direction: ``up`` opens on an idle rig and
expects every container the door read from the compose file, ``down`` opens
on the serving rig and expects an empty daemon. Nothing else is different,
nothing is skippable, and the operator never spells a container name: the
door reads them from the file ``mcgyvr emit`` wrote.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from mcgyvr.serving import run
from tests import onedoor
from tests.onedoor import STRAY_NAME

UNITS = ("mcgyvr-srv1-a-8001", "mcgyvr-srv1-b-8002")


def compose_file(root: Path, names: tuple[str, ...] = UNITS) -> Path:
    services = {
        f"svc{i}": {
            "image": "llamacpp:b10644-L3",
            "container_name": name,
            "command": ["--model", "/models/x.gguf", "--port", str(8001 + i)],
            "network_mode": "host",
        }
        for i, name in enumerate(names)
    }
    path = root / "compose.srv1.yml"
    path.write_text(yaml.safe_dump({"services": services}), encoding="utf-8")
    return path


def busy_rig(root: Path) -> None:
    onedoor.rig_stub(
        onedoor.stubs_dir(root),
        "srv1",
        containers="c0ffee000011;c0ffee000012",
        gpu_procs="4242,llama-server,5584MiB",
    )


# --- the shape ---------------------------------------------------------------


def test_serve_is_a_fixed_sequence_of_the_doors_own_gates() -> None:
    assert [e.script for e in run.SERVE_SEQUENCE] == [
        "01-round.py",
        "02-rig.py",
        "03-image.py",
        "05-envelope.py",
        "06-step.py",
    ]
    assert run.SERVE_ALWAYS == run.ALWAYS
    for step in run.SERVE_STEPS.values():
        assert step.is_file(), step


def test_serve_help_offers_no_way_past_a_gate_and_takes_no_model(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    result = onedoor.serve_door(root, "--help", tmp_path / "none")
    text = result.stdout + result.stderr
    for forbidden in ("--skip", "--no-gate", "--force", "--model"):
        assert forbidden not in text, forbidden


def test_serve_up_without_a_compose_file_is_refused_before_any_gate(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    result = onedoor.serve_door(root, "up", tmp_path / "absent.yml")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "--compose" in result.stderr
    assert onedoor.ssh_log(root) == [], "a rig was read before the refusal"


def test_a_compose_service_without_a_container_name_is_refused_before_any_gate(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    path = root / "compose.srv1.yml"
    path.write_text(
        yaml.safe_dump({"services": {"a": {"command": ["--port", "8001"]}}}),
        encoding="utf-8",
    )
    result = onedoor.serve_door(root, "up", path)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "container_name" in result.stderr
    assert onedoor.ssh_log(root) == []


# --- up ------------------------------------------------------------------------


def test_serve_up_brings_the_file_up_asks_each_unit_and_leaves_it_running(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    # The daemon lists the units once compose has brought them up.
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    result = onedoor.serve_door(root, "up", compose)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "not green" not in result.stderr

    log = onedoor.docker_log(root)
    assert any(
        line.startswith(f"compose -f {compose} -p mcgyvr up -d") for line in log
    ), log
    asked = [line for line in onedoor.ssh_log(root) if "v1/models" in line]
    assert any(":8001/" in line for line in asked) and any(
        ":8002/" in line for line in asked
    ), asked

    record = json.loads(
        (onedoor.envelope(root, "live-srv1") / "serve-up.json").read_text()
    )
    assert record["mode"] == "up" and record["host"] == "srv1"
    assert [u["container"] for u in record["units"]] == list(UNITS)
    assert all(u["healthy"] for u in record["units"])
    assert record["units"][0]["models"] == ["stub-model"]
    assert record["card_after"] == {"used_mib": 3374, "free_mib": 5727} or (
        "used_mib" in record["card_after"]
    )
    assert record["compose"] == compose.read_text(encoding="utf-8")


def test_serve_up_names_a_container_it_did_not_declare(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    stray = tmp_path / "stray-now"
    stray.touch()
    onedoor.docker_stub(onedoor.stubs_dir(root), stray_flag=stray)
    result = onedoor.serve_door(root, "up", compose)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert STRAY_NAME in result.stderr
    for name in UNITS:
        assert name not in result.stderr.split("NOT named")[-1], result.stderr


def test_serve_up_whose_unit_never_came_up_is_exit_1_and_says_which(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    # Only the first unit is listed by the daemon after compose up.
    onedoor.serving(onedoor.stubs_dir(root), UNITS[:1])
    result = onedoor.serve_door(root, "up", compose)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert UNITS[1] in result.stderr


def test_serve_up_still_refuses_a_busy_rig(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    busy_rig(root)
    result = onedoor.serve_door(root, "up", compose)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "not idle" in result.stderr
    assert not any(line.startswith("compose") for line in onedoor.docker_log(root))


# --- down ----------------------------------------------------------------------


def test_serve_down_opens_on_the_serving_rig_and_requires_nothing_left(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS, already_up=True)
    result = onedoor.serve_door(root, "down", compose)
    assert result.returncode == 0, (result.stdout, result.stderr)
    log = onedoor.docker_log(root)
    assert any(
        line.startswith(f"compose -f {compose} -p mcgyvr down") for line in log
    ), log
    record = json.loads(
        (onedoor.envelope(root, "live-srv1") / "serve-down.json").read_text()
    )
    assert record["mode"] == "down" and record["remaining"] == []


def test_serve_down_that_leaves_a_unit_up_is_not_green_and_names_it(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS, already_up=True, sticks=True)
    result = onedoor.serve_door(root, "down", compose)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert UNITS[0] in result.stderr and UNITS[1] in result.stderr


def test_up_then_down_on_one_day_file_under_one_envelope(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    up = onedoor.serve_door(root, "up", compose)
    assert up.returncode == 0, (up.stdout, up.stderr)
    down = onedoor.serve_door(root, "down", compose)
    assert down.returncode == 0, (down.stdout, down.stderr)
    envelope = onedoor.envelope(root, "live-srv1")
    assert (envelope / "serve-up.json").is_file()
    assert (envelope / "serve-down.json").is_file()
