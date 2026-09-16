"""A locked fleet is emitted as the launch its unit_ids were hashed over.

``mcgyvr emit`` on the stamped b-small setup (``~/.mcgyvr/config``, 2026-09-15)
refused before writing a file::

    refused: Qwen/Qwen2.5-Coder-3B-Instruct-AWQ: served by vLLM, which sizes its
    KV cache from the dtype the model declares, and nothing states one — set
    models.Qwen/Qwen2.5-Coder-3B-Instruct-AWQ.kv_cache_dtype_k

A ``fleet.yaml`` has no ``models`` block to state one in, so no locked fleet
could reach a compose file, and ``serve up`` takes nothing else. b-small went
live from a hand ``docker run``, and a door run cannot bring it back.

A locked unit was measured, approved and hashed. What emit owes it is that
launch, not a new one sized from a scan (owner, 2026-09-15):

* ``launch.argv`` and ``launch.env`` are the command and the environment,
  verbatim and in order: the argv and env its ``unit_id`` was hashed over.
* ``container`` is the container name. Gate 1 admits a live ``serve up`` by the
  container names the lock records, so a locked unit without one is refused.
* A llama.cpp unit mounts the ``launch.volumes`` it states. Its argv can name the
  blob by a container path (``/models/moe/…``), so the host side cannot be
  derived. A vLLM unit mounts its ``hf_cache`` at the image's cache path.
* One file per fleet per rig, ``compose.<host>.<fleet>.yml``, with services in
  layout order, each waiting for the one before it to be healthy.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.exits import Exit

REPO = Path(__file__).resolve().parent.parent
HF_CACHE = "/home/adaramir/.cache/huggingface"
MODELS_VOLUMES = [
    "/home/adaramir/models:/models:ro",
    "/home/adaramir/models:/home/adaramir/models:ro",
]

DEEPSEEK_ARGV = [
    "--model", "/home/adaramir/models/moe/deepseek-coder-v2-16b.gguf",
    "--n-cpu-moe", "19", "--parallel", "2", "--port", "8080",
    "-b", "512", "-ub", "512", "-c", "8192", "-fa", "on", "-ngl", "99", "-t", "6",
]  # fmt: skip
THREE_B_ARGV = [
    "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
    "--max-model-len", "4096", "--max-num-seqs", "8", "--port", "8001",
    "--gpu-memory-utilization", "0.30", "--kv-cache-memory-bytes", "1207959552",
]  # fmt: skip
SEVEN_B_ARGV = [
    "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
    "--max-model-len", "4096", "--max-num-seqs", "8", "--port", "8002",
    "--gpu-memory-utilization", "0.68", "--kv-cache-memory-bytes", "1879048192",
]  # fmt: skip
LLAMA_ENV = {"LLAMA_ARG_HOST": "0.0.0.0"}
VLLM_ENV = {"HF_HUB_OFFLINE": "1", "VLLM_LOGGING_LEVEL": "DEBUG"}
VLLM_IMAGE = (
    "vllm/vllm-openai@sha256:"
    "ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
)


def fleet() -> dict[str, Any]:
    """b-small as stamped: deepseek on srv1, the vLLM pair on srv2."""
    common = {"output_tokens": 2048, "request_timeout_s": 180}
    return {
        "profile": "live",
        "units": {
            "srv1_deepseek": {
                **common,
                "rig": "srv1",
                "address": "http://srv1:8080",
                "engine": "llama.cpp",
                "image": "llamacpp:b10644-L3",
                "model": "deepseek-coder-v2-16b",
                "width": 2,
                "window": 8192,
                "room_mib": 5458,
                "container": "mcgyvr-srv1-deepseek",
                "unit_id": "unt-" + "e" * 64,
                "launch": {
                    "argv": DEEPSEEK_ARGV,
                    "env": LLAMA_ENV,
                    "volumes": MODELS_VOLUMES,
                },
            },
            "srv2_3b": {
                **common,
                "rig": "srv2",
                "address": "http://srv2:8001",
                "engine": "vllm",
                "image": VLLM_IMAGE,
                "model": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
                "width": 8,
                "window": 4096,
                "room_mib": 3573,
                "kv_cache_memory_bytes": 1207959552,
                "attention_backend": "FLASH_ATTN",
                "container": "mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001",
                "hf_cache": HF_CACHE,
                "unit_id": "unt-" + "3" * 64,
                "launch": {"argv": THREE_B_ARGV, "env": VLLM_ENV},
            },
            "srv2_7b": {
                **common,
                "rig": "srv2",
                "address": "http://srv2:8002",
                "engine": "vllm",
                "image": VLLM_IMAGE,
                "model": "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
                "width": 8,
                "window": 4096,
                "room_mib": 8099,
                "kv_cache_memory_bytes": 1879048192,
                "attention_backend": "FLASH_ATTN",
                "container": "mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002",
                "hf_cache": HF_CACHE,
                "unit_id": "unt-" + "7" * 64,
                "launch": {"argv": SEVEN_B_ARGV, "env": VLLM_ENV},
            },
        },
        "rigs": {
            "srv1": {"rig_id": "rig-" + "1" * 64},
            "srv2": {"rig_id": "rig-" + "2" * 64},
        },
        "fleets": {
            "b-small": {
                "layout": {
                    "srv2": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
                    "srv1": [["srv1_deepseek", "awake"]],
                },
                "next": [],
            }
        },
    }


def install(tmp_path: Path, document: dict[str, Any]) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "fleet.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    ladder = list(document["units"])
    (config / "policy.yaml").write_text(
        yaml.safe_dump({"ladder": ladder}), encoding="utf-8"
    )
    return config


@pytest.fixture(autouse=True)
def no_scans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No rig has been scanned: a locked launch needs no scan to be rendered."""
    empty = tmp_path / "scans"
    empty.mkdir()
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(empty))


def emit(config: Path, out: Path, *extra: str) -> int:
    return main(["emit", "--config", str(config), "--out", str(out), *extra])


def services(path: Path) -> dict[str, dict[str, Any]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(loaded["services"])


def by_container(path: Path) -> dict[str, dict[str, Any]]:
    return {block["container_name"]: block for block in services(path).values()}


def test_a_locked_fleet_is_emitted_without_a_scan_or_a_kv_dtype(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "compose"
    assert emit(install(tmp_path, fleet()), out) == Exit.OK, capsys.readouterr().err
    assert sorted(path.name for path in out.iterdir()) == [
        "compose.srv1.b-small.yml",
        "compose.srv2.b-small.yml",
    ]


def test_each_service_runs_the_launch_its_unit_id_was_hashed_over(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = fleet()
    out = tmp_path / "compose"
    assert emit(install(tmp_path, document), out) == Exit.OK, capsys.readouterr().err
    emitted = by_container(out / "compose.srv1.b-small.yml") | by_container(
        out / "compose.srv2.b-small.yml"
    )
    for name, unit in document["units"].items():
        service = emitted.get(unit["container"])
        assert service is not None, f"{name}: no service runs as {unit['container']}"
        assert service["command"] == unit["launch"]["argv"], name
        assert service["environment"] == unit["launch"]["env"], name
        assert service["image"] == unit["image"], name


def test_a_llama_cpp_unit_mounts_what_it_states_and_vllm_mounts_its_cache(
    tmp_path: Path,
) -> None:
    out = tmp_path / "compose"
    assert emit(install(tmp_path, fleet()), out) == Exit.OK
    deepseek = by_container(out / "compose.srv1.b-small.yml")["mcgyvr-srv1-deepseek"]
    assert deepseek["volumes"] == MODELS_VOLUMES
    for service in services(out / "compose.srv2.b-small.yml").values():
        assert service["volumes"] == [f"{HF_CACHE}:/root/.cache/huggingface:ro"]
        assert service["ipc"] == "host"


def test_the_layout_is_the_start_order(tmp_path: Path) -> None:
    out = tmp_path / "compose"
    assert emit(install(tmp_path, fleet()), out) == Exit.OK
    pair = services(out / "compose.srv2.b-small.yml")
    assert pair["srv2_7b"]["depends_on"] == {
        "srv2_3b": {"condition": "service_healthy"}
    }
    assert "depends_on" not in pair["srv2_3b"]
    assert "localhost:8001" in " ".join(pair["srv2_3b"]["healthcheck"]["test"])
    assert (
        "depends_on" not in services(out / "compose.srv1.b-small.yml")["srv1_deepseek"]
    )


def test_a_locked_unit_that_names_no_container_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = fleet()
    del document["units"]["srv1_deepseek"]["container"]
    out = tmp_path / "compose"
    assert emit(install(tmp_path, document), out) == Exit.REFUSED
    said = capsys.readouterr().err
    assert "srv1_deepseek" in said and "container" in said
    assert not out.exists() or not any(out.iterdir())


def test_a_locked_llama_cpp_unit_that_states_no_volumes_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = fleet()
    del document["units"]["srv1_deepseek"]["launch"]["volumes"]
    out = tmp_path / "compose"
    assert emit(install(tmp_path, document), out) == Exit.REFUSED
    said = capsys.readouterr().err
    assert "srv1_deepseek" in said and "volumes" in said


def test_check_agrees_with_the_files_it_wrote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = install(tmp_path, fleet())
    out = tmp_path / "compose"
    assert emit(config, out) == Exit.OK
    capsys.readouterr()
    assert emit(config, out, "--check") == Exit.OK, capsys.readouterr().err


def test_the_stamped_setup_emits_the_argv_and_env_its_digests_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``fleet-setup/`` is the stamped a-solo/b-small/b-big setup, and
    ``digests-srv{1,2}.json`` record the argv and env each unit_id hashed."""
    config = tmp_path / "config"
    config.mkdir()
    for name in ("fleet.yaml", "policy.yaml"):
        shutil.copy(REPO / "fleet-setup" / name, config / name)
    # A setup is its two fleet files AND the seccomp profiles its units state:
    # `launch.seccomp` names one relative to here (owner, 2026-09-16).
    shutil.copytree(REPO / "fleet-setup" / "seccomp", config / "seccomp")
    out = tmp_path / "compose"
    assert emit(config, out) == Exit.OK, capsys.readouterr().err

    stamped = yaml.safe_load((config / "fleet.yaml").read_text(encoding="utf-8"))
    hashed: dict[str, Any] = {}
    for host in ("srv1", "srv2"):
        digests = REPO / "fleet-setup" / f"digests-{host}.json"
        hashed |= json.loads(digests.read_text(encoding="utf-8"))["units"]

    expected_files = sorted(
        [
            *(
                f"compose.{host}.{fleet_name}.yml"
                for fleet_name, block in stamped["fleets"].items()
                for host in block["layout"]
            ),
            # srv2_35b_256k states a seccomp profile, and emit writes it beside
            # the compose file that names it, which is where compose looks.
            "io-uring.json",
        ]
    )
    assert sorted(path.name for path in out.iterdir()) == expected_files
    for fleet_name, block in stamped["fleets"].items():
        for host, slots in block["layout"].items():
            emitted = services(out / f"compose.{host}.{fleet_name}.yml")
            for unit_name, _state in slots:
                service = emitted[unit_name]
                unit = stamped["units"][unit_name]
                fields = hashed[unit_name]["fields"]
                assert unit["unit_id"] == hashed[unit_name]["unit_id"], unit_name
                assert service["container_name"] == unit["container"], unit_name
                assert service["command"] == fields["argv"], unit_name
                assert service["environment"] == fields["env"], unit_name
