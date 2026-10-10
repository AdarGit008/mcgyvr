"""Fixes 1, 2, 4, 5 and 7, held as behaviour rather than as a changelog note.

Each fix gets one focused test here, so the setup flow's entry points and the
scan's on-disk inventory stay pinned while the surrounding code moves.
"""

from __future__ import annotations

import argparse
import json
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


# --- Fix 7: the two hosted tiers climb cheapest first -----------------------


def test_deepseek_flash_is_below_deepseek_v4_pro(tmp_path: Path) -> None:
    initialize(
        tmp_path / "setup",
        detection=KEYLESS_RIG,
        api_units=(
            parse_api_unit(_api("deepseek-v4-pro")),
            parse_api_unit(_api("deepseek-flash")),
        ),
    )
    from mcgyvr.config import load as load_config

    config = load_config(tmp_path / "setup")
    api_rungs = [name for name in config.ladder.names if name.startswith("api_")]
    assert api_rungs == [
        "api_deepseek-flash",
        "api_deepseek-v4-pro",
    ]
