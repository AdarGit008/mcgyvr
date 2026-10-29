"""A native head listens on the loopback alone, with only its engine's settings.

The head of a native pooled session is held to the native units' own rule
(``emit.native_block``, ``emit.LOOPBACK``): it is given ``--host`` the
loopback, a ``--host`` or ``LLAMA_ARG_HOST`` naming anything else is refused,
and a session that planned another bind address is refused before anything
starts. Its environment is a short list (what a program needs to run, and the
GPU runtimes' own variables), so an operator's hub token, cloud keys and
llama-server settings stay with the agent. Its devices are named by its
build's backend: CUDA by its own order, Metal as its one device, and a build
whose order is not the hub's (Vulkan, the CPU) names none. The agent itself
never runs a tool that needs admin rights to open a firewall.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcgyvr.emit import LOOPBACK
from mcgyvr.rig import pooled, userwg, wghelper
from mcgyvr.serving import llamacpp

SRC = Path(__file__).resolve().parents[1] / "src" / "mcgyvr" / "rig"


def _head_spec(bind: str) -> pooled.HeadSpec:
    return pooled.HeadSpec(
        session_id="s1",
        image=llamacpp.RUNTIME,
        binary="/app/llama-server",
        gpus=(0,),
        models_dir=Path("/models"),
        model="m.gguf",
        name="m.gguf",
        ctx=4096,
        n_gpu_layers=99,
        devices=("CUDA0",),
        tensor_split=(1,),
        rpc=(),
        bind=bind,
        memory_mb=8192,
    )


def _host(tmp_path: Path, backend: str = llamacpp.CUDA) -> userwg.NativeHost:
    engine = userwg.Engine(program=tmp_path / "llama-server", backend=backend)
    return userwg.NativeHost(
        agent_pid=1,
        helper=lambda: ["/x"],
        engine=lambda: engine,
        records=lambda: tmp_path / "records",
    )


@pytest.mark.parametrize("bind", ["198.51.100.2", "0.0.0.0"])
def test_a_native_head_never_binds_other_than_the_loopback(
    bind: str, tmp_path: Path
) -> None:
    host = _host(tmp_path)
    host._runs["s1"] = userwg._Run(
        session_id="s1",
        helper=wghelper.Helper(["/x"], log=tmp_path / "h.log"),
        api_port=18080,
    )
    with pytest.raises(pooled.PoolError, match=re.escape(f"binds {LOOPBACK}")):
        host.start_head(_head_spec(bind))


def test_an_operators_listening_address_is_refused_by_the_native_units_rule() -> None:
    with pytest.raises(pooled.PoolError, match=re.escape(f"{LOOPBACK} alone")):
        userwg.head_block("mcgyvr-pool-x-head", ["--host", "0.0.0.0"], {}, (0,))
    with pytest.raises(pooled.PoolError, match="LLAMA_ARG_HOST"):
        userwg.head_block(
            "mcgyvr-pool-x-head", ["-m", "m.gguf"], {"LLAMA_ARG_HOST": "x"}, (0,)
        )
    block = userwg.head_block("mcgyvr-pool-x-head", ["-m", "m.gguf"], {}, (0,))
    command = block["command"]
    assert command[command.index("--host") + 1] == LOOPBACK


def test_the_head_keeps_only_what_a_program_and_its_gpu_runtime_need() -> None:
    kept = userwg.engine_env(
        {
            "PATH": "/bin",
            "TEMP": "/tmp",
            "CUDA_CACHE_PATH": "/c",
            "GGML_METAL_PATH_RESOURCES": "/r",
            "HF_TOKEN": "hf_secret",
            "AWS_SECRET_ACCESS_KEY": "s",
            "LLAMA_ARG_HOST": "0.0.0.0",
            "LLAMA_API_KEY": "k",
            "MCGYVR_HOME": "/h",
        }
    )
    assert set(kept) == {"PATH", "TEMP", "CUDA_CACHE_PATH", "GGML_METAL_PATH_RESOURCES"}
    helper = userwg.helper_env({"PATH": "/bin", "HF_TOKEN": "s", "GGML_X": "1"})
    assert set(helper) == {"PATH", "GOMEMLIMIT"}


@pytest.mark.parametrize(
    ("backend", "named"),
    [
        (llamacpp.CUDA, "CUDA1"),
        (llamacpp.METAL, "MTL1"),
        (llamacpp.VULKAN, None),
        (llamacpp.CPU, None),
    ],
)
def test_a_native_heads_local_device_is_named_by_its_builds_backend(
    backend: str, named: str | None, tmp_path: Path
) -> None:
    host = _host(tmp_path, backend)
    assert host.local_device(1) is None  # no build is known before a prepare
    host.tunnel_image()
    assert host.local_device(1) == named


ADMIN_TOOLS = re.compile(
    r"\b(sudo|runas|netsh|pfctl|New-NetFirewallRule|Set-NetFirewallRule)\b"
)


@pytest.mark.parametrize("module", ["userwg.py", "wghelper.py", "wgpin.py"])
def test_the_native_session_code_runs_no_tool_that_needs_admin_rights(
    module: str,
) -> None:
    source = (SRC / module).read_text(encoding="utf-8")
    assert not ADMIN_TOOLS.findall(source)
