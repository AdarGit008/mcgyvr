"""Draw 0 is greedy, and every draw after it samples at ``breadth.temperature``.

Every dispatch mcgyvr made went out at ``temperature: 0.0`` — the
:class:`~mcgyvr.runner.Request` default, which no production caller ever set —
so ``breadth.draws: 3`` asked the same greedy question three times and got the
same bytes back three times. A lever whose whole benefit is a *different*
candidate bought nothing but wall clock, and the journal has no column that
would have said so.

The rule that fixes it keeps today's single draw byte-identical: draw 0 is
always greedy, so an unconfigured install sends exactly what it sent
yesterday, and only the draws after it — the ones that exist to be different —
sample at ``breadth.temperature``. The temperature is a schema field with the
schema's own bounds, threaded onto the request through
:func:`~mcgyvr.drive.dispatch_prompt`, which is the one seam between an
assembled prompt and the wire.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import BREADTH_FIELDS, ConfigSchemaError, parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import dispatch_prompt, worker_attempt
from mcgyvr.pool import Rung, source_map
from mcgyvr.route import Try
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.worker.prompt import build_prompt
from tests import livejournal as lj

RUNG = Rung(name="local_qwen-7b", model="qwen2.5-coder:7b")


def _temperatures_sent(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Every dispatch's temperature, in the order the dispatches were made."""
    sent: list[float] = []

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        sent.append(request.temperature)
        return lj.completion(lj.BAD_REPLY, request)

    lj.patch_dispatch(monkeypatch, fake_dispatch)
    return sent


def _drive(tmp_path: Path, policy: str) -> Any:
    repo = lj.make_repo(tmp_path / "repo")
    config = parse(lj.LADDER + policy)
    contract = load_contract(lj.MODEL_CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, source_map(config), contract, sandbox)
        return attempt(Try(rung=RUNG, attempt=1, of=1))


def test_the_schema_declares_a_breadth_temperature_between_zero_and_two() -> None:
    (field,) = [f for f in BREADTH_FIELDS if f.name == "temperature"]
    assert field.kind == "float"
    assert field.default == 0.7
    assert (field.min_value, field.max_value) == (0.0, 2.0)
    assert field.doc, "a key that cannot be explained does not belong in the file"

    assert parse(lj.LADDER).get("breadth.temperature") == 0.7

    with pytest.raises(
        ConfigSchemaError, match=r"breadth\.temperature: must be at most"
    ):
        parse(lj.LADDER + "breadth:\n  temperature: 2.5\n")
    with pytest.raises(
        ConfigSchemaError, match=r"breadth\.temperature: must be at least"
    ):
        parse(lj.LADDER + "breadth:\n  temperature: -0.1\n")


def test_draw_zero_goes_out_greedy_and_the_rest_at_the_breadth_temperature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _temperatures_sent(monkeypatch)

    judgement = _drive(tmp_path, "breadth:\n  draws: 3\n  temperature: 0.9\n")

    assert judgement.draws == 3
    assert sent == [0.0, 0.9, 0.9], (
        "draw 0 is the greedy anchor and every draw after it is sampled; "
        f"the dispatches went out at {sent}"
    )


def test_a_single_draw_is_greedy_whatever_the_temperature_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured install sends what it always sent, byte for byte."""
    sent = _temperatures_sent(monkeypatch)

    judgement = _drive(tmp_path, "breadth:\n  temperature: 1.5\n")

    assert judgement.draws == 1
    assert sent == [0.0], "one draw is draw 0, and draw 0 does not sample"


def test_dispatch_prompt_puts_the_temperature_it_is_handed_on_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[Any] = []

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        sent.append(request)
        return lj.completion(lj.BAD_REPLY, request)

    lj.patch_dispatch(monkeypatch, fake_dispatch)
    pool = source_map(parse(lj.LADDER))
    contract = load_contract(lj.MODEL_CONTRACT)
    prompt = build_prompt(contract)

    dispatch_prompt(pool, RUNG.name, prompt, contract, temperature=0.9)
    dispatch_prompt(pool, RUNG.name, prompt, contract)

    sampled, default = sent
    assert sampled.temperature == 0.9
    assert default.temperature == 0.0, (
        "a caller that names no temperature sends what this has always sent"
    )
