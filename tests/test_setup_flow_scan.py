"""Fixes 1, 2, 4, 5 and 7, held as behaviour rather than as a changelog note.

Each fix gets one focused test here, so the setup flow's entry points and the
scan's on-disk inventory stay pinned while the surrounding code moves.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from mcgyvr import cli, weights
from mcgyvr import scan as scan_module
from mcgyvr.initialize import InitResult, initialize, parse_api_unit
from mcgyvr.serving import rigfile
from tests.test_initialize import KEYLESS_RIG


def _api(model: str) -> str:
    return (
        f"model={model},address=https://api.deepseek.com,api_key_env=DEEPSEEK_API_KEY"
    )


# --- Fix 1: `local_pool` is the renamed `pool` command ----------------------


def test_local_pool_exists_and_init_is_gone() -> None:
    parser = cli.build_parser()
    sub = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    assert "local_pool" in sub.choices
    assert "init" not in sub.choices
    assert "setup" in sub.choices


# --- Fix 2: models on disk are part of the scan -----------------------------


def test_scan_inventories_models_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "coder-7b-Q4_K_M.gguf").write_bytes(b"\x00" * 1024)
    (store / "vision-encoder.safetensors").write_bytes(b"\x00" * 2048)

    monkeypatch.setattr(scan_module, "_free_bytes", lambda path: 512 * 1024**3)
    monkeypatch.setattr(scan_module, "_total_bytes", lambda path: 1024 * 1024**3)
    monkeypatch.setattr(scan_module, "_disk_device", lambda path: "nvme0n1")

    measured = scan_module.scan(weights_dir=store)
    names = {(m.name, m.quant) for m in measured.models_on_disk}
    assert ("coder-7b", "Q4_K_M") in names
    assert ("vision-encoder", None) in names

    document = json.loads(measured.to_json())
    assert "models_on_disk" in document
    assert document["disk"]["total_gb"] == 1024.0
    assert document["disk"]["device"] == "nvme0n1"


def test_rig_scan_carries_bandwidth_and_models_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "coder-7b-Q4_K_M.gguf").write_bytes(b"\x00" * 1024)

    monkeypatch.setattr(scan_module, "_free_bytes", lambda path: 512 * 1024**3)
    monkeypatch.setattr(scan_module, "_total_bytes", lambda path: 1024 * 1024**3)
    monkeypatch.setattr(scan_module, "_disk_device", lambda path: "nvme0n1")

    measured = scan_module.scan(weights_dir=store)
    rig = rigfile.from_scan("rig", measured)
    assert rig.bandwidth_gbps is not None
    assert [(m.name, m.quant) for m in rig.models_on_disk] == [("coder-7b", "Q4_K_M")]


# --- Fix 4: a download is reused when the same model is already on disk -----


def test_an_on_disk_model_is_reused_by_default(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "coder-7b-Q4_K_M.gguf").write_bytes(b"\x00" * 1024)

    hit = weights.existing_model(
        "coder-7b", quant="Q4_K_M", size_bytes=1024, roots=[store]
    )
    assert hit is not None
    assert hit[1] == "Q4_K_M"

    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return ""

    assert weights.reuse_or_download(
        "coder-7b",
        quant="Q4_K_M",
        size_bytes=1024,
        roots=[store],
        prompt=ask,
    )
    assert asked, "a reuse match is a question, not a silent overwrite"

    assert (
        weights.reuse_or_download(
            "coder-7b",
            quant="Q4_K_M",
            size_bytes=1024,
            roots=[store],
            prompt=lambda question: "n",
        )
        is False
    )


# --- Fix 5: `setup` is the one entry point ----------------------------------


def _setup_namespace(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "host": [],
        "api": [],
        "force": False,
        "priority": None,
        "profile": None,
        "use_case": None,
        "deployment": None,
        "jev": None,
        "mcorch": None,
        "window": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_setup_is_interactive_only_on_a_tty_without_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_stdin_isatty", lambda: True)
    assert cli._setup_is_interactive(_setup_namespace())
    assert not cli._setup_is_interactive(_setup_namespace(api=["model=m"]))
    assert not cli._setup_is_interactive(_setup_namespace(force=True))
    assert not cli._setup_is_interactive(_setup_namespace(use_case="chat"))

    monkeypatch.setattr(cli, "_stdin_isatty", lambda: False)
    assert not cli._setup_is_interactive(_setup_namespace())


def test_setup_routes_to_interactive_only_on_a_tty_without_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_stdin_isatty", lambda: True)
    interactive: list[Path] = []

    def fake_interactive(path: Path) -> int:
        interactive.append(path)
        return 0

    monkeypatch.setattr(cli, "_setup_interactive", fake_interactive)
    target = tmp_path / "setup"
    assert cli.main(["setup", str(target)]) == 0
    assert interactive == [target]


def test_setup_with_a_flag_keeps_the_flag_driven_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_stdin_isatty", lambda: True)
    interactive: list[Path] = []

    def fake_interactive(path: Path) -> int:
        interactive.append(path)
        return 0

    monkeypatch.setattr(cli, "_setup_interactive", fake_interactive)
    seen: list[Path] = []

    def fake_initialize(path: Path, **_: object) -> InitResult:
        seen.append(path)
        return InitResult(path=path, created=True, written=False)

    monkeypatch.setattr(cli, "initialize", fake_initialize)
    target = tmp_path / "setup"
    assert cli.main(["setup", "--api", _api("deepseek-flash"), str(target)]) == 0
    assert interactive == []
    assert seen == [target]


def test_interactive_download_is_gated_on_an_explicit_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date

    from mcgyvr.knowledge.record import ModelRecord, Number, Weights
    from mcgyvr.knowledge.store import Knowledge, Known

    def number() -> Number:
        return Number(
            value=1024, kind="fact", source="shipped:test", read_at=date(2026, 1, 1)
        )

    record = ModelRecord(
        model_id="m",
        quant="Q4",
        engines=("llama.cpp",),
        weights=Weights(
            repo="org/repo",
            revision="0" * 40,
            file="m.gguf",
            sha256="0" * 64,
        ),
        size_bytes=number(),
        context_length=number(),
        kv_bytes_per_token=number(),
        recurrent_bytes_per_slot=number(),
        scores=(),
    )
    monkeypatch.setattr(
        "mcgyvr.knowledge.store.offline",
        lambda: Knowledge(known=(Known(record=record, origin="shipped"),), skipped=()),
    )
    plans = {
        "rig": {
            "placement": {
                "model_id": "m",
                "quant": "Q4",
                "size_bytes": 1024,
                "engine": "llama.cpp",
            }
        }
    }

    asked: list[str] = []

    def ask_no(question: str) -> str:
        asked.append(question)
        return ""

    assert cli._setup_downloads(plans, {}, prompt=ask_no) == ()
    assert asked, "a download with no disk match is a question, not a default"

    asked.clear()
    got = cli._setup_downloads(plans, {}, prompt=lambda question: "y")
    assert len(got) == 1
    assert got[0][0] == "rig"
    assert got[0][1].model_id == "m"


def test_interactive_reuse_is_found_on_the_rigs_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date

    from mcgyvr.knowledge.record import ModelRecord, Number, Weights
    from mcgyvr.knowledge.store import Knowledge, Known

    def number() -> Number:
        return Number(
            value=1024, kind="fact", source="shipped:test", read_at=date(2026, 1, 1)
        )

    record = ModelRecord(
        model_id="org/coder-7b",
        quant="Q4_K_M",
        engines=("llama.cpp",),
        weights=Weights(
            repo="org/repo",
            revision="0" * 40,
            file="coder-7b-Q4_K_M.gguf",
            sha256="0" * 64,
        ),
        size_bytes=number(),
        context_length=number(),
        kv_bytes_per_token=number(),
        recurrent_bytes_per_slot=number(),
        scores=(),
    )
    monkeypatch.setattr(
        "mcgyvr.knowledge.store.offline",
        lambda: Knowledge(known=(Known(record=record, origin="shipped"),), skipped=()),
    )
    scan = scan_module.Scan(
        machine=scan_module.Machine(id="x", host="localhost", kernel="k"),
        models_on_disk=(
            scan_module.ModelOnDisk(
                name="coder-7b",
                quant="Q4_K_M",
                size_bytes=1024,
                path=Path("/x/coder-7b-Q4_K_M.gguf"),
            ),
        ),
    )
    plans = {
        "rig": {
            "placement": {
                "model_id": "org/coder-7b",
                "quant": "Q4_K_M",
                "size_bytes": 1024,
                "engine": "llama.cpp",
            }
        }
    }

    asked: list[str] = []

    def ask_default(question: str) -> str:
        asked.append(question)
        return ""

    # The default (an empty answer) reuses the on-disk model.
    assert cli._setup_downloads(plans, {"rig": scan}, prompt=ask_default) == ()
    assert asked, "a reuse match is a question, not a silent reuse"

    # A "no" downloads it instead.
    got = cli._setup_downloads(plans, {"rig": scan}, prompt=lambda question: "n")
    assert len(got) == 1
    assert got[0][1].model_id == "org/coder-7b"


def test_setup_fetch_and_start_go_through_the_door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Sequence
    from datetime import date

    from mcgyvr.knowledge.record import ModelRecord, Number, Weights
    from mcgyvr.serving import spec_name

    calls: list[tuple[str, ...]] = []

    def fake_spawn(argv: Sequence[str], **_: object) -> int:
        calls.append(tuple(argv))
        return 0

    monkeypatch.setattr("mcgyvr.wake.spawn_door", fake_spawn)

    def number() -> Number:
        return Number(
            value=1024, kind="fact", source="shipped:test", read_at=date(2026, 1, 1)
        )

    record = ModelRecord(
        model_id="org/coder-7b",
        quant="Q4_K_M",
        engines=("llama.cpp",),
        weights=Weights(
            repo="org/repo",
            revision="0" * 40,
            file="coder-7b-Q4_K_M.gguf",
            sha256="0" * 64,
        ),
        size_bytes=number(),
        context_length=number(),
        kv_bytes_per_token=number(),
        recurrent_bytes_per_slot=number(),
        scores=(),
    )

    cli._setup_fetch("srv1", record, tmp_path)
    argv = calls[-1]
    assert argv[:5] == (sys.executable, "-m", "mcgyvr.serving.run", "serve", "fetch")
    assert argv[argv.index("--host") + 1] == "srv1"
    assert "--weights" in argv and "--suffix" in argv

    scan = scan_module.Scan(
        machine=scan_module.Machine(id="x", host="localhost", kernel="k")
    )
    (tmp_path / spec_name("localhost")).write_text("services: {}", encoding="utf-8")
    cli._setup_start(["srv1"], {"srv1": scan}, tmp_path)
    argv = calls[-1]
    assert argv[:5] == (sys.executable, "-m", "mcgyvr.serving.run", "serve", "up")
    assert argv[argv.index("--host") + 1] == "srv1"
    assert "--compose" in argv and "--suffix" in argv


def test_setup_start_runs_the_door_against_the_bootstrap_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 6b points the door at the bootstrap fleet.yaml via MCGYVR_CONFIG."""
    from collections.abc import Sequence

    from mcgyvr import config as configlib
    from mcgyvr.serving import spec_name

    spawns: list[dict[str, object]] = []

    def fake_spawn(argv: Sequence[str], **kwargs: object) -> int:
        spawns.append(kwargs)
        return 0

    monkeypatch.setattr("mcgyvr.wake.spawn_door", fake_spawn)
    scan = scan_module.Scan(
        machine=scan_module.Machine(id="x", host="localhost", kernel="k")
    )
    (tmp_path / spec_name("localhost")).write_text("services: {}", encoding="utf-8")

    cli._setup_start(["srv1"], {"srv1": scan}, tmp_path)

    assert spawns and spawns[-1]["env"] is not None
    env = spawns[-1]["env"]
    assert isinstance(env, dict)
    assert env[configlib.CONFIG_PATH_ENV] == str(tmp_path / configlib.FLEET_FILENAME)


def test_setup_emit_declares_the_priced_context_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_setup_emit`` hands ``emit`` the window the placement was priced at."""
    seen: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        seen.append(list(argv))
        return 0

    monkeypatch.setattr(cli, "main", fake_main)
    cli._setup_emit(tmp_path / "setup", 32768)
    assert seen == [
        [
            "emit",
            "--config",
            str(tmp_path / "setup"),
            "--out",
            str(tmp_path / "setup"),
            "--ctx-per-slot",
            "32768",
        ]
    ]


def test_setup_context_window_collapses_differing_placements_to_the_smallest() -> None:
    """Differing rig windows collapse to the smallest, never an invention."""
    plans = {
        "srv1": {"placement": {"context_length": 32768}},
        "srv2": {"placement": {"context_length": 4096}},
        "srv3": {"placement": {"context_length": 65536}},
    }
    assert cli._setup_context_window(plans) == 4096


def test_setup_context_window_refuses_a_placement_without_a_window() -> None:
    """A placement with no declared window is refused, not guessed."""
    plans = {"srv1": {"placement": {"context_length": None}}}
    with pytest.raises(cli._SetupInteractiveError):
        cli._setup_context_window(plans)


def test_the_serve_step_runs_on_the_doors_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.serving as serving_pkg
    from tests._helpers import by_path

    gate6 = by_path(
        "six_step_for_test",
        Path(serving_pkg.__file__).parent / "gate-scripts" / "06-step.py",
    )
    step = tmp_path / "serve-fetch.py"
    step.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    step.chmod(0o755)

    seen: list[list[str]] = []

    def fake_run(argv: list[str]) -> int:
        seen.append(list(argv))
        return 0

    monkeypatch.setattr(gate6, "door_required", lambda what: None)
    monkeypatch.setattr(gate6, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["06-step.py", "--host", "srv1"])
    monkeypatch.setenv("RUN_STEP_FILE", str(step))
    monkeypatch.setenv("RUN_HOST", "srv1")
    monkeypatch.setenv("RUN_OUT_DIR", "/x")
    monkeypatch.setenv("RUN_ID", "r1")

    # A serve run's step is mcgyvr code: run it on the door's interpreter.
    monkeypatch.setenv("RUN_SERVE", "fetch")
    assert gate6.main() == 0
    assert seen == [[sys.executable, str(step), "--host", "srv1"]]

    # A caller's own --step keeps its shebang and runs as itself.
    monkeypatch.delenv("RUN_SERVE")
    seen.clear()
    assert gate6.main() == 0
    assert seen == [[str(step), "--host", "srv1"]]


def test_setup_writes_through_the_initialize_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def fake_initialize(path: Path, **_: object) -> InitResult:
        seen.append(path)
        return InitResult(path=path, created=True, written=False)

    monkeypatch.setattr(cli, "initialize", fake_initialize)
    target = tmp_path / "setup"
    assert cli.main(["setup", str(target)]) == 0
    assert seen == [target]


# --- Fix 7: the two hosted tiers climb cheapest first in declaration order --


def test_deepseek_flash_is_below_deepseek_v4_pro(tmp_path: Path) -> None:
    initialize(
        tmp_path / "setup",
        detection=KEYLESS_RIG,
        api_units=(
            parse_api_unit(_api("deepseek-flash")),
            parse_api_unit(_api("deepseek-v4-pro")),
        ),
    )
    from mcgyvr.config import load as load_config

    config = load_config(tmp_path / "setup")
    api_rungs = [name for name in config.ladder.names if name.startswith("api_")]
    assert api_rungs == [
        "api_deepseek-flash",
        "api_deepseek-v4-pro",
    ]
