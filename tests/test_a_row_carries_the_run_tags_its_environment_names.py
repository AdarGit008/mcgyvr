"""A row carries the run tags its environment names, and nothing it was not told.

Whoever starts a run can say what the run belongs to — an experiment, a build,
a round — by setting ``MCGYVR_RUN_TAGS`` to a JSON object. The product does not
read meaning into it: every row the process writes carries the object, as it
was given, under ``run_tags``. Nested under one key rather than spread over the
row, so a tag can never stand in for a field the product writes itself
(``outcome`` is what :func:`~mcgyvr.telemetry.fold` folds a correction into,
``attempt_id`` is what it folds by), and so a reader can tell what the product
measured from what its caller asserted.

What these tests hold:

* the tags are on the answering row and on the failing one;
* a tag value that is text has a credentialed URL in it scrubbed, as every
  other string the row quotes and did not build;
* a set variable is the whole answer: the checkout's round is not also read
  (``{}`` says "no tags" and is obeyed);
* unset or empty, nothing is tagged — and an install with no development
  checkout around it carries no round either;
* anything but a small JSON object of text, number or true/false values is
  refused, and refused before the run starts, the way the product refuses an
  unusable ``$MCGYVR_HOME``;
* the setup document names the variable and the key.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from mcgyvr import config as configlib
from mcgyvr import telemetry
from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import ATTEMPT_KIND, fold, observe
from tests import livejournal as lj

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

REPO = Path(__file__).resolve().parent.parent

# ``observe`` called through an untyped alias.
_observe = cast("Callable[..., Any]", observe)

TAGS = {"round": "r7", "product_sha256": "ab" * 32, "draws": 3, "warm": True}


def _completion() -> Completion:
    return Completion(
        text="```python\nVALUE = 1\n```",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _record(sink: Path, attempt: Callable[[], Any] = _completion) -> dict[str, Any]:
    _observe(
        attempt,
        path=sink,
        attempt_id="agent-a:impl:local_qwen-7b:1",
        orchestrator="agent-a",
        rung="local_qwen-7b",
        messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ],
        endpoint="http://localhost:8080",
    )
    (row,) = fold(path=sink)
    return row


@pytest.fixture
def no_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """The checkout's round, made unreadable: a call to it fails the test."""

    def read() -> None:
        raise AssertionError("the checkout's round was read although tags were set")

    monkeypatch.setattr(telemetry, "_product_revision", read)


def test_the_row_carries_the_tags_under_run_tags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_revision: None
) -> None:
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, json.dumps(TAGS))

    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert row[telemetry.RUN_TAGS_KEY] == TAGS
    # A set variable is the whole answer: the checkout is not also asked.
    assert "round" not in row
    assert "product_sha256" not in row
    assert "revision_error" not in row


def test_the_failing_row_carries_the_tags_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_revision: None
) -> None:
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, json.dumps(TAGS))
    sink = tmp_path / "journal" / "agent-a.jsonl"

    def refused() -> Completion:
        raise ConnectionRefusedError("nobody home")

    with pytest.raises(ConnectionRefusedError):
        _record(sink, refused)

    (row,) = fold(path=sink)
    assert row["ok"] is False
    assert row[telemetry.RUN_TAGS_KEY] == TAGS


def test_a_credential_in_a_tag_is_scrubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_revision: None
) -> None:
    monkeypatch.setenv(
        telemetry.RUN_TAGS_ENV,
        json.dumps({"mirror": "https://me:hunter2@example.org/x"}),
    )

    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert "hunter2" not in json.dumps(row)
    assert row[telemetry.RUN_TAGS_KEY]["mirror"].startswith("https://")


def test_an_empty_object_tags_nothing_and_reads_no_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_revision: None
) -> None:
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, "{}")

    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert telemetry.RUN_TAGS_KEY not in row
    assert "round" not in row


def test_unset_or_empty_tags_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telemetry, "_product_revision", lambda: None)
    monkeypatch.delenv(telemetry.RUN_TAGS_ENV, raising=False)
    assert telemetry.RUN_TAGS_KEY not in _record(tmp_path / "a" / "agent-a.jsonl")

    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, "")
    assert telemetry.RUN_TAGS_KEY not in _record(tmp_path / "b" / "agent-a.jsonl")


@pytest.mark.parametrize(
    ("value", "says"),
    [
        ("round=r7", "not JSON"),
        ('["r7"]', "not a JSON object"),
        ('"r7"', "not a JSON object"),
        ('{"round": null}', "round"),
        ('{"round": ["r7"]}', "round"),
        ('{"round": {"id": "r7"}}', "round"),
        ('{"": "r7"}', "empty"),
        ('{"round": "r7", "round": "r8"}', "twice"),
        ('{"ratio": NaN}', "ratio"),
        ('{"ratio": Infinity}', "ratio"),
        (json.dumps({"blob": "x" * 5000}), "bytes"),
    ],
)
def test_anything_but_a_small_object_of_scalars_is_refused(
    value: str, says: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, value)

    with pytest.raises(telemetry.RunTagsError) as refused:
        telemetry.run_tags()

    assert telemetry.RUN_TAGS_ENV in str(refused.value)
    assert says in str(refused.value)


def test_a_refused_variable_still_leaves_its_one_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly one record per call: the refusal is a row, then a raise."""
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, "round=r7")
    sink = tmp_path / "journal" / "agent-a.jsonl"
    ran: list[bool] = []

    def attempt() -> Completion:
        ran.append(True)
        return _completion()

    with pytest.raises(telemetry.RunTagsError):
        _record(sink, attempt)

    assert not ran, "the attempt ran under tags that were refused"
    (row,) = fold(path=sink)
    assert row["record_kind"] == ATTEMPT_KIND
    assert row["error"] == "RunTagsError"
    assert "prompt_sha256" in row


def test_mcgyvr_run_refuses_malformed_tags_before_it_starts(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Asked before the run, as an unwritable journal is: one line, exit 1."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    ours = tmp_path / "corpus"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, "round=r7")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    err = capsys.readouterr().err
    assert f"error: {telemetry.RUN_TAGS_ENV}" in err, err
    assert lj.rows(ours) == []


def test_mcgyvr_run_journals_the_tags(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    ours = tmp_path / "corpus"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    monkeypatch.setenv(telemetry.RUN_TAGS_ENV, json.dumps(TAGS))

    assert lj.main(lj.run_args(contract, repo, config)) == 0

    (row,) = lj.rows(ours)
    assert row[telemetry.RUN_TAGS_KEY] == TAGS


_OUTSIDE = """
import json
from pathlib import Path
import mcgyvr
from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

completion = Completion(
    text="x", stop_reason=StopReason.COMPLETE, raw_stop_reason="stop",
    model="m", source="workstation", protocol=Protocol.OPENAI,
    max_output_tokens=8, latency_s=0.0,
)
sink = Path(SINK)
observe(
    lambda: completion, path=sink, attempt_id="a:1", orchestrator="a", rung="r",
    messages=[{"role": "user", "content": "u"}],
)
(row,) = fold(path=sink)
print(json.dumps({"file": mcgyvr.__file__, "row": row}))
"""


@pytest.mark.parametrize("tagged", [False, True], ids=["no-env", "env"])
def test_outside_the_checkout_only_the_environment_tags_a_row(
    tmp_path: Path, tagged: bool
) -> None:
    """The package alone, with no development checkout around it: a wheel.

    A copy of ``src/mcgyvr`` on ``PYTHONPATH`` ahead of the editable install;
    ``cwd`` is the copy too, so nothing resolves the checkout. With no variable
    the row carries no tags and no round; with one, it carries the tags.
    """
    site = tmp_path / "elsewhere" / "src"
    shutil.copytree(
        REPO / "src" / "mcgyvr",
        site / "mcgyvr",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    sink = tmp_path / "journal" / "a.jsonl"
    env = {**os.environ, "PYTHONPATH": str(site)}
    env.pop(telemetry.RUN_TAGS_ENV, None)
    if tagged:
        env[telemetry.RUN_TAGS_ENV] = json.dumps(TAGS)
    proc = subprocess.run(
        [sys.executable, "-c", _OUTSIDE.replace("SINK", repr(str(sink)))],
        env=env,
        cwd=site.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert Path(out["file"]).is_relative_to(site), out["file"]
    row = out["row"]
    assert "round" not in row
    assert "product_sha256" not in row
    if tagged:
        assert row[telemetry.RUN_TAGS_KEY] == TAGS
    else:
        assert telemetry.RUN_TAGS_KEY not in row


def test_the_setup_document_names_the_variable_and_the_key() -> None:
    """One description, in the schema the setup document is rendered from."""
    (journal,) = (field for field in configlib.SCHEMA if field.name == "journal")
    assert f"`{telemetry.RUN_TAGS_ENV}`" in journal.doc
    assert f"`{telemetry.RUN_TAGS_KEY}`" in journal.doc
    assert str(telemetry.RUN_TAGS_MAX_BYTES) in journal.doc
