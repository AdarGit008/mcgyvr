"""The invented machines come in every shape a user may have.

A product test that sizes, detects or proposes against a machine gets that
machine from :mod:`tests.machine_shapes`, the one generator of invented
machines. These promises hold the generator to four things: it offers every
kind of machine a user may bring, its machines taken together are spread over
many card sizes and counts, what it says a machine is, is what the product's
own readers make of it, and nothing of the machine the tests run on gets into
what it reports.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import re
import shutil
import subprocess
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from unittest import mock

import pytest

import tests.machine_shapes as machine_shapes
from mcgyvr import detect
from tests.machine_shapes import (
    VENDORS,
    Card,
    Holder,
    Server,
    Shape,
    card_reader_text,
    detection,
    scan,
    shape,
    shapes,
    with_server,
)

#: The labels, pinned: they are pytest ids other tests rely on, so a renamed or
#: dropped label fails here. A new shape adds its label at the end.
LABELS = (
    "bare",
    "bare-local-server",
    "bare-remote-server",
    "one-card",
    "four-equal",
    "two-sizes",
    "several-sizes",
    "busy-card",
    "busy-beside-free",
    "unreadable-size",
    "other-vendor",
    "other-vendor-no-reader",
    "mixed-vendors",
    "no-reader",
    "same-cards-here",
    "same-cards-there",
)


def _sizes(machine: Shape) -> set[int]:
    return {card.total_mib for card in machine.cards if card.total_mib is not None}


# 1. Every kind of machine is offered.


def test_the_generator_offers_every_kind_of_machine_a_user_may_bring() -> None:
    """Asserted by what the machines are, never by what they are called."""
    machines = shapes()
    kinds: dict[str, bool] = {
        "no card and no server": any(not m.cards and not m.servers for m in machines),
        "no card, a server on this machine": any(
            not m.cards and m.local and m.servers for m in machines
        ),
        "no card, a server on another machine": any(
            not m.cards and not m.local and m.servers for m in machines
        ),
        "one card": any(len(m.cards) == 1 for m in machines),
        "four equal cards": any(
            len(m.cards) == 4 and len(_sizes(m)) == 1 for m in machines
        ),
        "two cards of different sizes": any(
            len(m.cards) == 2 and len(_sizes(m)) == 2 for m in machines
        ),
        "several cards of several sizes": any(
            len(m.cards) > 2 and len(_sizes(m)) > 2 for m in machines
        ),
        "a busy card": any(card.holders for m in machines for card in m.cards),
        "a busy card beside a free one": any(
            any(c.holders for c in m.readable_cards)
            and any(not c.holders for c in m.readable_cards)
            for m in machines
        ),
        "an unreadable memory size beside a readable one": any(
            any(c.total_mib is None for c in m.cards)
            and any(c.total_mib is not None for c in m.cards)
            for m in machines
        ),
        "cards all of a vendor the reader is not for, with the card tool": any(
            m.cards
            and not m.card_reader_missing
            and not any(c.card_reader_reads for c in m.cards)
            for m in machines
        ),
        "cards all of a vendor the reader is not for, without the card tool": any(
            m.cards
            and m.card_reader_missing
            and not any(c.card_reader_reads for c in m.cards)
            for m in machines
        ),
        "two vendors mixed": any(
            len({c.vendor for c in m.cards}) > 1 for m in machines
        ),
        "cards the reader is for but no card reading tool": any(
            m.card_reader_missing and any(c.card_reader_reads for c in m.cards)
            for m in machines
        ),
        "a card that keeps memory for itself": any(
            c.reserved_mib for m in machines for c in m.readable_cards
        ),
        "the same cards here and over the network": any(
            near.local and not far.local and near.cards and near.cards == far.cards
            for near in machines
            for far in machines
        ),
    }
    missing = [kind for kind, offered in kinds.items() if not offered]
    assert not missing, f"no invented machine of these kinds: {missing}"


# 2. The machines, taken together, are spread over many sizes and counts.


def test_the_machines_together_are_spread_over_many_card_sizes_and_counts() -> None:
    """A property of the whole set, not of any one machine.

    Across the generator's machines:

    - at least five distinct card sizes appear;
    - no single size is more than half of all the cards;
    - some machine has more than two cards;
    - the machines of one or two cards between them use more than two sizes.
    """
    machines = shapes()
    every_size = [
        card.total_mib
        for m in machines
        for card in m.cards
        if card.total_mib is not None
    ]
    counts = Counter(every_size)
    assert len(counts) >= 5, f"only {len(counts)} distinct card sizes"
    size, most = counts.most_common(1)[0]
    assert most * 2 <= len(every_size), (
        f"{size} MiB is {most} of {len(every_size)} cards"
    )
    assert any(len(m.cards) > 2 for m in machines)
    small = set().union(*(_sizes(m) for m in machines if 1 <= len(m.cards) <= 2))
    assert len(small) > 2, f"the one- and two-card machines use only {sorted(small)}"


# 3. What the generator says is what the product reads.


def test_card_reader_text_answers_the_query_detection_asks() -> None:
    """The default query is detect's own: captured, not restated."""
    asked: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> str | None:
        asked.append(tuple(command))
        return None

    with mock.patch.object(detect, "_run", run):
        detect.detect_gpus()
    query = next(a for a in asked[0] if a.startswith("--query-gpu="))
    cards = shape("several-sizes").cards
    assert card_reader_text(cards) == card_reader_text(
        cards, query=query.removeprefix("--query-gpu=")
    )


def test_the_card_reader_refuses_by_name_what_it_does_not_answer() -> None:
    cards = shape("busy-card").cards
    with pytest.raises(ValueError, match="'pid'"):
        card_reader_text(cards, query="pid,used_memory")


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_detection_reports_the_cards_the_product_reader_can_read(
    machine: Shape,
) -> None:
    found = detection(machine)
    if not machine.local:
        # The helper's model, not the product's behaviour: for a machine that
        # is not local, detection() runs the command on a machine with no card
        # tool, so no card can be reported. This line holds the helper to its
        # own docstring and cannot fail on a change of the product.
        assert found.gpus == ()
    else:
        assert [(g.name, g.vram_gb) for g in found.gpus] == [
            (c.name, round(c.total_mib / detect.MIB_PER_GB, 1))
            for c in machine.readable_cards
            if c.total_mib is not None
        ]
    if machine.card_reader_missing:
        assert found.gpus == ()
    assert {(b.kind, b.host, b.models) for b in found.backends} == {
        (s.kind, s.host, s.models) for s in machine.servers
    }


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_a_scan_reports_the_cards_the_product_reader_can_read(
    machine: Shape,
) -> None:
    measured = scan(machine)
    assert measured.machine.id == machine.machine_id
    assert measured.machine.host == machine.host
    assert [
        (
            g.index,
            g.name,
            g.vram.total_mib,
            g.vram.used_mib,
            g.vram.free_mib,
            g.vram.reserved_mib,
        )
        for g in measured.gpus
    ] == [
        (c.index, c.name, c.total_mib, c.used_mib, c.free_mib, c.reserved_mib)
        for c in machine.readable_cards
    ]
    unread = any(c.total_mib is None and c.card_reader_reads for c in machine.cards)
    assert measured.gpus_determined == (not machine.card_reader_missing and not unread)


@pytest.mark.parametrize(
    "machine", [m for m in shapes() if m.local], ids=lambda m: m.label
)
def test_a_scan_and_a_detection_of_one_machine_agree_on_its_cards(
    machine: Shape,
) -> None:
    found = detection(machine)
    measured = scan(machine)
    assert [(g.name, g.vram_gb) for g in found.gpus] == [
        (g.name, round(g.vram.total_mib / detect.MIB_PER_GB, 1)) for g in measured.gpus
    ]


# 4. Nothing of the machine the tests run on gets in.


@contextmanager
def _nothing_of_this_machine_is_asked() -> Iterator[list[str]]:
    """Every way out to this machine fails the test, even if caught inside."""
    asked: list[str] = []

    def forbidden(name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            asked.append(f"{name}{args!r}")
            raise AssertionError(f"{name} was called with {args!r}")

        return call

    with (
        mock.patch.object(subprocess, "run", forbidden("subprocess.run")),
        mock.patch.object(urllib.request, "urlopen", forbidden("urlopen")),
        mock.patch.object(shutil, "which", forbidden("shutil.which")),
    ):
        yield asked


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_nothing_of_the_machine_the_tests_run_on_gets_into_what_is_reported(
    machine: Shape,
) -> None:
    with _nothing_of_this_machine_is_asked() as asked:
        found = detection(machine)
        measured = scan(machine)
    assert asked == []
    # Detection: memory, processor and container tool are not determined.
    assert found.cpu_count is None
    assert found.ram_gb is None
    assert found.docker is False
    assert "cpu_count" not in found.provenance
    assert "ram_gb" not in found.provenance
    # Scan: memory, processor, bandwidth and disk absent; id, host and kernel
    # are the shape's and the helper's stand-in.
    assert measured.memory is None
    assert measured.cpu is None
    assert measured.bandwidth is None
    assert measured.disk is None
    assert (measured.machine.id, measured.machine.host, measured.machine.kernel) == (
        machine.machine_id,
        machine.host,
        machine_shapes._KERNEL,
    )


# 5. Busy cards, reserves and free memory.


def test_a_cards_free_memory_is_what_its_reserve_and_holders_leave() -> None:
    busy = [(m, c) for m in shapes() for c in m.readable_cards if c.holders]
    assert busy
    for machine, card in busy:
        read = {g.index: g for g in scan(machine).gpus}
        assert read[card.index].vram.used_mib == sum(h.mib for h in card.holders)
        assert read[card.index].vram.free_mib == card.free_mib


def test_at_least_two_machines_have_a_card_that_keeps_memory_for_itself() -> None:
    reserving = [m for m in shapes() if any(c.reserved_mib for c in m.readable_cards)]
    assert len(reserving) >= 2


def test_a_card_of_unreadable_size_has_no_free_memory_either() -> None:
    unread = [c for m in shapes() for c in m.cards if c.total_mib is None]
    assert unread
    assert all(c.free_mib is None for c in unread)


def test_every_holder_has_a_positive_process_id_unique_on_its_card() -> None:
    for card in (c for m in shapes() for c in m.cards if c.holders):
        pids = [h.pid for h in card.holders]
        assert all(pid > 0 for pid in pids)
        assert len(pids) == len(set(pids))


# 6. A shape that contradicts itself is refused by name.


def _card(**changes: Any) -> Card:
    fields: dict[str, Any] = {
        "index": 0,
        "name": "Example Card Z",
        "vendor": "vendor-a",
        "total_mib": 4000,
    }
    return Card(**(fields | changes))


def _holder(mib: int, pid: int = 1) -> Holder:
    return Holder(name="example-holder", mib=mib, pid=pid)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: _card(vendor="vendor-z"), "is not one of"),
        (lambda: _card(index=-1), "negative index"),
        (lambda: _card(total_mib=-1), "negative total"),
        (lambda: _card(reserved_mib=-1), "negative reserve"),
        (lambda: _card(holders=(_holder(-5),)), "holds a negative"),
        (lambda: _card(holders=(_holder(1), _holder(1))), "share a process id"),
        (
            lambda: _card(total_mib=None, holders=(_holder(1),)),
            "holders on a card of unreadable size",
        ),
        (
            lambda: _card(total_mib=None, reserved_mib=8),
            "reserve on a card of unreadable size",
        ),
        (lambda: _card(reserved_mib=4001), "more than its total"),
        (lambda: _card(holders=(_holder(4001),)), "more than the 4000 MiB"),
        (
            lambda: _card(reserved_mib=100, holders=(_holder(3901),)),
            "more than the 3900 MiB",
        ),
        (lambda: _holder(1, pid=0), "not positive"),
    ],
    ids=[
        "unknown-vendor",
        "negative-index",
        "negative-total",
        "negative-reserve",
        "negative-holder",
        "shared-pid",
        "holders-unreadable",
        "reserve-unreadable",
        "reserve-over-total",
        "holders-over-total",
        "holders-over-room",
        "pid-not-positive",
    ],
)
def test_a_card_that_contradicts_itself_is_refused_by_name(
    build: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        build()


def _kind_and_port() -> tuple[str, int]:
    kind, port, _ = detect.PORT_CONVENTIONS[0]
    return kind, port


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"local": False}, "contradicts host"),
        ({"host": "box-9.example"}, "contradicts host"),
        ({"cards": (_card(), _card())}, "two vendor-a cards with index 0"),
        (
            {
                "servers": (
                    Server(
                        kind=_kind_and_port()[0],
                        host="box-9.example",
                        port=_kind_and_port()[1],
                        models=(),
                    ),
                )
            },
            "not on the machine's host",
        ),
        (
            {
                "servers": (
                    Server(kind="no-such-kind", host="localhost", port=1, models=()),
                )
            },
            "not one the product probes",
        ),
        (
            {
                "servers": (
                    Server(
                        kind=_kind_and_port()[0], host="localhost", port=1, models=()
                    ),
                )
            },
            "probes",
        ),
    ],
    ids=[
        "local-false-on-localhost",
        "local-true-on-a-far-host",
        "two-cards-one-index",
        "server-elsewhere",
        "unknown-server-kind",
        "unprobed-port",
    ],
)
def test_a_shape_that_contradicts_itself_is_refused_by_name(
    change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        dataclasses.replace(shape("bare"), **change)


def test_two_cards_of_one_index_are_accepted_when_their_vendors_differ() -> None:
    mixed = shape("mixed-vendors")
    assert len({c.index for c in mixed.cards}) < len(mixed.cards)


# 7. A server can be put on any machine.


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_a_server_put_on_a_machine_is_found_by_detection(machine: Shape) -> None:
    taken = {s.kind for s in machine.servers}
    for kind, port, _ in detect.PORT_CONVENTIONS:
        if kind in taken:
            continue
        served = with_server(machine, kind=kind, models=("example-model-extra",))
        assert served.label == machine.label
        added = served.servers[-1]
        assert (added.kind, added.host, added.port) == (kind, machine.host, port)
        found = {(b.kind, b.host, b.models) for b in detection(served).backends}
        assert (kind, machine.host, ("example-model-extra",)) in found


def test_a_server_the_product_would_not_find_is_refused() -> None:
    kind, port = _kind_and_port()
    with pytest.raises(ValueError, match="not one the product probes"):
        with_server(shape("bare"), kind="no-such-kind", models=())
    with pytest.raises(ValueError, match=f"port {port} only"):
        with_server(shape("bare"), kind=kind, models=(), port=port + 1)
    with pytest.raises(ValueError, match="two servers on one port"):
        with_server(shape("bare-local-server"), kind=kind, models=())


# 8. Labels and names.


def test_the_labels_are_pinned() -> None:
    assert tuple(m.label for m in shapes()) == LABELS


def test_labels_are_unique_identifiers_and_an_unknown_one_names_them_all() -> None:
    labels = [m.label for m in shapes()]
    assert len(labels) == len(set(labels))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", label) for label in labels)
    for label in labels:
        assert shape(label).label == label
    with pytest.raises(KeyError) as refused:
        shape("no-such-machine")
    assert all(label in str(refused.value) for label in labels)


def test_the_interface_is_exactly_its_public_names() -> None:
    assert sorted(machine_shapes.__all__) == sorted(
        [
            "VENDORS",
            "Card",
            "Holder",
            "Server",
            "Shape",
            "card_reader_text",
            "detection",
            "scan",
            "shape",
            "shapes",
            "with_server",
        ]
    )


def test_every_vendor_label_is_declared_and_both_kinds_exist() -> None:
    assert {c.vendor for m in shapes() for c in m.cards} <= set(VENDORS)
    assert set(VENDORS.values()) == {True, False}


# 9. Every invented name is a placeholder by shape.

# RFC 2606 / RFC 6761 names reserved for examples and tests.
_RESERVED_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
# RFC 5737 / RFC 3849 documentation ranges.
_DOCUMENTATION = tuple(
    ipaddress.ip_network(n)
    for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)
_LABEL = re.compile(r"[a-z][a-z0-9-]*")


def _placeholder_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return any(address in net for net in _DOCUMENTATION)
    if host == "localhost":
        return True
    return host.endswith(_RESERVED_SUFFIXES) and all(
        _LABEL.fullmatch(part) for part in host.split(".")
    )


def test_every_invented_network_name_is_a_placeholder_by_shape() -> None:
    hosts = {m.host for m in shapes()} | {s.host for m in shapes() for s in m.servers}
    real_looking = sorted(h for h in hosts if not _placeholder_host(h))
    assert not real_looking, real_looking
    # A documentation address and a reserved example name are both exercised.
    assert any(_is_address(h) for h in hosts)
    assert any("." in h and not _is_address(h) for h in hosts)


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
