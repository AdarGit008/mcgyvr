"""A readings file of your own links that cannot be read is refused by name.

The user's reading of their link outranks the estimate, so a file that holds
one must never be read as "no reading": the estimate would then answer for a
link the user has measured. A file that is not there is no reading; any other
file that cannot be read, or states something that cannot be a link, is refused
with its path and what is wrong, for a read of a link and for the next reading
alike, and a reading is never written over a file that cannot be read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.fleet import links
from mcgyvr.serving import interconnect
from tests import link_fixture as lf


@pytest.fixture(autouse=True)
def _own_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lf.own_folders(tmp_path, monkeypatch)


def _reading(**changes: object) -> dict[str, object]:
    made: dict[str, object] = {
        "gib_s": 3.0,
        "latency_us": 50.0,
        "how": "by hand",
        "at": "t",
        "between": [lf.HOST_A, lf.HOST_B],
    }
    made.update(changes)
    return made


def _write(text: str) -> Path:
    path = interconnect.readings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _document(**classes: object) -> str:
    return json.dumps({"schema": 1, "links": classes})


def test_a_file_that_is_not_there_is_no_reading() -> None:
    assert interconnect.link(links.NETWORK).source == "estimate"


def test_a_file_that_is_not_json_is_refused_by_name() -> None:
    path = _write("{ not json")
    with pytest.raises(interconnect.InterconnectError, match="not valid JSON") as was:
        interconnect.link(links.NETWORK)
    assert str(path) in str(was.value)


def test_a_file_that_is_not_utf8_text_is_refused_by_name() -> None:
    path = interconnect.readings_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(interconnect.InterconnectError, match="UTF-8") as was:
        interconnect.link(links.NETWORK)
    assert str(path) in str(was.value)


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        json.dumps({"links": {}}),
        json.dumps({"schema": 2, "links": {}}),
        json.dumps({"schema": 1}),
        json.dumps({"schema": 1, "links": []}),
    ],
)
def test_a_file_of_another_shape_is_refused_by_name(text: str) -> None:
    path = _write(text)
    with pytest.raises(interconnect.InterconnectError) as was:
        interconnect.link(links.NETWORK)
    assert str(path) in str(was.value)


@pytest.mark.parametrize(
    ("classes", "named"),
    [
        ({lf.HOST_A: _reading()}, lf.HOST_A),
        ({links.NETWORK: "fast"}, links.NETWORK),
        ({links.NETWORK: _reading(gib_s=0)}, "gib_s"),
        ({links.NETWORK: _reading(gib_s=-1.0)}, "gib_s"),
        ({links.NETWORK: _reading(gib_s="3")}, "gib_s"),
        ({links.NETWORK: _reading(gib_s=True)}, "gib_s"),
        ({links.NETWORK: _reading(latency_us=None)}, "latency_us"),
        ({links.NETWORK: _reading(how="")}, "how"),
        ({links.NETWORK: _reading(at=3)}, "at"),
        ({links.NETWORK: _reading(between=[lf.HOST_A])}, "between"),
        ({links.NETWORK: _reading(between="a,b")}, "between"),
    ],
)
def test_a_reading_that_cannot_be_a_link_is_refused_by_name(
    classes: dict[str, object], named: str
) -> None:
    path = _write(_document(**classes))
    with pytest.raises(interconnect.InterconnectError, match=named) as was:
        interconnect.link(links.PCIE)
    assert str(path) in str(was.value)


@pytest.mark.parametrize("spelled", ["NaN", "Infinity", "-Infinity"])
def test_a_reading_that_is_not_a_finite_number_is_refused_by_name(spelled: str) -> None:
    text = json.dumps({"schema": 1, "links": {links.NETWORK: _reading(gib_s=1)}})
    path = _write(text.replace('"gib_s": 1', f'"gib_s": {spelled}'))
    with pytest.raises(interconnect.InterconnectError, match="gib_s") as was:
        interconnect.link(links.NETWORK)
    assert str(path) in str(was.value)


def test_a_new_reading_is_not_written_over_a_file_that_cannot_be_read() -> None:
    path = _write("{ not json")
    with pytest.raises(interconnect.InterconnectError):
        interconnect.read_link(lf.HOST_A, lf.HOST_B, lf.reader, how="x", at="t")
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_a_well_formed_file_is_read_as_the_reading_it_holds() -> None:
    _write(_document(**{links.NETWORK: _reading(gib_s=2.5, latency_us=80.0)}))
    answer = interconnect.link(links.NETWORK)
    assert (answer.gib_s, answer.latency_us, answer.source) == (2.5, 80.0, "reading")
