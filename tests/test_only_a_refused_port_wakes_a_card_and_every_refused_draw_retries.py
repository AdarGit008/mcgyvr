"""Only a refused port wakes a card, and every draw it refused is sent again.

The wake signal is the instant refusal a card with nothing listening gives
(:mod:`mcgyvr.wake`). Two defects sat either side of it:

* Any :class:`~mcgyvr.runner.TransportError` woke the card, a read timeout on a
  card that is up included. A slow generation then started a door run and a
  second full generation, neither charged as an attempt.
* The waker held one lock for the whole door run. A second draw refused by the
  same card waited on it, found the card already woken, and re-raised its
  refusal although the card was now up — so it failed after a wake that worked.

Both go through the real ``runner._post_json`` against sockets on this machine,
so the refusal and the timeout are the ones the transport really produces.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

import mcgyvr.wake as wake
from mcgyvr.config import load
from mcgyvr.runner import TransportError, _post_json
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import (
    RUNG_3B,
    compose_dir,
    config_file,
)


@pytest.fixture
def waker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> wake.Waker:
    (tmp_path / "rendezvous").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    path = config_file(
        tmp_path / "mcgyvr.yaml",
        journal=tmp_path / "journal",
        specs=compose_dir(tmp_path, with_spec=True),
        switch=True,
        profile="dev",
    )
    made = wake.for_config(load(path))
    assert made is not None
    return made


@pytest.fixture
def closed_port() -> int:
    """A port on this machine with nothing listening: a sleeping card."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port: int = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture
def silent_port() -> Iterator[int]:
    """A port that accepts a connection and never answers: a busy card."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port: int = listener.getsockname()[1]
    try:
        yield port
    finally:
        listener.close()


def _door(
    monkeypatch: pytest.MonkeyPatch, *, seconds: float
) -> tuple[list[Sequence[str]], threading.Event]:
    spawned: list[Sequence[str]] = []
    up = threading.Event()

    def spawn(argv: Sequence[str], **_: object) -> int:
        spawned.append(list(argv))
        time.sleep(seconds)
        up.set()
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return spawned, up


def test_a_read_timeout_on_a_card_that_is_up_is_raised_and_wakes_nothing(
    waker: wake.Waker, silent_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned, _ = _door(monkeypatch, seconds=0.0)
    sent: list[int] = []

    def send() -> dict[str, object]:
        sent.append(1)
        return _post_json(f"http://127.0.0.1:{silent_port}/v1", {}, {}, 0.3)

    with pytest.raises(TransportError):
        waker.dispatching(RUNG_3B, send)

    assert spawned == [], "a timeout on a live card started a door run"
    assert len(sent) == 1, "a timed-out generation was sent a second time"


def test_every_draw_one_sleeping_card_refused_is_sent_again_after_one_wake(
    waker: wake.Waker, closed_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned, up = _door(monkeypatch, seconds=0.5)
    refused = threading.Barrier(2, timeout=5.0)

    def send() -> str:
        if up.is_set():
            return "answered"
        try:
            _post_json(f"http://127.0.0.1:{closed_port}/v1", {}, {}, 1.0)
        finally:
            refused.wait()
        raise AssertionError("nothing listens on the closed port")

    results: list[str] = []
    errors: list[BaseException] = []

    def draw() -> None:
        try:
            results.append(waker.dispatching(RUNG_3B, send))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=draw) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert len(spawned) == 1, f"the door ran {len(spawned)} times for one card"
    assert errors == [], f"a draw failed after the card was woken: {errors}"
    assert results == ["answered", "answered"]
