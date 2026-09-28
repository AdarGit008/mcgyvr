"""The invented machines come in every shape a user may have.

A product test that sizes, detects or proposes against a machine gets that
machine from :mod:`tests.machine_shapes`, the one generator of invented
machines. These promises hold the generator to three things: it offers every
kind of machine a user may bring, none of its machines is only of the kind the
product happened to be developed on, and what it says a machine is, is what the
product's own readers make of it.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from collections.abc import Sequence
from unittest import mock

import pytest

from mcgyvr import detect
from tests.machine_shapes import (
    VENDORS,
    Card,
    Shape,
    detection,
    nvidia_smi_text,
    scan,
    shape,
    shapes,
)


def _readable(machine: Shape) -> tuple[Card, ...]:
    """The cards the product's card reader can read on this machine."""
    if machine.card_reader_missing:
        return ()
    return tuple(
        card
        for card in machine.cards
        if card.card_reader_reads and card.total_mib is not None
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
        "an unreadable memory size beside a readable one": any(
            any(c.total_mib is None for c in m.cards)
            and any(c.total_mib is not None for c in m.cards)
            for m in machines
        ),
        "cards all of a vendor the reader is not for": any(
            m.cards and not any(c.card_reader_reads for c in m.cards) for m in machines
        ),
        "two vendors mixed": any(
            len({c.vendor for c in m.cards}) > 1 for m in machines
        ),
        "cards but no card reading tool": any(
            m.cards and m.card_reader_missing for m in machines
        ),
        "the same cards here and over the network": any(
            near.local and not far.local and near.cards and near.cards == far.cards
            for near in machines
            for far in machines
        ),
    }
    missing = [kind for kind, offered in kinds.items() if not offered]
    assert not missing, f"no invented machine of these kinds: {missing}"


# 2. No machine is only of the developer's kind.


def test_no_invented_machine_is_only_of_the_kind_the_product_was_built_on() -> None:
    """The rule, stated without restating any size.

    The product was developed on machines of one or two cards whose sizes came
    from a set of two. So, across the generator's machines:

    - at least five distinct card sizes appear;
    - no single size is more than half of all the cards;
    - some machine has more than two cards;
    - the machines of one or two cards between them use more than two sizes,
      so the small machines are not a two-size set either.
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


def test_nvidia_smi_text_answers_the_query_detection_asks() -> None:
    """The default query is detect's own: captured, not restated."""
    asked: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> str | None:
        asked.append(tuple(command))
        return None

    with mock.patch.object(detect, "_run", run):
        detect.detect_gpus()
    query = next(a for a in asked[0] if a.startswith("--query-gpu="))
    cards = shape("several-sizes").cards
    assert nvidia_smi_text(cards) == nvidia_smi_text(
        cards, query=query.removeprefix("--query-gpu=")
    )


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_detection_reports_the_cards_the_product_reader_can_read(
    machine: Shape,
) -> None:
    found = detection(machine)
    if not machine.local:
        # Detection reads cards only on the machine it runs on.
        assert found.gpus == ()
    else:
        assert [(g.name, g.vram_gb) for g in found.gpus] == [
            (c.name, round(c.total_mib / detect.MIB_PER_GB, 1))
            for c in _readable(machine)
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
        (g.index, g.name, g.vram.total_mib, g.vram.free_mib) for g in measured.gpus
    ] == [(c.index, c.name, c.total_mib, c.free_mib) for c in _readable(machine)]
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


# 4. A busy card.


def test_a_busy_cards_free_memory_is_what_its_holders_leave() -> None:
    busy = [(m, c) for m in shapes() for c in m.cards if c.holders]
    assert busy
    for machine, card in busy:
        assert card.total_mib is not None
        held = sum(h.mib for h in card.holders)
        assert card.free_mib == card.total_mib - held
        read = {g.index: g for g in scan(machine).gpus}
        if card in _readable(machine):
            assert read[card.index].vram.used_mib == held
            assert read[card.index].vram.free_mib == card.free_mib


def test_a_card_of_unreadable_size_has_no_free_memory_either() -> None:
    unread = [c for m in shapes() for c in m.cards if c.total_mib is None]
    assert unread
    assert all(c.free_mib is None for c in unread)


# 5. Labels.


def test_labels_are_unique_stable_identifiers() -> None:
    labels = [m.label for m in shapes()]
    assert len(labels) == len(set(labels))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", label) for label in labels)
    assert shapes() == shapes()
    for label in labels:
        assert shape(label).label == label
    with pytest.raises(KeyError) as refused:
        shape("no-such-machine")
    assert all(label in str(refused.value) for label in labels)


def test_every_vendor_label_is_declared_and_both_kinds_exist() -> None:
    assert {c.vendor for m in shapes() for c in m.cards} <= set(VENDORS)
    assert set(VENDORS.values()) == {True, False}


# 6. Every invented name is a placeholder by shape.

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
    if host == "localhost" or _LABEL.fullmatch(host):
        return True
    return host.endswith(_RESERVED_SUFFIXES) and all(
        _LABEL.fullmatch(part) for part in host.split(".")
    )


def test_every_invented_network_name_is_a_placeholder_by_shape() -> None:
    hosts = {m.host for m in shapes()} | {s.host for m in shapes() for s in m.servers}
    real_looking = sorted(h for h in hosts if not _placeholder_host(h))
    assert not real_looking, real_looking
    assert all((m.host == "localhost") == m.local for m in shapes())
    # A documentation address and a reserved example name are both exercised.
    assert any(_is_address(h) for h in hosts)
    assert any("." in h and not _is_address(h) for h in hosts)


def test_every_server_runs_on_the_machine_it_belongs_to() -> None:
    assert all(s.host == m.host for m in shapes() for s in m.servers)


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
