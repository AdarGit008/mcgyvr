"""Setup writes the context window each local backend serves on its unit.

Owner decision (2026-10-14, e2e run 3 T1): every unit carries a ceiling from
setup, which a `code` contract's cap is held to. A hosted unit is written with
``output_tokens``; a local one with ``window``, the context length its backend
serves, read off the running process rather than assumed:

* vLLM: ``max_model_len`` on its ``/v1/models`` rows;
* llama-server: ``default_generation_settings.n_ctx`` from ``/props``;
* LM Studio: ``max_context_length`` on its ``/api/v0/models`` rows;
* TGI: ``max_total_tokens`` from ``/info``.

A backend whose window cannot be read is written with none, and setup lists it
under what is NOT configured: a `code` dispatch to that unit refuses until
``window`` or ``output_tokens`` is set.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import detect as detect_module
from mcgyvr.detect import Backend, Detection, ProbeTarget, probe
from mcgyvr.initialize import _sources_for, build
from mcgyvr.propose import propose

MODELS = {"data": [{"id": "small-coder"}]}


def stub_http(monkeypatch: pytest.MonkeyPatch, table: dict[str, Any]) -> None:
    monkeypatch.setattr(
        detect_module, "_get_json", lambda url, timeout: table.get(url), raising=True
    )


@pytest.mark.parametrize(
    ("kind", "port", "answers", "window"),
    [
        (
            "vllm",
            8000,
            {"/v1/models": {"data": [{"id": "small-coder", "max_model_len": 32768}]}},
            32768,
        ),
        (
            "llama-server",
            8080,
            {
                "/v1/models": MODELS,
                "/props": {"default_generation_settings": {"n_ctx": 8192}},
            },
            8192,
        ),
        (
            "lmstudio",
            1234,
            {
                "/v1/models": MODELS,
                "/api/v0/models": {
                    "data": [{"id": "small-coder", "max_context_length": 4096}]
                },
            },
            4096,
        ),
        (
            "tgi",
            3000,
            {"/v1/models": MODELS, "/info": {"max_total_tokens": 2048}},
            2048,
        ),
    ],
)
def test_the_served_window_is_read_where_each_backend_states_it(
    kind: str,
    port: int,
    answers: dict[str, Any],
    window: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = f"http://localhost:{port}"
    stub_http(monkeypatch, {base + path: body for path, body in answers.items()})

    found = probe(ProbeTarget(kind, base, "openai"))

    assert found is not None
    assert found.window == window


@pytest.mark.parametrize(
    "props",
    [None, {}, {"default_generation_settings": {"n_ctx": "lots"}}, {"n_ctx": 0}],
)
def test_a_window_that_cannot_be_read_is_none(
    props: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = "http://localhost:8080"
    stub_http(monkeypatch, {base + "/v1/models": MODELS, base + "/props": props})

    found = probe(ProbeTarget("llama-server", base, "openai"))

    assert found is not None and found.window is None


def _setup(window: int | None) -> tuple[dict[str, Any], tuple[str, ...]]:
    from mcgyvr.initialize import _limits

    detection = Detection(
        backends=(
            Backend(
                name="llama-server",
                base_url="http://localhost:8080",
                api="openai",
                models=("small-coder",),
                how="substituted",
                window=window,
            ),
        ),
        provenance={"backends": "substituted"},
    )
    proposal = propose(sources=_sources_for(detection))
    return build(detection, proposal), _limits(detection, proposal)


def test_a_local_unit_is_written_with_the_window_its_backend_serves() -> None:
    data, limits = _setup(8192)

    (unit,) = data["units"].values()
    assert unit["window"] == 8192
    assert not any("window" in line for line in limits), limits


def test_a_window_setup_could_not_read_is_named_as_not_configured() -> None:
    data, limits = _setup(None)

    (name,) = data["units"]
    assert "window" not in data["units"][name]
    (said,) = [line for line in limits if f"units.{name}.window" in line]
    assert f"units.{name}.output_tokens" in said, said
    assert "refuses" in said, said
