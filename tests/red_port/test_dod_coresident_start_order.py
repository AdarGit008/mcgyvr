"""Two units on one card are started in an order, not at the same time.

``mcgyvr emit`` writes one compose service per serving unit and no dependency
between them, so ``docker compose up -d`` starts every unit on a host at once.
Where two of them share a GPU that is a race, and vLLM loses it in a way that
leaves no error behind: each engine sizes its KV cache from the free memory it
observes at its own startup instant, so a unit that measures the card while its
neighbour is still allocating gets a smaller cache and serves fewer concurrent
requests than it was sized for, for the life of the process.

MEASURED on srv2, 2026-09-06. Started together, the 7B unit read 1.47 GiB of
"non-torch memory" and was left with 0.89 GiB of KV cache; started alone on the
same card with the same flags it read 0.05 GiB and was left with 2.77 GiB — a
concurrency of 12.68x against 4.08x, from ordering alone. On the first attempt the
7B did not come up at all: ``Free memory on device (7.61/11.63 GiB) on startup is
less than desired GPU memory utilization (0.72, 8.37 GiB)``, and it crash-looped
under ``restart: unless-stopped`` until the units were stopped and started in
sequence by hand.

Stated as a property of the emitted file, because that is where the fix has to
live: an operator who is handed a compose file and told to run it cannot be
expected to know that two of its services must not start together. Whether the
order is expressed as ``depends_on``, a healthcheck condition or something else is
the port's choice; that the file cannot be started concurrently is the
requirement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import required


def _units_on_one_gpu(tmp_path: Path) -> dict[str, Any]:
    """The emitted compose for a host serving two models on one card."""
    write = required(
        "emit a compose file for a host whose units share one GPU",
        lambda: (
            __import__("mcgyvr.emit", fromlist=["compose_document"]).compose_document
        ),
    )
    return write(tmp_path)


def test_two_units_sharing_a_card_declare_a_start_order(tmp_path: Path) -> None:
    """One of the two waits for the other; ``compose up`` cannot race them."""
    document = _units_on_one_gpu(tmp_path)
    services = document["services"]
    assert len(services) >= 2, "this fixture is about a host with two units"
    waits = [name for name, body in services.items() if body.get("depends_on")]
    assert waits, (
        "two units on one GPU must not both start at once: no service in the "
        f"emitted file waits for another ({', '.join(sorted(services))})"
    )


def test_the_order_puts_the_larger_unit_first(tmp_path: Path) -> None:
    """The big model goes first, because it is the one that cannot recover.

    A unit that measures the card after a smaller neighbour has taken its share
    still fits; the smaller one measuring after the larger has taken its share is
    what fails to start. srv2's 7B needed 8.37 GiB free and found 7.61.
    """
    document = _units_on_one_gpu(tmp_path)
    services = document["services"]
    waiting = {
        name: set(body["depends_on"])
        for name, body in services.items()
        if body.get("depends_on")
    }
    assert waiting, "no order is declared at all"
    for name, waits_for in waiting.items():
        for other in waits_for:
            assert _weight_of(services[other]) >= _weight_of(services[name]), (
                f"{name} waits for {other}, but {other} is the smaller unit"
            )


def _weight_of(service: dict[str, Any]) -> float:
    """The utilisation a vLLM service claims, as a stand-in for its size."""
    command = service.get("command") or []
    for index, token in enumerate(command):
        if token == "--gpu-memory-utilization" and index + 1 < len(command):
            return float(command[index + 1])
    return 0.0


def test_a_host_with_one_unit_declares_no_order(tmp_path: Path) -> None:
    """An order where nothing contends is a dependency that only slows a restart."""
    single = required(
        "emit a compose file for a host with a single unit",
        lambda: (
            __import__("mcgyvr.emit", fromlist=["compose_document"]).compose_document
        ),
    )(tmp_path, units=1)
    for body in single["services"].values():
        assert not body.get("depends_on")
