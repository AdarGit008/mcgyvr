"""How long one request may take is the run's declaration, not a constant.

``GENERATE_TIMEOUT_S`` was a module literal of 120 seconds and every dispatch
took it, so a fixed number in the runner silently decided which combinations
of reply cap and rung width an operator was allowed to declare.

The three are not independent. A reply of ``limits.max_output_tokens`` tokens,
generated at whatever per-stream rate a rung gives at the width it is serving,
takes a time that either fits the timeout or does not. Measured on the live
ladder, 2026-09-06 (``records/measurements/serving-concurrency-2026-09-06/``):
the srv1 rung gives 27.2 tok/s to one stream and 5.09 tok/s to each of eight,
so a 1024-token reply takes 38 seconds alone and 201 seconds at width eight.
Under a constant of 120 the second is unreachable — not refused, and not
reported as a width that is too wide for this cap, but failed one request at a
time as a transport error that names a socket and not the ceiling behind it.

So the number belongs to the run that declares the cap and the width, beside
them, where an operator changing one can see the other two. ``budgets`` is
where this file already keeps what bounds one task's cost, and 120 stays the
default: a run that declares nothing behaves exactly as it did.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _config(path: Path, journal: Path, budgets: str = "") -> Path:
    text = LADDER + budgets + f"journal:\n  dir: {journal}\n"
    path.write_text(text, encoding="utf-8")
    return path


def _timeout_of_one_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budgets: str
) -> float:
    seen: list[float] = []

    def capture(source_map: Any, rung: str, request: Any, **kw: Any) -> Any:
        seen.append(request.timeout_s)
        return lj.completion(lj.GOOD_REPLY, request)

    lj.patch_dispatch(monkeypatch, capture)
    repo = lj.make_repo(tmp_path / "repo")
    config = _config(tmp_path / "mcgyvr.yaml", tmp_path / "journal", budgets)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    lj.main(lj.run_args(contract, repo, config))
    assert seen, "no dispatch was made"
    return seen[0]


def test_a_declared_request_timeout_reaches_the_request(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declared = _timeout_of_one_dispatch(
        tmp_path, monkeypatch, "budgets:\n  request_timeout_s: 300\n"
    )
    assert declared == 300.0, (
        "the run declared `budgets.request_timeout_s: 300` and the request "
        f"went out with {declared}: a constant in the runner decided how long "
        "a reply was allowed to take, so a cap and a width the operator is "
        "free to declare can be impossible to satisfy and never say so"
    )


def test_a_run_that_declares_no_timeout_keeps_the_one_it_always_had(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.runner import GENERATE_TIMEOUT_S

    assert _timeout_of_one_dispatch(tmp_path, monkeypatch, "") == GENERATE_TIMEOUT_S
