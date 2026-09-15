"""lock-fleets' steps start only the launch fleet.yaml and its digests name.

``_unit.sh`` and ``_move.sh`` ask ``tools/runs/campaigns/lock-fleets/lockfleets.py``
for every fact they act on, and refuse, before a container starts, a unit or a
move that is not the one the fleet files name, or a door run sized for another
launch. A move's stopwatch is one rendered shell that runs on the rig, with the
docker verbs in its text for the shim's spend check. Outside the door neither
step reaches a rig; under a door that refuses, the step's artifact still says why.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving.gatelib import ssh_spends
from tests import onedoor
from tests.lockfleets_window import (
    REPO,
    fleet_doc,
    make_tree,
    steps_module,
)
from tests.test_one_door import (
    _hand_set,
    _outside,
    _reached,
    _refused_naming_the_door,
    _stubs,
)

CAMPAIGN = REPO / "tools" / "runs" / "campaigns" / "lock-fleets"


def _door(**override: str) -> Any:
    values = {
        "host": "alpha",
        "run_id": "2026-09-16-lock-fleets-x",
        "model": "/models/a_pair.gguf",
        "parallel": "2",
        "ctx_per_slot": "4096",
        "ubatch": "512",
        **override,
    }
    return steps_module().Door(**values)


def _refusals(root: Path, name: str = "a_pair", **door: str) -> list[str]:
    lf = steps_module()
    _unit, refused = lf.unit_refusals(root, lf.load(root), name, _door(**door))
    return list(refused)


def test_a_unit_as_fleet_yaml_and_its_digests_state_it_is_not_refused(
    tmp_path: Path,
) -> None:
    assert _refusals(make_tree(tmp_path)) == []


@pytest.mark.parametrize(
    ("name", "door", "said"),
    [
        ("no_such_unit", {}, "no_such_unit is not a unit of fleet.yaml"),
        ("a_pair", {"host": "beta"}, "is placed on alpha, and this run is on beta"),
        ("b_small", {"host": "beta"}, "b_small is vllm"),
        (
            "a_pair",
            {"model": "/models/a_solo.gguf"},
            "--model /models/a_solo.gguf is not",
        ),
        ("a_pair", {"parallel": "1"}, "--parallel 1 is not a_pair's --parallel 2"),
        (
            "a_pair",
            {"ctx_per_slot": "8192"},
            "--ctx-per-slot 8192 is not a_pair's -c/np 4096",
        ),
        ("a_pair", {"ubatch": "1024"}, "--ubatch 1024 is not a_pair's -ub 512"),
    ],
)
def test_a_unit_the_door_was_not_opened_for_is_refused_by_name(
    tmp_path: Path, name: str, door: dict[str, str], said: str
) -> None:
    refused = _refusals(make_tree(tmp_path), name, **door)
    assert any(said in why for why in refused), refused


@pytest.mark.parametrize(
    ("key", "said"), [("argv", "launch.argv is not"), ("env", "launch.env is not")]
)
def test_a_launch_that_is_not_what_its_digests_hashed_is_refused(
    tmp_path: Path, key: str, said: str
) -> None:
    root = make_tree(tmp_path)
    path = root / "fleet-setup" / "digests-alpha.json"
    doc = json.loads(path.read_text("utf-8"))
    fields = doc["units"]["a_pair"]["fields"]
    fields[key] = (
        [*fields[key], "--jinja"] if key == "argv" else {**fields[key], "X": "1"}
    )
    path.write_text(json.dumps(doc), "utf-8")
    assert any(said in why for why in _refusals(root)), _refusals(root)


def test_a_cache_that_is_not_a_whole_multiple_of_its_slots_is_refused(
    tmp_path: Path,
) -> None:
    fleet = fleet_doc()
    argv = fleet["units"]["a_pair"]["launch"]["argv"]
    argv[argv.index("--parallel") + 1] = "3"
    root = make_tree(tmp_path, fleet=fleet)
    assert any(
        "not a whole multiple of -np" in why for why in _refusals(root, parallel="3")
    )


def test_the_recorded_image_is_read_under_either_spelling(tmp_path: Path) -> None:
    lf = steps_module()
    root = make_tree(tmp_path)
    alpha = lf.recorded(root, "alpha", "a_pair")
    beta = lf.recorded(root, "beta", "b_small")
    assert "image_id" in alpha and "image" in beta
    assert lf.recorded_image(alpha) == "sha256:" + "a" * 64
    assert lf.recorded_image(beta) == "sha256:" + "f" * 64
    assert lf.digest_part("vllm/vllm-openai@sha256:" + "f" * 64) == "sha256:" + "f" * 64


def _move_facts(
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    compose: str,
    **env: str,
) -> dict[str, str]:
    values = {
        "RUN_HOST": "beta",
        "RUN_ID": "2026-09-16-lock-fleets-m",
        "RUN_MODEL": "/models/b_big.gguf",
        "RUN_PARALLEL": "4",
        "RUN_CTX_PER_SLOT": "4096",
        "RUN_UBATCH": "512",
        **env,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    said = steps_module()._move_facts(root, state, "beta", "one", "two", compose)
    return dict(line.split("=", 1) for line in shlex.split(said))


def test_a_move_with_the_emitted_compose_file_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf = steps_module()
    root = make_tree(tmp_path)
    compose = tmp_path / "compose.beta.two.yml"
    compose.write_bytes(lf.emitted_compose(lf.load(root), "beta", "two"))
    facts = _move_facts(root, tmp_path, monkeypatch, str(compose))
    assert facts["MOVE_REFUSED"] == ""
    assert (facts["MOVE_SOURCE_KIND"], facts["MOVE_TARGET_KIND"]) == ("run", "compose")
    assert facts["MOVE_ALL_NAMES"].split() == [
        "2026-09-16-lock-fleets-m-b_big",
        "mcgyvr-beta-b_small",
        "mcgyvr-beta-b_mid",
    ]


@pytest.mark.parametrize(
    ("compose", "env", "said"),
    [
        ("", {}, "no compose file was given"),
        ("edited", {}, "is not byte-identical to mcgyvr.emit.emit_locked's file"),
        (
            "emitted",
            {"RUN_MODEL": "/models/a_solo.gguf"},
            "is no llama.cpp unit of this move",
        ),
        (
            "emitted",
            {"RUN_HOST": "alpha"},
            "the move is on beta, and this run is on alpha",
        ),
    ],
)
def test_a_move_the_fleet_files_do_not_name_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    compose: str,
    env: dict[str, str],
    said: str,
) -> None:
    lf = steps_module()
    root = make_tree(tmp_path)
    path = tmp_path / "compose.beta.two.yml"
    text = lf.emitted_compose(lf.load(root), "beta", "two")
    path.write_bytes(text + b"# edited\n" if compose == "edited" else text)
    facts = _move_facts(
        root, tmp_path, monkeypatch, str(path) if compose else "", **env
    )
    assert said in facts["MOVE_REFUSED"], facts["MOVE_REFUSED"]


def test_a_switch_that_is_not_listed_or_moves_nothing_is_refused(
    tmp_path: Path,
) -> None:
    lf = steps_module()
    fleet = fleet_doc()
    fleet["fleets"]["one"]["next"] = []
    with pytest.raises(lf.StepRefusedError, match="does not list two"):
        lf.move_sides(fleet, "beta", "one", "two")
    fleet = fleet_doc()
    fleet["fleets"]["two"]["layout"]["alpha"] = [["a_solo", "awake"]]
    with pytest.raises(lf.StepRefusedError, match="moves nothing on alpha"):
        lf.move_sides(fleet, "alpha", "one", "two")


def test_the_stopwatch_stamps_parse_into_downtime_and_wake() -> None:
    lf = steps_module()
    text = (
        "### START uptime_since=x run_id=r\n"
        "t0 100.000000001\nrc_stop 0\nrc_drop 0\nt1 101.5\nt_compose 104\n"
        "t2 b_mid 190.25\nt2 b_small 150.5\nrc_compose 0\nsomething else\n"
    )
    stamps = lf.parse_stamps(text)
    assert stamps["rc"] == {"rc_stop": 0, "rc_drop": 0, "rc_compose": 0}
    assert stamps["unparsed"] == ["something else"]
    downtime, wake = lf.move_times(stamps, ["b_small", "b_mid"])
    assert downtime == 90.25
    assert wake == {"b_small": 49.0, "b_mid": 88.75}
    assert lf.move_times(stamps, ["b_small", "b_big"]) == (None, {"b_small": 49.0})


def _template(name: str) -> str:
    text = (CAMPAIGN / "_move.sh").read_text("utf-8")
    match = re.search(rf"^{name}='(.*?)^'$", text, re.S | re.M)
    assert match is not None, name
    return match.group(1)


VALUES = {
    "RIG_DIR": '"$HOME"/mcgyvr-relock',
    "RIG_FILE": '"$HOME"/mcgyvr-relock/r.move',
    "RUN_ID": "r",
    "PROJECT": "mcgyvr",
    "SOURCE_NAMES": "r-a_solo",
    "ALL_NAMES": "r-a_solo r-a_pair",
    "SOURCE_POLLS": "a_solo:llama.cpp:8080",
    "TARGET_POLLS": "b_small:vllm:8001 b_mid:vllm:8002",
    "SOURCE_RUN_ARGS": "--name r-a_solo --gpus all --network host img --model /m.gguf",
    "TARGET_RUN_ARGS": "--name r-a_pair --gpus all --network host img --model /n.gguf",
}


@pytest.mark.parametrize(
    "name", ["SOURCE_RUN", "SOURCE_COMPOSE", "TIMED_RUN", "TIMED_COMPOSE"]
)
def test_the_rigs_shell_names_its_docker_verbs_and_parses(name: str) -> None:
    lf = steps_module()
    script = lf.render(_template("PRELUDE") + _template(name), VALUES)
    assert "@" not in script.replace('"$HOME"', "")
    assert ssh_spends([script]), script
    done = subprocess.run(
        ["sh", "-n"], input=script, text=True, capture_output=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "http://127.0.0.1:$3/health" in script and "curl -sf -m 5" in script


def test_the_timed_shell_stamps_in_the_ruled_order() -> None:
    lf = steps_module()
    run = lf.render(_template("TIMED_RUN"), VALUES)
    order = [
        "st t0",
        "docker rm -f",
        "drop_caches",
        "rc drop",
        "run -d --name r-a_pair",
        "st t1",
        "poll",
    ]
    assert [run.index(word) for word in order] == sorted(
        run.index(word) for word in order
    )
    compose = lf.render(_template("TIMED_COMPOSE"), VALUES)
    order = [
        "st t0",
        "drop_caches",
        "st t1",
        'poll "$p" </dev/null &',
        "docker compose -p mcgyvr -f - up -d",
        "st t_compose",
        "wait",
    ]
    assert [compose.index(word) for word in order] == sorted(
        compose.index(w) for w in order
    )
    with pytest.raises(lf.StepRefusedError, match="@NOPE@"):
        lf.render("echo @NOPE@", VALUES)


def test_a_move_artifact_is_written_whole_from_the_stamps_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf = steps_module()
    monkeypatch.setenv("RUN_ID", "r")
    monkeypatch.setenv("RUN_HOST", "beta")
    state = tmp_path / "state"
    state.mkdir()
    compose = tmp_path / "c.yml"
    compose.write_text("services: {}\n")
    (state / "move.json").write_text(
        json.dumps({"rig": "beta", "to_units": ["b_big"], "compose": str(compose)})
    )
    (state / "timed.out").write_text("t0 1\n")
    (state / "readback").write_text(
        "### START run_id=r\nt0 10\nt1 12\nt2 b_big 70\nrc_run 0\n"
    )
    (state / "ssh_exit").write_text("0\n")
    lf.write_move(
        state,
        tmp_path / "m.json",
        lf.Door.from_env({"RUN_ID": "r", "RUN_HOST": "beta"}),
    )
    doc = json.loads((tmp_path / "m.json").read_text())
    assert doc["schema"] == "lock-fleets-move/1"
    assert (doc["downtime_s"], doc["wake_s"], doc["ssh_exit"]) == (
        60.0,
        {"b_big": 58.0},
        0,
    )
    assert doc["stamp_text"].startswith("### START")
    assert len(doc["compose_sha256"]) == 64


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", str(CAMPAIGN / "_unit.sh"), "x.json", "srv1_deepseek"],
        ["bash", str(CAMPAIGN / "_move.sh"), "x.json", "srv1", "b-small", "b-big"],
        [
            "bash",
            str(
                CAMPAIGN
                / "rig-id-relock"
                / "01-rig-id-relock-srv1-c1-srv1_35b_maxctx.sh"
            ),
        ],
    ],
    ids=["unit", "move", "wrapper"],
)
def test_a_step_with_every_run_variable_typed_in_is_refused_outside_the_door(
    tmp_path: Path, argv: list[str]
) -> None:
    stubs = _stubs(tmp_path / "stubs")
    done = _outside(argv, _hand_set(stubs, tmp_path))
    _refused_naming_the_door(done, stubs, argv[1])


def test_a_refused_unit_writes_its_artifact_and_reaches_no_daemon(
    tmp_path: Path,
) -> None:
    stubs = _stubs(tmp_path / "stubs")
    env = _hand_set(stubs, tmp_path)
    door = onedoor.fake_door(tmp_path)
    done = subprocess.run(
        [
            sys.executable,
            str(door),
            "bash",
            str(CAMPAIGN / "_unit.sh"),
            "refused.json",
            "no_such_unit",
        ],
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 2, (done.stdout, done.stderr)
    artifact = json.loads((Path(env["RUN_OUT_DIR"]) / "refused.json").read_text())
    assert artifact["schema"] == "lock-fleets-unit/1"
    assert "no_such_unit is not a unit of fleet.yaml" in artifact["failure"]
    assert _reached(stubs) == []
