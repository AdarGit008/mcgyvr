"""Ctrl-C hangs up on every dispatch in flight before it stops the command.

A command interrupted mid-answer — a run killed at the keyboard, a facade
server stopped — left its units decoding: a dispatch runs on a thread of a
batch, and ``KeyboardInterrupt`` is the main thread's alone, which then waits
for the batch's threads to finish what they were asked. Now the command line
hangs up on every dispatch of the process first (:func:`mcgyvr.runner.hang_up_all`:
each unit's connection shut down, each dispatch ended, none made after), then
stops as Ctrl-C always stopped it: the same ``KeyboardInterrupt`` from the
same place, so every command's own handling of it is as it was. The hang-up
is on the interrupt itself, not after the command returns, since the command
is what waits. Only Python's own handler is replaced, only while a command
runs, and only on the main thread, where a signal is heard.
"""

from __future__ import annotations

import signal
import threading

import pytest

from mcgyvr import cli, runner


@pytest.fixture
def hung_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(runner, "hang_up_all", lambda: calls.append("hang_up_all"))
    return calls


def test_an_interrupt_hangs_up_on_every_dispatch_then_is_the_interrupt_it_was(
    hung_up: list[str],
) -> None:
    before = signal.getsignal(signal.SIGINT)
    with cli.hanging_up_on_interrupt():
        assert signal.getsignal(signal.SIGINT) is not before
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGINT)
    assert hung_up == ["hang_up_all"]
    assert signal.getsignal(signal.SIGINT) is before


def test_a_handler_someone_else_installed_is_left_alone(
    hung_up: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An embedding process that handles the signal its own way keeps it."""
    heard: list[int] = []
    theirs = signal.signal(signal.SIGINT, lambda signum, frame: heard.append(signum))
    try:
        with cli.hanging_up_on_interrupt():
            signal.raise_signal(signal.SIGINT)
    finally:
        signal.signal(signal.SIGINT, theirs)
    assert heard == [signal.SIGINT]
    assert hung_up == []


def test_off_the_main_thread_nothing_is_installed(hung_up: list[str]) -> None:
    before = signal.getsignal(signal.SIGINT)
    seen: list[object] = []

    def run() -> None:
        with cli.hanging_up_on_interrupt():
            seen.append(signal.getsignal(signal.SIGINT))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=5.0)
    assert seen == [before]
    assert signal.getsignal(signal.SIGINT) is before


def test_every_command_runs_under_it(
    hung_up: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main`` is the one way in, so the handler is on for whatever runs."""
    import argparse

    def command(args: argparse.Namespace) -> int:
        signal.raise_signal(signal.SIGINT)
        return 0  # pragma: no cover - the interrupt is raised first

    def build() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        hang = sub.add_parser("hang")
        hang.set_defaults(func=command)
        return parser, hang

    monkeypatch.setattr(cli, "_build", build)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["hang"])
    assert hung_up == ["hang_up_all"]
