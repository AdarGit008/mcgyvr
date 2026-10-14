"""``mcgyvr emit`` stamps the launch it resolves back into ``fleet.yaml``.

A locked fleet is emitted from what its units state, and live admission matches
a running container to a unit by the container name the unit states. So the
launch ``emit`` computes for a dev config must be written beside the compose
file it writes: a compose file and a fleet.yaml that disagree are the exact
drift the emit layer exists to prevent. These tests hold that the two are
byte-identical, that the write is non-destructive and idempotent, and that a
unit stamped this way renders as a locked unit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.config import FLEET_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.emit import (
    _locked_service,
    render_compose,
    resolved_launch,
)
from mcgyvr.exits import Exit
from mcgyvr.fleet.files import load_fleet
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, unit_for

WINDOW = 4096
SMALL = ModelSpec(
    name="qwen2.5-coder-3b",
    vram_gb=2.4,
    ram_gb=0.0,
    disk_gb=2.1,
    kv_cache_dtype_k="f16",
    kv_cache_dtype_v="f16",
)
VLLM_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
HF_CACHE = "/home/someone/.cache/huggingface"
VLLM_SPEC = ModelSpec(
    name=VLLM_MODEL,
    vram_gb=3.49,
    ram_gb=0.0,
    disk_gb=1.95,
    hf_cache=HF_CACHE,
    serve_args=("--gpu-memory-utilization", "0.33"),
    kv_cache_dtype_k="auto",
)


def machine(host: str, *, vram_mib: int) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=48.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def service_of(document: str) -> dict[str, Any]:
    return next(iter(yaml.safe_load(document)["services"].values()))


def llama_unit() -> Any:
    return unit_for(
        machine("box1", vram_mib=6144),
        SMALL,
        engine="llama.cpp",
        width=8,
        ctx_per_slot=WINDOW,
    )


def vllm_unit() -> Any:
    return unit_for(
        machine("box2", vram_mib=12288),
        VLLM_SPEC,
        engine="vllm",
        width=8,
        port=8001,
        ctx_per_slot=WINDOW,
    )


def test_resolved_launch_is_the_compose_service_for_a_llama_cpp_unit() -> None:
    unit = llama_unit()
    service = service_of(render_compose(unit))

    resolved = resolved_launch(unit)

    assert resolved["engine"] == "llama.cpp"
    assert resolved["image"] == service["image"]
    assert resolved["container"] == service["container_name"]
    assert resolved["launch"]["argv"] == service["command"]
    assert resolved["launch"]["env"] == service["environment"]
    assert resolved["launch"]["volumes"] == service["volumes"]
    assert "hf_cache" not in resolved


def test_resolved_launch_states_hf_cache_not_volumes_for_a_vllm_unit() -> None:
    unit = vllm_unit()
    service = service_of(render_compose(unit))

    resolved = resolved_launch(unit)

    assert resolved["engine"] == "vllm"
    assert resolved["image"] == service["image"]
    assert resolved["container"] == service["container_name"]
    assert resolved["launch"]["argv"] == service["command"]
    assert resolved["launch"]["env"] == service["environment"]
    assert resolved["hf_cache"] == str(unit.weights_dir)
    assert "volumes" not in resolved["launch"]


def test_a_unit_stamped_by_resolved_launch_renders_as_locked() -> None:
    unit = llama_unit()
    resolved = resolved_launch(unit)
    block = {"unit_id": "unt-" + "e" * 64, **resolved}

    service = _locked_service("local_qwen2.5-coder-3b", block)

    assert service["container_name"] == resolved["container"]
    assert service["command"] == resolved["launch"]["argv"]
    assert service["environment"] == resolved["launch"]["env"]
    assert service["volumes"] == resolved["launch"]["volumes"]
    assert service["image"] == resolved["image"]


def test_a_stamped_vllm_unit_renders_as_locked_too() -> None:
    unit = vllm_unit()
    resolved = resolved_launch(unit)
    block = {"unit_id": "unt-" + "3" * 64, **resolved}

    service = _locked_service("local_vllm", block)

    assert service["container_name"] == resolved["container"]
    assert service["command"] == resolved["launch"]["argv"]
    assert service["volumes"] == [f"{resolved['hf_cache']}:/root/.cache/huggingface:ro"]
    assert service["ipc"] == "host"


def _config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A scanned rig and a directory setup (fleet.yaml + policy.yaml)."""
    host = "localhost"
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / f"{host}.json").write_text(
        machine(host, vram_mib=12288).to_json(), encoding="utf-8"
    )
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))

    config = tmp_path / "config"
    config.mkdir()
    (config / FLEET_FILENAME).write_text(
        "profile: dev\n"
        "units:\n"
        "  local_qwen2.5-coder-3b:\n"
        "    address: http://localhost:8080\n"
        "    model: 'qwen2.5-coder:3b'\n"
        "    rig: localhost\n"
        "    width: 2\n",
        encoding="utf-8",
    )
    (config / "policy.yaml").write_text(
        "ladder:\n- local_qwen2.5-coder-3b\n", encoding="utf-8"
    )
    out = tmp_path / "compose"
    return config, out


def _emit(config: Path, out: Path) -> int:
    return main(
        [
            "emit",
            "--config",
            str(config),
            "--out",
            str(out),
            "--ctx-per-slot",
            str(WINDOW),
        ]
    )


def test_dev_emit_stamps_fleet_yaml_with_the_compose_launch_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = _config_dir(tmp_path, monkeypatch)

    assert _emit(config, out) == Exit.OK, capsys.readouterr().err
    fleet_path = config / FLEET_FILENAME
    first = fleet_path.read_text(encoding="utf-8")
    fleet = load_fleet(first)
    block = fleet["units"]["local_qwen2.5-coder-3b"]

    assert block["engine"] == "llama.cpp"
    assert block["image"]
    assert block["container"]
    assert block["launch"]["argv"]
    assert block["launch"]["env"]
    assert block["launch"]["volumes"]

    # The stamp and the compose file the same call wrote must agree byte for
    # byte on every fact a locked unit states.
    service = service_of((out / "compose.localhost.yml").read_text(encoding="utf-8"))
    assert block["container"] == service["container_name"]
    assert block["image"] == service["image"]
    assert block["launch"]["argv"] == service["command"]
    assert block["launch"]["env"] == service["environment"]
    assert block["launch"]["volumes"] == service["volumes"]

    # The loader accepts the result as a run config.
    assert load_config(config) is not None

    # Re-running is idempotent: nothing already stated is rewritten differently.
    capsys.readouterr()
    assert _emit(config, out) == Exit.OK, capsys.readouterr().err
    assert fleet_path.read_text(encoding="utf-8") == first


def test_dev_emit_fills_only_what_a_unit_does_not_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = _config_dir(tmp_path, monkeypatch)
    fleet_path = config / FLEET_FILENAME
    fleet_path.write_text(
        "profile: dev\n"
        "units:\n"
        "  local_qwen2.5-coder-3b:\n"
        "    address: http://localhost:8080\n"
        "    model: 'qwen2.5-coder:3b'\n"
        "    rig: localhost\n"
        "    width: 2\n"
        "    image: operator/image:tag\n"
        "    launch:\n"
        "      vram_gb: 2.4\n"
        "      disk_gb: 2.1\n"
        "      kv_cache_dtype_k: f16\n"
        "      kv_cache_dtype_v: f16\n"
        "      argv: ['--parallel', '4', '--port', '8080']\n",
        encoding="utf-8",
    )

    assert _emit(config, out) == Exit.OK, capsys.readouterr().err
    block = load_fleet(fleet_path.read_text(encoding="utf-8"))["units"][
        "local_qwen2.5-coder-3b"
    ]

    assert block["image"] == "operator/image:tag"
    assert block["launch"]["argv"] == ["--parallel", "4", "--port", "8080"]
    # Everything else was missing and is filled in.
    assert block["engine"] == "llama.cpp"
    assert block["container"]
    assert block["launch"]["env"] == {"LLAMA_ARG_HOST": "0.0.0.0"}
    assert block["launch"]["volumes"]


def test_a_stamped_unit_that_states_nothing_else_is_not_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stamp runs on the dev path, so it never manufactures a unit_id."""
    config, out = _config_dir(tmp_path, monkeypatch)

    assert _emit(config, out) == Exit.OK, capsys.readouterr().err
    fleet = load_fleet((config / FLEET_FILENAME).read_text(encoding="utf-8"))

    assert all("unit_id" not in block for block in fleet["units"].values())


def test_check_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = _config_dir(tmp_path, monkeypatch)
    fleet_path = config / FLEET_FILENAME
    before = fleet_path.read_text(encoding="utf-8")

    code = main(
        [
            "emit",
            "--check",
            "--config",
            str(config),
            "--out",
            str(out),
            "--ctx-per-slot",
            str(WINDOW),
        ]
    )
    assert code == Exit.MISMATCH, capsys.readouterr()
    assert fleet_path.read_text(encoding="utf-8") == before
