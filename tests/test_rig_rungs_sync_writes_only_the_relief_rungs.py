"""``mcgyvr rig rungs sync`` keeps the hub's relief rungs, and touches nothing else.

The hub matches this rider to other people's open slots (hitchhike) and lists
them at ``/api/v1/me/rungs``; the sync ``POST``s the rider's ladder there (what
it holds is the business of
``tests/test_a_sync_reports_the_riders_ladder_and_nothing_else.py``) and reads
the same listing back. The sync asks with the rider's *personal*
key — read from a variable whose NAME it is told (``MCGYVR_HUB_API_KEY`` when
it is told none), never the rig token, never printed and never written — and
writes the answer whole into ``relief.yaml`` beside the setup: one relief rung
per listed rung, each naming that variable as its ``api_key_env``. A rung the
hub no longer lists is gone after the next sync. ``fleet.yaml`` and
``policy.yaml`` are not touched. The hub's privacy warning is shown every time.

The hub is the one :mod:`mcgyvr.rig.verbs` keeps for this machine unless one
is named, and the key goes to it only over ``https://``, or ``http://`` on this
machine: the rule the rig token is held to, read from the same place. Every
address a rung names is held to it as well, and must be the hub's own — the
key is sent there.

The hub's answer is hostile until read. A response this client cannot read
whole — a field of the wrong type or size, a model outside the pattern, a
width under one, a position the contract does not name, an id twice, a rung
on another host — is refused whole: nothing is written, and the relief rungs
already kept stay as they were. A hub that half-speaks the contract is not
trusted for the half it seems to get right.

Every hub here is a loopback server this test starts.
"""

from __future__ import annotations

import contextlib
import copy
import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

HANDLE = "bob"
KEY = "mhu_0123456789abcdef_" + "k" * 40
TOKEN = "mhr_0123456789abcdef_" + "t" * 43
FIRST = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"
SECOND = "1a2b3c4d5e6f708192a3b4c5d6e7f809"
PRIVACY = (
    "Riding sends your prompts to other people's machines: the host of each "
    "rung runs the model on hardware they control and can read your prompts "
    "and the answers. Ride only with prompts you would show them."
)
FLEET = """\
# what runs where
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
"""
POLICY = """\
# my own ladder, commented by hand
ladder: [local_fast]
fanout: idle
"""


def rung(
    rung_id: str, address: str, *, position: str = "below_floor"
) -> dict[str, Any]:
    return {
        "id": rung_id,
        "host": HANDLE,
        "address": address,
        "model": f"hitchhike@{rung_id}",
        "served_model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
        "width": 2,
        "relief": True,
        "position": position,
        "price": {
            "currency": "credits",
            "per_tokens": 1000,
            "input": "0.5",
            "output": "1",
        },
    }


class Hub:
    """What the loopback hub answers, and what it was asked."""

    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = b""
        self.asked: list[dict[str, Any]] = []
        self.address = ""

    def answer(self, document: object, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(document).encode()

    def listing(self, *rung_ids: str, ride: bool = True) -> dict[str, Any]:
        return {
            "ride": ride,
            "privacy": PRIVACY,
            "refresh_s": 60,
            "rungs": [rung(i, f"{self.address}/v1") for i in rung_ids],
        }


@contextlib.contextmanager
def serving(hub: Hub) -> Iterator[Hub]:
    class _Hub(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            hub.asked.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "content_type": self.headers.get("Content-Type"),
                    "body": self.rfile.read(length),
                }
            )
            self.send_response(hub.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(hub.body)))
            self.end_headers()
            self.wfile.write(hub.body)

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Hub)
    hub.address = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield hub
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (folder / "policy.yaml").write_text(POLICY, encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(folder))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "config-folder"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data-folder"))
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    return folder


@pytest.fixture
def hub(setup: Path) -> Iterator[Hub]:
    from mcgyvr.rig import credentials

    with serving(Hub()) as running:
        credentials.save(credentials.Credentials(hub=running.address, token=TOKEN))
        yield running


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(["rig", "rungs", "sync", *argv])


def relief(setup: Path) -> dict[str, Any]:
    from mcgyvr.config import load

    return {name: unit for name, unit in load(setup).relief.items()}


# --- what a sync writes --------------------------------------------------------


def test_a_sync_keeps_each_rung_the_hub_lists_as_a_relief_rung(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli() == 0

    (only,) = relief(setup).values()
    assert only.name == f"hitchhike-{FIRST}"
    assert only.relief is True
    assert only.address == f"{hub.address}/v1"
    assert only.model == f"hitchhike@{FIRST}"
    assert only.api_key_env == "MCGYVR_HUB_API_KEY"
    assert only.width == 2
    assert only.position == "below_floor"
    assert only.hosted_by == "bob"
    assert only.served_model == "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"


def test_a_sync_asks_with_the_personal_key_and_never_shows_or_keeps_it(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli() == 0

    (asked,) = hub.asked
    assert asked["path"] == "/api/v1/me/rungs"
    assert asked["authorization"] == f"Bearer {KEY}"
    out = capsys.readouterr()
    written = (setup / "relief.yaml").read_text(encoding="utf-8")
    for text in (out.out, out.err, written):
        assert KEY not in text and "k" * 40 not in text


def test_a_sync_shows_the_hubs_privacy_warning(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli() == 0

    assert PRIVACY in capsys.readouterr().out


def test_a_sync_touches_neither_the_fleet_nor_the_policy(setup: Path, hub: Hub) -> None:
    hub.answer(hub.listing(FIRST, SECOND))

    assert cli() == 0

    assert (setup / "fleet.yaml").read_text(encoding="utf-8") == FLEET
    assert (setup / "policy.yaml").read_text(encoding="utf-8") == POLICY
    assert sorted(path.name for path in setup.iterdir()) == [
        "fleet.yaml",
        "policy.yaml",
        "relief.yaml",
    ]


def test_a_rung_the_hub_no_longer_lists_is_gone_after_the_next_sync(
    setup: Path, hub: Hub
) -> None:
    hub.answer(hub.listing(FIRST, SECOND))
    assert cli() == 0
    assert sorted(relief(setup)) == [f"hitchhike-{FIRST}", f"hitchhike-{SECOND}"]

    hub.answer(hub.listing(SECOND))
    assert cli() == 0
    assert sorted(relief(setup)) == [f"hitchhike-{SECOND}"]


def test_a_rider_who_does_not_ride_keeps_no_relief_rung(setup: Path, hub: Hub) -> None:
    hub.answer(hub.listing(FIRST))
    assert cli() == 0

    hub.answer(hub.listing(ride=False))
    assert cli() == 0

    assert relief(setup) == {}


def test_the_keys_variable_is_named_by_the_rider(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MCGYVR_HUB_API_KEY")
    monkeypatch.setenv("MY_HUB_KEY", KEY)
    hub.answer(hub.listing(FIRST))

    assert cli("--key-env", "MY_HUB_KEY") == 0

    assert hub.asked[0]["authorization"] == f"Bearer {KEY}"
    assert [unit.api_key_env for unit in relief(setup).values()] == ["MY_HUB_KEY"]


def test_a_named_hub_is_asked_instead_of_the_kept_one(setup: Path, hub: Hub) -> None:
    from mcgyvr.rig import credentials

    credentials.remove()
    hub.answer(hub.listing(FIRST))

    assert cli("--hub", hub.address) == 0
    assert len(hub.asked) == 1


# --- what a sync refuses ---------------------------------------------------------


def test_with_no_key_nothing_is_asked_and_the_variable_is_named(
    setup: Path,
    hub: Hub,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.exits import Exit

    monkeypatch.delenv("MCGYVR_HUB_API_KEY")

    assert cli() == Exit.ERROR
    assert "MCGYVR_HUB_API_KEY" in capsys.readouterr().err
    assert hub.asked == []


def test_with_no_hub_kept_or_named_nothing_is_asked(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    assert cli() == Exit.ERROR
    assert "--hub" in capsys.readouterr().err


@pytest.mark.parametrize("named", ["http://hub.example.com", "http://192.0.2.10:8000"])
def test_the_key_is_never_sent_in_clear_past_this_machine(
    setup: Path, named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    assert cli("--hub", named) == Exit.REFUSED
    assert "https://" in capsys.readouterr().err
    assert not (setup / "relief.yaml").exists()


def test_a_folder_with_no_setup_is_not_written_into(
    tmp_path: Path, setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.exits import Exit

    empty = tmp_path / "not-a-setup"
    empty.mkdir()
    monkeypatch.setenv("MCGYVR_CONFIG", str(empty))
    hub.answer(hub.listing(FIRST))

    assert cli() == Exit.ERROR
    assert list(empty.iterdir()) == []


def test_a_hub_that_refuses_the_key_is_said_and_nothing_is_written(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    hub.answer({"detail": "invalid or missing token"}, status=401)

    assert cli() == Exit.REFUSED
    assert "401" in capsys.readouterr().err
    assert not (setup / "relief.yaml").exists()


Mutation = Callable[[dict[str, Any]], object]


def _set(key: str, value: object) -> Mutation:
    def mutate(document: dict[str, Any]) -> object:
        document["rungs"][0][key] = value
        return document

    return mutate


def _top(key: str, value: object) -> Mutation:
    def mutate(document: dict[str, Any]) -> object:
        document[key] = value
        return document

    return mutate


def _drop(key: str) -> Mutation:
    def mutate(document: dict[str, Any]) -> object:
        del document["rungs"][0][key]
        return document

    return mutate


def _twice(document: dict[str, Any]) -> object:
    document["rungs"].append(copy.deepcopy(document["rungs"][0]))
    return document


def _many(document: dict[str, Any]) -> object:
    template = document["rungs"][0]
    document["rungs"] = [
        {**template, "id": f"{n:032x}", "model": f"hitchhike@{n:032x}"}
        for n in range(1000)
    ]
    return document


HOSTILE: dict[str, Mutation] = {
    "not an object": lambda document: [document],
    "ride not a flag": _top("ride", "yes"),
    "rungs while not riding": _top("ride", False),
    "privacy missing": lambda document: {
        k: v for k, v in document.items() if k != "privacy"
    },
    "privacy not text": _top("privacy", 7),
    "refresh not positive": _top("refresh_s", 0),
    "refresh a flag": _top("refresh_s", True),
    "rungs not a list": _top("rungs", {"a": 1}),
    "too many rungs": _many,
    "a rung not an object": _top("rungs", ["hitchhike"]),
    "id not hex": _set("id", "Z" * 32),
    "id twice": _twice,
    "model outside the pattern": _set("model", "hitchhike@x y"),
    "model not this rung's": _set("model", f"hitchhike@{SECOND}"),
    "width zero": _set("width", 0),
    "width a flag": _set("width", True),
    "width text": _set("width", "2"),
    "relief false": _set("relief", False),
    "position unknown": _set("position", "beside"),
    "position missing": _drop("position"),
    "host not text": _set("host", ["bob"]),
    "host too long": _set("host", "b" * 1000),
    "served model too long": _set("served_model", "m" * 1000),
    "address on another host": _set("address", "https://elsewhere.example.org/v1"),
    "address carrying credentials": _set("address", "http://me:secret@127.0.0.1:1/v1"),
    "address not a url": _set("address", "nonsense"),
}


@pytest.mark.parametrize("mutate", HOSTILE.values(), ids=HOSTILE.keys())
def test_a_response_this_client_cannot_read_whole_is_refused_whole(
    setup: Path, hub: Hub, mutate: Mutation, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    hub.answer(hub.listing(SECOND))
    assert cli() == 0
    kept = (setup / "relief.yaml").read_bytes()

    hub.answer(mutate(hub.listing(FIRST)))
    assert cli() == Exit.REFUSED

    assert (setup / "relief.yaml").read_bytes() == kept
    assert "refused" in capsys.readouterr().err


def test_an_answer_that_is_not_json_is_refused(setup: Path, hub: Hub) -> None:
    from mcgyvr.exits import Exit

    hub.status, hub.body = 200, b"<html>gateway</html>"

    assert cli() == Exit.REFUSED
    assert not (setup / "relief.yaml").exists()


def test_an_answer_too_large_to_be_a_listing_is_refused(setup: Path, hub: Hub) -> None:
    from mcgyvr.exits import Exit

    document = hub.listing(FIRST)
    document["privacy"] = "p" * 2_000_000
    hub.answer(document)

    assert cli() == Exit.REFUSED
    assert not (setup / "relief.yaml").exists()


def test_a_rung_address_in_clear_past_this_machine_is_refused() -> None:
    """The rule the key is held to, for every address the sync would write."""
    from mcgyvr.rig import rungs

    document = {
        "ride": True,
        "privacy": PRIVACY,
        "refresh_s": 60,
        "rungs": [rung(FIRST, "http://hub.example.org/v1")],
    }

    with pytest.raises(rungs.HubAnswerError, match="https://"):
        rungs.read(document, "https://hub.example.org")
