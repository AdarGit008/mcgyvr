"""A composed init writes the use case and deployment it says it chose.

``mcgyvr init --priority X`` (formerly ``--profile X``) writes the candidate
the Jev decision selected, not the deterministic ladder. The decisions it
prints name the use case and deployment from the command line; the file it
writes must say the same, or the printed decision and the setup on disk
disagree.

The transport is stubbed as ``tests/test_compose.py`` stubs it: no test here
reaches a server, and a single candidate consults no model at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import compose as compose_module
from mcgyvr.config import load as load_config
from mcgyvr.decision import Choice, ChoiceAnswer, Decision
from mcgyvr.initialize import initialize, parse_api_unit
from mcgyvr.pool import Endpoint, Protocol
from tests.machine_shapes import detection, shape, with_server

LOCAL = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)


def _choose(monkeypatch: pytest.MonkeyPatch, choice: str) -> None:
    def fake_classify(
        endpoint: Endpoint,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> Decision:
        question = questions["setup"]
        assert isinstance(question, Choice)
        return Decision(
            answers={
                "setup": ChoiceAnswer(
                    choice=choice,
                    probabilities={n: float(n == choice) for n in question.options},
                    confidence=1.0,
                )
            }
        )

    monkeypatch.setattr(compose_module, "classify", fake_classify)


@pytest.mark.parametrize(
    ("use_case", "deployment", "hosted", "choice", "written_deployment"),
    [
        # One candidate: no model is consulted, the only one is written.
        ("chat", None, False, None, "local-only"),
        ("chat", "hybrid", False, None, "hybrid"),
        # Several candidates: the stubbed decision picks one.
        ("agent", None, True, "escalate", "hybrid"),
        ("agent", "local-only", False, None, "local-only"),
    ],
)
def test_the_file_states_the_use_case_and_deployment_the_decisions_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_case: str,
    deployment: str | None,
    hosted: bool,
    choice: str | None,
    written_deployment: str,
) -> None:
    if choice is not None:
        _choose(monkeypatch, choice)
    found = detection(
        with_server(
            shape("one-card"), kind="llama-server", models=("example-model-small",)
        )
    )
    api = (
        (
            parse_api_unit(
                "model=claude-opus-5,address=https://api.anthropic.com,"
                "api_key_env=ANTHROPIC_API_KEY"
            ),
        )
        if hosted
        else ()
    )

    result = initialize(
        tmp_path / "setup",
        detection=found,
        api_units=api,
        priority="quality",
        decision_endpoint=LOCAL,
        decision_model="example-model-small",
        use_case=use_case,
        deployment=deployment,
    )

    assert any("quality" in decision for decision in result.decisions), (
        "the composed path ran"
    )
    stated = f"Use case {use_case!r} under deployment {written_deployment!r}."
    assert stated in result.decisions
    config = load_config(tmp_path / "setup")
    assert config.use_case == use_case
    assert config.deployment == written_deployment
