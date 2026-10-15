"""The door a rig is served through: its ladder, its rungs, and waking a card."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ModelSpec,
)
from tests import livejournal as lj

UNITS = ("mcgyvr-box1-a-8001", "mcgyvr-box1-b-8002")


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
    path = root / "compose.box1.yml"
    path.write_text(yaml.safe_dump({"services": services}), encoding="utf-8")
    return path


CONFIG_VAR = "MCGYVR_CONFIG"


#: A setup under development: same rig, its own file, outside the config
#: folder, so nothing locked holds it (:func:`mcgyvr.fleet.roots.runs_live`).
DEV_LADDER = """\
units:
  only:
    address: http://box1:8001
    model: a-model
    rig: rig
    engine: vllm
    window: 32768
ladder:
- only
sandbox:
  mode: tempdir
"""


def dev_config(path: Path) -> Path:
    """A setup outside the config folder, which this door run reads."""
    path.write_text(DEV_LADDER, encoding="utf-8")
    return path


HOST = "box2"


RUNG_3B = "local_qwen2.5-coder-3b"


RUNG_7B = "local_qwen2.5-coder-7b"


def ladder(*, engine: str) -> str:
    """box2's two rungs, on one card, behind ``engine``.

    ``attempts: 1`` on each tier so that "the retry spends no attempt" is a
    statement the result file can be read for: a rung allowed one attempt that
    was refused and then answered must show one attempt, and a rung that
    charged the refusal has none left to answer with.
    """
    return f"""
units:
  {RUNG_3B}:
    address: http://{HOST}:8001
    model: qwen2.5-coder-3b
    engine: {engine}
    rig: box2_3b
    width: 2
    window: 32768
  {RUNG_7B}:
    address: http://{HOST}:8002
    model: qwen2.5-coder-7b
    engine: {engine}
    rig: box2_7b
    width: 2
    window: 32768
ladder:
- {RUNG_3B}
- {RUNG_7B}
attempts:
  {RUNG_3B}: 1
  {RUNG_7B}: 1
"""


def compose_dir(tmp_path: Path, *, with_spec: bool) -> Path:
    """Where this checkout keeps launch specs, holding box2's or holding none.

    The file name is ``emit_all``'s own convention rather than a literal, so a
    wake that looked somewhere else would fail here rather than in a year on a
    rig: one compose file per host, ``compose.<host>.yml``, because a host is
    what an operator brings up.
    """
    from mcgyvr.emit import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    if with_spec:
        (where / f"{COMPOSE_PREFIX}{HOST}{COMPOSE_SUFFIX}").write_text(
            "services:\n"
            "  qwen7b:\n"
            "    image: vllm/vllm-openai:v0.26.0\n"
            f"    container_name: mcgyvr-{HOST}-qwen7b-8002\n"
            "  qwen3b:\n"
            "    image: vllm/vllm-openai:v0.26.0\n"
            f"    container_name: mcgyvr-{HOST}-qwen3b-8001\n"
            "    depends_on: [qwen7b]\n",
            encoding="utf-8",
        )
    return where


def config_file(
    path: Path,
    *,
    journal: Path,
    specs: Path | None,
    switch: bool | None,
    engine: str = "vllm",
) -> Path:
    """A config on disk. ``switch=None`` writes no ``serving:`` block at all.

    The file is written where the test says, outside the config folder, so a
    run under it is held to no lock (:func:`mcgyvr.fleet.roots.runs_live`):
    these tests pin the wake mechanism, which a setup that is not the live
    fleet may exercise freely.

    Loaded here rather than left for ``mcgyvr run`` to load, so that a config
    the schema does not know says so at the line that wrote it.
    """
    from mcgyvr.config import load

    text = ladder(engine=engine) + f"journal:\n  dir: {journal}\n"
    if switch is not None:
        text += "serving:\n"
        text += f"  enable_sleep_wake: {'true' if switch else 'false'}\n"
        if specs is not None:
            text += f"  compose_dir: {specs}\n"
    path.write_text(text, encoding="utf-8")
    load(path)
    return path


def door_log(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Substitute the one subprocess a wake is allowed to make, and record it.

    D3: "A wake is ``python -m mcgyvr.serving.run serve up --host H --compose
    FILE --suffix S``, spawned as a subprocess. ... Nothing in ``mcgyvr.wake``
    runs ``docker`` or ``ssh``." Under the door those two names resolve to shims
    that admit only the host the door was opened for and only a process the door
    started, and ``tests/test_one_door.py`` bans the way round it. So a single
    seam is the whole of this module's contact with a rig, and a test that owns
    it owns everything that could reach a machine.

    Returning ``0`` is the door reporting the card up. What the caller does with
    that — dispatch again, once — is what the tests below read.
    """
    import mcgyvr.wake as wake

    spawned: list[list[str]] = []

    def spawn(argv: Sequence[str], **_: Any) -> int:
        spawned.append(list(argv))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return spawned


FAST = "local_fast"


SMALL = "local_small"


LARGE = "local_large"


FAST_HOST = "fast-box.example"


SHARED_HOST = "shared-box.example"


SMALL_CONTAINER = "mcgyvr-shared-small"


LARGE_CONTAINER = "mcgyvr-shared-large"


def ladder_text(
    compose_dir: Path | None,
    *,
    engine: str = "vllm",
    small_mib: int | None = 4000,
    large_mib: int | None = 9000,
) -> str:
    def room(mib: int | None) -> str:
        return "" if mib is None else f"    room_mib: {mib}\n"

    serving = (
        ""
        if compose_dir is None
        else f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    )
    return (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: small-coder\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {SMALL}:\n"
        f"    address: http://{SHARED_HOST}:8001\n"
        "    model: mid-coder\n"
        "    rig: shared-rig-small\n"
        f"    engine: {engine}\n"
        "    width: 2\n" + room(small_mib) + f"  {LARGE}:\n"
        f"    address: http://{SHARED_HOST}:8002\n"
        "    model: large-coder\n"
        "    rig: shared-rig-large\n"
        f"    engine: {engine}\n"
        "    width: 2\n" + room(large_mib) + "ladder:\n"
        f"- {FAST}\n"
        f"- {SMALL}\n"
        f"- {LARGE}\n" + serving
    )


def reservation(device_ids: list[str]) -> dict[str, Any]:
    """The card reservation ``emit`` writes for a service, naming ``device_ids``."""
    return {
        "resources": {
            "reservations": {
                "devices": [
                    {
                        "driver": "nvidia",
                        "device_ids": device_ids,
                        "capabilities": ["gpu"],
                    }
                ]
            }
        }
    }


def write_spec(
    tmp_path: Path,
    *,
    small_on: list[str] | None = None,
    large_on: list[str] | None = None,
) -> Path:
    """The shared host's one launch spec: both units, each its own container.

    ``small_on`` and ``large_on`` are the card ids each service reserves;
    ``None`` writes no reservation, as a hand-written spec may not.
    """
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    services: dict[str, dict[str, Any]] = {
        "small": {
            "image": "example/server:1",
            "container_name": SMALL_CONTAINER,
            "command": ["mid-coder", "--port", "8001"],
        },
        "large": {
            "image": "example/server:1",
            "container_name": LARGE_CONTAINER,
            "command": ["large-coder", "--port", "8002"],
        },
    }
    if small_on is not None:
        services["small"]["deploy"] = reservation(small_on)
    if large_on is not None:
        services["large"]["deploy"] = reservation(large_on)
    (where / f"{COMPOSE_PREFIX}{SHARED_HOST}{COMPOSE_SUFFIX}").write_text(
        yaml.safe_dump({"services": services}), encoding="utf-8"
    )
    return where


def a_clean_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


OTHER_HOST = "other-box.example"


def split_ladder(compose_dir: Path, *, across: str) -> str:
    """The shared host's larger unit split over two cards, the second on ``across``.

    No worker ``bind`` is stated: which machines a unit spans is all the
    manager reads, and an address is emit's to check.
    """
    return ladder_text(compose_dir).replace(
        "    model: large-coder\n",
        "    model: large-coder\n"
        "    launch:\n"
        "      shards:\n"
        f"      - {{rig: {SHARED_HOST}, gpu: 0}}\n"
        f"      - {{rig: {across}, gpu: 1}}\n",
    )


#: A serve of another run, on another machine, holding box1 (the lease format of
#: ``tests/red_port/test_dod_rig_lease.py``).
DEV_SERVE_LEASE = (
    "lease_id=deadbeefdeadbeef holder=someone@elsewhere "
    "machine=elsewhere0000 pid=1 started_at=2026-09-06T01:02:03Z "
    "step=serve-up run_id=2026-09-06-box1-serve-up"
)


SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"


HF_CACHE = "/home/someone/.cache/huggingface"


# The spike's card figures, in GiB: 7291 MiB alone, 10869 - 7291 beside it.
SEVEN_B_SPEC = ModelSpec(
    name=SEVEN_B,
    vram_gb=7.12,
    ram_gb=0.0,
    disk_gb=4.93,
    hf_cache=HF_CACHE,
    serve_args=("--gpu-memory-utilization", "0.68"),
    kv_cache_dtype_k="auto",
)


def rig(host: str, *, vram_mib: int = 12288, free_mib: int = 11911) -> Scan:
    scan = Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=45.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=27.9,
    )
    gpu = scan.gpus[0]
    from dataclasses import replace

    return replace(
        scan, gpus=(replace(gpu, vram=replace(gpu.vram, free_mib=free_mib)),)
    )


def service_of(document: str) -> dict[str, Any]:
    return next(iter(yaml.safe_load(document)["services"].values()))


THINKING_OFF = ("--chat-template-kwargs", '{"enable_thinking":false}')


DENSE = ModelSpec(
    name="qwen2.5-coder-3b",
    vram_gb=2.4,
    ram_gb=0.0,
    disk_gb=2.1,
    serve_args=THINKING_OFF,
    kv_cache_dtype_k="f16",
    kv_cache_dtype_v="f16",
)
