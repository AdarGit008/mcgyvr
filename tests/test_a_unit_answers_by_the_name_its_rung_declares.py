"""A unit mcgyvr emits answers by the name its rung declares, and a ride is
read by the same rule as a rung of one's own.

llama.cpp names an answer's ``model`` after the path it was handed unless it is
started with ``--alias``. A unit emitted without one answers
``/models/<name>.gguf`` to a request for ``<name>``, and a rider whose relief
rung was matched on ``<name>`` receives the host's path. So the emitted launch
carries ``--alias <the unit's model>``: the name the setup declares and the hub
is told, with no path and no file suffix added.

The rider's side reads a ridden answer with :func:`mcgyvr.weights.is_model`,
the rule a rung of its own is read by, so a host started by hand without an
alias is still the model it was matched on. A different model, the hub's own
``hitchhike@<id>`` and no name at all are still the rung refusing the request.

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from mcgyvr.emit import argv, render_command, render_compose
from mcgyvr.runner import Completion
from mcgyvr.scan import Scan
from mcgyvr.serving import ROLE_RPC, ModelSpec, Unit, unit_for
from tests.test_a_ridden_answer_from_another_model_is_a_full_rung import (
    SERVED,
    completion,
    ride,
)
from tests.test_a_ridden_answer_from_another_model_is_a_full_rung import (
    key as key,  # the fixture that sets the rider's key
)

MODEL = "qwen2.5-coder-3b"
WINDOW = 4096


def unit(engine: str = "llama.cpp", name: str = MODEL) -> Unit:
    scan = Scan.of(
        host="rig-a.example",
        vram_mib=12288,
        ram_gb=16.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )
    spec = ModelSpec(
        name=name,
        vram_gb=2.4,
        ram_gb=0.0,
        disk_gb=2.1,
        kv_cache_dtype_k="f16" if engine == "llama.cpp" else "auto",
        kv_cache_dtype_v="f16" if engine == "llama.cpp" else "auto",
        hf_cache="" if engine == "llama.cpp" else "/srv/hf",
    )
    return unit_for(scan, spec, engine=engine, width=2, ctx_per_slot=WINDOW)


def alias_of(parts: tuple[str, ...] | list[str]) -> list[str]:
    return [parts[i + 1] for i, part in enumerate(parts) if part == "--alias"]


def test_the_emitted_server_answers_by_the_units_model_name() -> None:
    assert alias_of(argv(unit())) == [MODEL]


def test_the_compose_file_and_the_bare_command_carry_the_same_alias() -> None:
    emitted = unit()
    service = next(iter(yaml.safe_load(render_compose(emitted))["services"].values()))

    assert alias_of(service["command"]) == [MODEL]
    assert alias_of(render_command(emitted).split()) == [MODEL]


def test_a_model_named_as_a_file_is_aliased_as_declared_and_not_doubled() -> None:
    named = "Qwen3-8B-Q4_K_M.gguf"

    assert alias_of(argv(unit(name=named))) == [named]


@pytest.mark.parametrize("flag", ["--alias", "-a"])
def test_an_alias_the_owner_stated_is_the_only_one(flag: str) -> None:
    stated = replace(unit(), extra=(flag, "mine"))

    parts = argv(stated)

    assert alias_of(parts) == (["mine"] if flag == "--alias" else [])
    assert parts[-2:] == (flag, "mine")


def test_only_a_llama_cpp_server_is_given_an_alias() -> None:
    # vLLM serves the repository id it was started with; a worker answers no
    # request at all.
    assert alias_of(argv(unit("vllm"))) == []
    assert alias_of(argv(replace(unit(), role=ROLE_RPC))) == []


@pytest.mark.parametrize(
    "answered",
    [
        SERVED,
        f"/models/dense/{SERVED}.gguf",
        f"/models/dense/{SERVED.upper()}.gguf",
        f"/models/dense/{SERVED}-00001-of-00002.gguf",
    ],
)
def test_a_ridden_answer_naming_the_matched_model_in_any_served_form_is_kept(
    tmp_path: Path, answered: str
) -> None:
    done = ride(completion(answered), tmp_path)

    assert isinstance(done, Completion)
    assert done.text == "ok"
