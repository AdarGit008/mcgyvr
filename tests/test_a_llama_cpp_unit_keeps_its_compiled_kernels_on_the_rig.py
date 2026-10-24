"""A llama.cpp unit keeps the kernels its card's driver compiled on the rig.

The driver caches what it compiles under ``$CUDA_CACHE_PATH``, else under
``$HOME/.nv/ComputeCache`` inside the container, which is gone with the
container. So a llama.cpp unit's service mounts the rig's store,
``$MCGYVR_HOME/cuda-cache``, resolved on the rig by its own scan, and names it
in ``CUDA_CACHE_PATH`` whatever user and home the image runs as. A rig whose
scan read no home, and a vLLM unit, are rendered as before.

The machines here are invented.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import _rpc_service, render_compose, resolved_launch
from mcgyvr.fleet import roots
from mcgyvr.scan import Scan
from mcgyvr.serving import ROLE_RPC, ModelSpec, kernelcache, rigscan, unit_for

HOME = Path("/srv/someone/.mcgyvr")
STORE = f"{HOME}/cuda-cache:/cuda-cache:rw"
ENV = {"CUDA_CACHE_PATH": "/cuda-cache", "CUDA_CACHE_MAXSIZE": "4294967296"}
SPEC = ModelSpec(
    name="coder-small",
    vram_gb=2.4,
    ram_gb=0.0,
    disk_gb=2.1,
    kv_cache_dtype_k="f16",
    kv_cache_dtype_v="f16",
)
VLLM_SPEC = ModelSpec(
    name="org/coder-small-awq",
    vram_gb=3.5,
    ram_gb=0.0,
    disk_gb=2.0,
    hf_cache="/srv/someone/.cache/huggingface",
    kv_cache_dtype_k="auto",
)


def rig(*, home: Path | None) -> Scan:
    scan = Scan.of(
        host="rig-a", vram_mib=8192, ram_gb=32.0, disk_free_gb=500.0, cores=8
    )
    return replace(scan, home=home)


def service(unit: Any) -> dict[str, Any]:
    document = yaml.safe_load(render_compose(unit))
    return next(iter(document["services"].values()))


def llama(home: Path | None = HOME) -> Any:
    return unit_for(
        rig(home=home), SPEC, engine="llama.cpp", width=2, ctx_per_slot=4096
    )


def test_a_llama_cpp_service_mounts_the_store_and_names_it_to_the_driver() -> None:
    served = service(llama())
    assert STORE in served["volumes"]
    for name, value in ENV.items():
        assert served["environment"][name] == value
    # The weights are mounted as before, beside the store.
    assert len(served["volumes"]) == 3


def test_an_rpc_worker_is_handed_the_same_store() -> None:
    """A worker runs kernels on its card too, so it finds the same store."""
    worker = replace(llama(), role=ROLE_RPC, image="example/llama-rpc:1")
    served = _rpc_service(worker)
    assert served["volumes"] == [STORE]
    assert served["environment"] == ENV


def test_a_rig_whose_scan_read_no_home_is_rendered_as_before() -> None:
    served = service(llama(home=None))
    assert not any(":/cuda-cache" in volume for volume in served["volumes"])
    assert "CUDA_CACHE_PATH" not in served["environment"]
    assert "volumes" not in _rpc_service(
        replace(llama(home=None), role=ROLE_RPC, image="example/llama-rpc:1")
    )


def test_a_vllm_unit_is_not_handed_the_store() -> None:
    unit = unit_for(
        rig(home=HOME), VLLM_SPEC, engine="vllm", width=4, ctx_per_slot=4096
    )
    served = service(unit)
    assert served["volumes"] == [
        "/srv/someone/.cache/huggingface:/root/.cache/huggingface:ro"
    ]
    assert "CUDA_CACHE_PATH" not in served["environment"]


def test_the_stamped_launch_carries_the_store_a_locked_unit_renders() -> None:
    launch = resolved_launch(llama())["launch"]
    assert STORE in launch["volumes"]
    assert {name: launch["env"][name] for name in ENV} == ENV


def test_a_unit_env_that_moves_the_cache_is_refused_by_name() -> None:
    from mcgyvr.emit import EmitError

    moved = replace(llama(), env={"CUDA_CACHE_PATH": "/elsewhere"})
    with pytest.raises(EmitError, match="CUDA_CACHE_PATH"):
        render_compose(moved)


def test_docker_run_flags_spell_the_store_as_compose_does() -> None:
    mounted = kernelcache.mount(kernelcache.folder(HOME))
    assert mounted.docker_args() == [
        "--volume",
        STORE,
        "--env",
        "CUDA_CACHE_MAXSIZE=4294967296",
        "--env",
        "CUDA_CACHE_PATH=/cuda-cache",
    ]


def test_the_rig_resolves_its_own_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scan runs on the rig, so the store is under the rig's home, not the
    home of the machine that renders the compose file."""
    monkeypatch.delenv("MCGYVR_HOME", raising=False)
    monkeypatch.setenv("HOME", "/srv/someone")
    assert rigscan.mcgyvr_home() == "/srv/someone/.mcgyvr"
    monkeypatch.setenv("MCGYVR_HOME", "/data/mcgyvr")
    assert rigscan.mcgyvr_home() == "/data/mcgyvr"
    monkeypatch.setenv("MCGYVR_HOME", "relative/mcgyvr")
    assert rigscan.mcgyvr_home() is None


def test_the_rig_spells_the_home_as_the_package_does() -> None:
    """rigscan runs on a rig without the package, so it spells the pair again."""
    assert (rigscan.HOME_ENV, rigscan.HOME_DIR) == (roots.HOME_ENV, roots.HOME_DIR)
    assert kernelcache.SHOWN == "$MCGYVR_HOME/cuda-cache (default ~/.mcgyvr/cuda-cache)"


def test_a_scan_keeps_the_home_it_read_and_an_older_one_reads_none() -> None:
    scan = rig(home=HOME)
    assert Scan.from_json(scan.to_json()).home == HOME
    older = json.loads(scan.to_json())
    del older["home"]
    assert Scan.from_json(json.dumps(older)).home is None
