"""The run headers: intent, in a home that outlives the campaign that asked.

`run.json` records what a run WAS. Nothing recorded what a run is FOR — not the
question, not what it could have carried, not what was left on the table — and
D7's intent survived only as prose `_doc` keys in a config, a three-tuple of
shell commands in `launch.py`, and a dated evidence directory that would have
taken the questions with it. #322 decided the gate; #330 is the half that is
not the gate, and these are its checks.

Two of them are worth naming for what they refuse rather than what they assert.
:func:`test_a_header_carries_no_key_the_spine_does_not_name` is why free text
cannot leak into the aggregatable layer: prose goes under `notes` or nowhere,
because open questions dispersed over 147 session records is the state this
record type exists to leave behind. And
:func:`test_the_field_review_is_owed_once_ten_run_headers_exist` is the closing
condition made mechanical — a gate left open with no review date states no
property (ADR-0026 lens 3), so the owed state is a non-zero exit rather than a
line in a record somebody has to remember to read.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


headers = _by_path("bench_headers", REPO / "tools" / "bench" / "headers.py")

#: The twelve seed questions #330 files, by id. The four D6 constants
#: (README:652-655), the four "Decision owed" blocks (README:48, 115, 150, 363)
#: and one per bucket-B/C sibling issue.
D6_CONSTANTS = (
    "2026-08-21-start-timeout-s",
    "2026-08-21-digest-timeout-s",
    "2026-08-21-load-attempts",
    "2026-08-21-ramp-repeats",
)
OWED_BLOCKS = (
    "2026-08-21-owed-line-48",
    "2026-08-21-owed-line-115",
    "2026-08-21-owed-line-150",
    "2026-08-21-owed-line-363",
)
SIBLINGS = {
    "2026-08-21-issue-325": "#325",
    "2026-08-21-issue-326": "#326",
    "2026-08-21-issue-327": "#327",
    "2026-08-21-issue-328": "#328",
}


def _write(home: Path, stem: str, **fields: Any) -> Path:
    path = home / f"{stem}.json"
    path.write_text(
        json.dumps({"record": headers.RECORD, "id": stem, **fields}), encoding="utf-8"
    )
    return path


def test_every_header_on_disk_is_a_run_header_with_a_question() -> None:
    """Four fields, and v1 asks for nothing else.

    Requiring more now would be inventing the shape before seeing the things it
    has to describe, which is the mistake #322 was rewritten to avoid.
    """
    found = headers.headers(headers.HOME)
    assert found, f"no header under {headers.HOME}"
    for path, header in found:
        assert header.get("record") == headers.RECORD, path
        assert header.get("id") == path.stem, path
        assert headers._DATE.match(str(header.get("declared", ""))), path
        question = header.get("question")
        assert isinstance(question, str) and question.strip(), path
        assert headers.problems(header, path) == [], path


def test_a_header_carries_no_key_the_spine_does_not_name(tmp_path: Path) -> None:
    """Prose goes under `notes`, so free text cannot enter the spine."""
    for path, header in headers.headers(headers.HOME):
        stray = sorted(set(header) - set(headers.KEYS))
        assert not stray, f"{path.name} carries {stray}"

    refused = _write(
        tmp_path,
        "2026-08-21-loose",
        declared="2026-08-21",
        question="does a stray key get in?",
        rationale="a paragraph that no listing can aggregate",
    )
    assert any(
        "not a key the spine names" in problem
        for problem in headers.problems(headers.load(refused), refused)
    )


def test_an_unknown_field_says_what_was_searched(tmp_path: Path) -> None:
    """An agent asked for a number it cannot source will produce one.

    `{"unknown": true, "searched": [...]}` is how it says it looked, and the
    rule reaches nested values too: an unknown buried two levels down makes the
    same claim as one at the top.
    """
    for path, header in headers.headers(headers.HOME):
        for field in headers.unknown_fields(header):
            value: Any = header
            for step in field.split("."):
                value = value[step]
            assert value.get("searched"), f"{path.name}: {field} searched nothing"

    bare = _write(
        tmp_path,
        "2026-08-21-bare",
        declared="2026-08-21",
        question="q",
        cost="unknown",
    )
    assert any(
        "bare string" in problem
        for problem in headers.problems(headers.load(bare), bare)
    )

    silent = _write(
        tmp_path,
        "2026-08-21-silent",
        declared="2026-08-21",
        question="q",
        cost={"unknown": True},
    )
    assert any(
        "names nothing it searched" in problem
        for problem in headers.problems(headers.load(silent), silent)
    )

    nested = _write(
        tmp_path,
        "2026-08-21-nested",
        declared="2026-08-21",
        question="q",
        left_on_table={"price": {"unknown": True, "searched": []}},
    )
    assert any(
        "left_on_table.price" in problem
        for problem in headers.problems(headers.load(nested), nested)
    )

    honest = _write(
        tmp_path,
        "2026-08-21-honest",
        declared="2026-08-21",
        question="q",
        cost={"unknown": True, "searched": ["tools/bench/rate-card.json"]},
    )
    assert headers.problems(headers.load(honest), honest) == []


def test_a_header_declared_after_its_run_says_so(tmp_path: Path) -> None:
    """A header written after the fact is a different thing from a declaration.

    #322's whole mechanism is that compiling a header BEFORE a run makes the
    agent look things up. A retroactive header is worth keeping and must not be
    counted as evidence that the gate was used.
    """
    late = _write(
        tmp_path,
        "2026-08-19-late",
        declared="2026-08-21",
        question="q",
        run={"started": "2026-08-19T19:31"},
    )
    assert any(
        "retroactive" in problem
        for problem in headers.problems(headers.load(late), late)
    )

    owned = _write(
        tmp_path,
        "2026-08-19-owned",
        declared="2026-08-21",
        question="q",
        retroactive=True,
        run={"started": "2026-08-19T19:31"},
    )
    assert headers.problems(headers.load(owned), owned) == []

    same_day = _write(
        tmp_path,
        "2026-08-19-same-day",
        declared="2026-08-19",
        question="q",
        run={"started": "2026-08-19T19:31"},
    )
    assert headers.problems(headers.load(same_day), same_day) == []


def test_the_listing_counts_only_headers_that_carry_a_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A question is a header. Only a header with a run counts toward ten.

    Otherwise the review could be reached by filing questions, which is the one
    thing that costs nothing — and the review exists to read fields that real
    runs filled in.
    """
    assert headers.REVIEW_AFTER == 10
    on_disk = headers.headers(headers.HOME)
    with_run = [path for path, header in on_disk if headers.started(header) is not None]
    without = [path for path, header in on_disk if headers.started(header) is None]
    assert with_run and without, "this check needs one of each to mean anything"

    assert headers.main(["list"]) == 0
    printed = capsys.readouterr().out.splitlines()
    for path, _ in on_disk:
        assert any(line.startswith(path.stem) for line in printed), path
    assert printed[-1] == (
        f"{len(with_run)} of {headers.REVIEW_AFTER} run headers before the field review"
    )


def test_the_field_review_is_owed_once_ten_run_headers_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The owed state is code, not memory.

    Ten headers with a run and no `run-header/2` on disk is a non-zero exit and
    a line saying so. The schema's existence clears it, because a review is
    finished when it has produced one — not when someone says it is.
    """
    home = tmp_path / "headers"
    home.mkdir()
    schema = tmp_path / "record.run-header.schema.json"
    for index in range(headers.REVIEW_AFTER):
        _write(
            home,
            f"2026-08-{index + 1:02d}-run",
            declared=f"2026-08-{index + 1:02d}",
            question=f"run {index}",
            run={"started": f"2026-08-{index + 1:02d}T10:00"},
        )

    assert headers.main(["list", "--home", str(home), "--schema", str(schema)]) == 1
    owed = capsys.readouterr().out
    assert "review owed" in owed, owed
    assert f"{headers.REVIEW_AFTER} of {headers.REVIEW_AFTER}" in owed

    schema.write_text('{"record": "run-header/2"}', encoding="utf-8")
    assert headers.main(["list", "--home", str(home), "--schema", str(schema)]) == 0
    assert "review owed" not in capsys.readouterr().out


def test_the_d7_header_is_on_disk_and_passes_the_schema() -> None:
    """The first header, written retroactively from the campaign's own files.

    Its cost points at the log rather than restating it: a number copied out of
    an artifact is a number that can drift from it.
    """
    path = headers.HOME / "2026-08-19-d7-campaign.json"
    header = headers.load(path)
    assert headers.problems(header, path) == []
    assert header["retroactive"] is True
    assert header["run"]["started"] == "2026-08-19T19:31"
    source = header["cost"]["source"]
    assert source == "records/evidence/calibration-2026-08-19/d7-campaign.log"
    assert (REPO / source).exists(), "the cost points at a file that is not there"


def test_the_seed_questions_are_on_disk_and_pass_the_schema() -> None:
    """Twelve questions that were living inside a dated evidence directory.

    The sibling headers point and never restate: the issue is the record of
    truth for its instruments and its conflicts, and a second copy here would
    be a second thing to keep true.
    """
    for stem in D6_CONSTANTS + OWED_BLOCKS + tuple(SIBLINGS):
        path = headers.HOME / f"{stem}.json"
        assert path.exists(), f"{stem} is not on disk"
        header = headers.load(path)
        assert headers.problems(header, path) == [], stem
        assert headers.started(header) is None, f"{stem} is a question, not a run"

    for stem in OWED_BLOCKS:
        answered = headers.load(headers.HOME / f"{stem}.json")["answered_by"]
        assert any(f"D{n}" in answered for n in range(1, 6)), (stem, answered)

    for stem, issue in SIBLINGS.items():
        header = headers.load(headers.HOME / f"{stem}.json")
        assert header["answered_by"] == issue
        assert set(header) == set(headers.REQUIRED) | {"answered_by", "notes"}, stem
