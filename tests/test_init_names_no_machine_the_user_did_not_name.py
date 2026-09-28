"""`mcgyvr init` names no machine the user did not name.

Promise: every machine named in the files `init` writes, in the text of its
refusals, and in every example hint of the config schema is a machine the
user's own detection or command line carried, `localhost`, or a placeholder.

A placeholder is a name in angle brackets (``<host>``), a reserved example
name (``example``, ``*.example``, ``example.com``/``.net``/``.org``, RFC 2606)
or a reserved documentation address (``192.0.2.0/24``, ``198.51.100.0/24``,
``203.0.113.0/24``, RFC 5737). Anything else is a machine somebody else owns,
written into a stranger's files.

The test holds no list of names to avoid. It finds machine names by their
shape — the host of every URL, the value after every ``--host``, every dotted
IPv4 address, the host segment of every container name, the example value of
the schema's ``rig`` key and every unit name in an example map — and asks of
each one where it came from.

The machines below are invented, in names and in shape: no card, one card,
several cards of mixed sizes, a local server, servers on remote hosts named
on the command line, and hosted units named with ``--api``.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcgyvr import config
from mcgyvr.capability import load as load_table
from mcgyvr.detect import DEFAULT_HOST, Backend, Detection, Gpu, targets_for
from mcgyvr.initialize import (
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
)
from mcgyvr.propose import API, LOCAL

# --- what counts as a machine name, by shape -------------------------------

_URL_HOST = re.compile(
    r"\b[a-z][a-z0-9+.-]*://(\[[^\]\s]+\]|<[^<>\s]+>|[^\s/:?#\"'`,()<>]+)",
    re.IGNORECASE,
)
_HOST_FLAG = re.compile(r"--host[ =]+([^\s`'\"(),]+)")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
#: A container name as the product mints it: ``mcgyvr-<host>-<service>``.
_CONTAINER = re.compile(r"\bmcgyvr-(<[^<>\s]+>|[A-Za-z0-9_.]+)-\S+")
#: The keys of an example map such as ``{<unit>: 2}``.
_MAP_KEY = re.compile(r"[{,]\s*([^\s{},:]+)\s*:")
#: A hosted unit's endpoint inside an ``--api`` example. A hosted endpoint is
#: not a machine in anyone's fleet (it has no `rig`), so its host is a
#: provider's public name, not a machine the user was meant to own.
_API_EXAMPLE_ADDRESS = re.compile(r"--api\s+\S*address=https://([^\s,/]+)")

_PLACEHOLDER = re.compile(r"<[^<>\s]+>")
_RESERVED_NAMES = re.compile(
    r"(?:[a-z0-9-]+\.)*(?:example|example\.com|example\.net|example\.org)",
    re.IGNORECASE,
)
_DOC_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)


def _is_placeholder(token: str, carried: frozenset[str]) -> bool:
    """Whether a machine name is one the user gave, loopback, or a placeholder."""
    bare = token.strip().strip("[]")
    if _PLACEHOLDER.fullmatch(token.strip()):
        return True
    if bare.lower() in {c.lower() for c in carried}:
        return True
    if bare.lower() == DEFAULT_HOST:
        return True
    if _RESERVED_NAMES.fullmatch(bare):
        return True
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        return False
    return address.is_loopback or any(address in net for net in _DOC_NETWORKS)


def _machine_names(text: str) -> Iterator[str]:
    """Every token in ``text`` whose shape says it names a machine."""
    hosted = {m.group(1) for m in _API_EXAMPLE_ADDRESS.finditer(text)}
    for match in _URL_HOST.finditer(text):
        if match.group(1) not in hosted:
            yield match.group(1)
    for match in _HOST_FLAG.finditer(text):
        yield match.group(1)
    for match in _IPV4.finditer(text):
        yield match.group(1)
    for match in _CONTAINER.finditer(text):
        yield match.group(1)


def _strangers(text: str, carried: frozenset[str]) -> list[str]:
    return sorted({t for t in _machine_names(text) if not _is_placeholder(t, carried)})


# --- invented machines ------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """One invented machine: its cards, what answered, what the user typed."""

    label: str
    cards_gb: tuple[float, ...]
    hosts: tuple[str, ...]  # named with --host; empty means this machine
    serving: bool  # whether the servers hold a model the table knows
    api: tuple[str, ...] = ()  # --api values

    def detection(self, model_id: str) -> Detection:
        models = (model_id,) if self.serving else ()
        targets = targets_for(self.hosts) if self.hosts else targets_for()
        backends = tuple(
            Backend(
                name=t.name,
                base_url=t.base_url,
                api=t.api,
                models=models,
                how=f"invented answer at {t.base_url}",
                host=t.host,
                kind=t.kind,
            )
            for t in targets
            if t.kind == "llama-server"
        )
        return Detection(
            gpus=tuple(
                Gpu(f"Invented card {i}", gb, "invented")
                for i, gb in enumerate(self.cards_gb)
            ),
            cpu_count=4,
            ram_gb=48.0,
            backends=backends,
            docker=bool(self.cards_gb),
            provenance={},
        )

    def carried(self) -> frozenset[str]:
        """Every machine the invented detection or command line carried."""
        names = set(self.hosts)
        for spec in self.api:
            host = re.match(r"[a-z]+://([^/:]+)", parse_api_unit(spec).address)
            if host:
                names.add(host.group(1))
        return frozenset(names)


_API = "model=invented-coder,address=https://llm.inventedprovider.test/v1,api_key_env=INVENTED_KEY"

SHAPES: tuple[Shape, ...] = (
    Shape("no card, nothing serving", (), (), serving=False),
    Shape("no card, a hosted unit", (), (), serving=False, api=(_API,)),
    Shape("one 10 GB card, local server", (10.0,), (), serving=True),
    Shape("one 20 GB card, local server empty", (20.0,), (), serving=False),
    Shape("three mixed cards, local server", (4.0, 10.0, 24.0), (), serving=True),
    Shape("no card, one remote host", (), ("orchard",), serving=True),
    Shape(
        "one 16 GB card, two remote hosts",
        (16.0,),
        ("quarry.internal", "10.20.30.40"),
        serving=True,
    ),
    Shape("remote hosts with nothing loaded", (), ("larch", "birch"), serving=False),
    Shape(
        "two 32 GB cards, remote host and hosted unit",
        (32.0, 32.0),
        ("fen",),
        True,
        (_API,),
    ),
)


def _model_id() -> str:
    table = load_table()
    rows = sorted(table.models, key=lambda m: m.vram_gb_working)
    return rows[0].id


def _what_init_says(shape: Shape, where: Path) -> str:
    """The files init writes and every line it shows, or its refusal."""
    api_units = tuple(parse_api_unit(spec) for spec in shape.api)
    try:
        result = initialize(
            where,
            detection=shape.detection(_model_id()),
            api_units=api_units,
        )
    except InitError as refusal:
        return str(refusal)
    return "\n".join((result.content, *result.decisions, *result.limits))


@pytest.mark.parametrize("shape", SHAPES, ids=[s.label for s in SHAPES])
def test_what_init_writes_or_refuses_names_only_the_users_machines(
    shape: Shape, tmp_path: Path
) -> None:
    text = _what_init_says(shape, tmp_path / "setup")
    assert _strangers(text, shape.carried()) == [], (
        f"init on '{shape.label}' names machines nobody named:\n{text}"
    )


def test_some_shape_is_refused_and_some_is_written(tmp_path: Path) -> None:
    """The sweep above covers both halves of the promise, files and refusals."""
    refused = written = 0
    for i, shape in enumerate(SHAPES):
        try:
            initialize(
                tmp_path / str(i),
                detection=shape.detection(_model_id()),
                api_units=tuple(parse_api_unit(s) for s in shape.api),
            )
        except InitError:
            refused += 1
        else:
            written += 1
    assert refused and written


_BAD_API_SPECS: tuple[str, ...] = (
    "model",
    "model=a,address=https://llm.inventedprovider.test,api_key_env=K,colour=blue",
    "model=a,model=b",
    "model=a",
)


@pytest.mark.parametrize("spec", _BAD_API_SPECS)
def test_an_api_refusal_names_no_machine(spec: str) -> None:
    with pytest.raises(ApiSpecError) as refusal:
        parse_api_unit(spec)
    assert (
        _strangers(str(refusal.value), frozenset({"llm.inventedprovider.test"})) == []
    )


def test_a_hosted_setup_the_loader_rejects_names_no_machine(tmp_path: Path) -> None:
    """The refusal quotes the loader, and the loader echoes what was typed."""
    unit = parse_api_unit(
        "model=invented-coder,address=notanaddress,api_key_env=INVENTED_KEY"
    )
    with pytest.raises(InitError) as refusal:
        initialize(tmp_path / "s", detection=Detection(), api_units=(unit,))
    assert _strangers(str(refusal.value), frozenset({"notanaddress"})) == []


def test_two_hosted_units_minting_one_name_are_refused_naming_only_their_hosts(
    tmp_path: Path,
) -> None:
    first = parse_api_unit("model=same,address=https://a.invented.test,api_key_env=K1")
    second = parse_api_unit("model=same,address=https://b.invented.test,api_key_env=K2")
    with pytest.raises(InitError) as refusal:
        initialize(tmp_path / "s", detection=Detection(), api_units=(first, second))
    carried = frozenset({"a.invented.test", "b.invented.test"})
    assert _strangers(str(refusal.value), carried) == []


# --- the schema's own examples ----------------------------------------------


def _fields(fields: Sequence[config.Field]) -> Iterator[config.Field]:
    for spec in fields:
        yield spec
        yield from _fields(spec.block)


def _all_fields() -> list[config.Field]:
    """Every field the config module declares, reached from SCHEMA or not."""
    tuples = [config.SCHEMA] + [
        value
        for value in vars(config).values()
        if isinstance(value, tuple)
        and value
        and all(isinstance(v, config.Field) for v in value)
    ]
    seen: dict[int, config.Field] = {}
    for group in tuples:
        for spec in _fields(group):
            seen[id(spec)] = spec
    return list(seen.values())


def _unit_name_is_placeholder(name: str) -> bool:
    """A unit named in an example says what runs, never the machine it runs on.

    Either a placeholder, or a name `init` itself would mint, which begins
    with a locality rather than with a machine.
    """
    return bool(_PLACEHOLDER.fullmatch(name)) or name.startswith(
        (f"{LOCAL}_", f"{API}_")
    )


def _example_value(hint: str) -> str | None:
    match = re.search(r"e\.g\.\s+([^\s,]+)", hint)
    return match.group(1) if match else None


def test_every_schema_example_names_only_placeholder_machines() -> None:
    found: list[str] = []
    for spec in _all_fields():
        texts = [spec.doc, spec.bind_hint, *(why for _, why in spec.retired)]
        for text in texts:
            found += [f"{spec.name}: {t}" for t in _strangers(text, frozenset())]
        if spec.name == "rig" and spec.bind_hint:
            value = _example_value(spec.bind_hint)
            if value is not None and not _is_placeholder(value, frozenset()):
                found.append(f"{spec.name}: {value}")
        if spec.kind == "int_map" and spec.bind_hint:
            found += [
                f"{spec.name}: {key}"
                for key in _MAP_KEY.findall(spec.bind_hint)
                if not _unit_name_is_placeholder(key)
            ]
    assert found == [], "schema examples name machines nobody named:\n" + "\n".join(
        found
    )


# --- the method finds what it claims to find --------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("e.g. http://somebox:8123", ["somebox"]),
        ("run `mcgyvr init --host alpha --host 10.1.2.3`", ["10.1.2.3", "alpha"]),
        ("e.g. mcgyvr-somebox-unit_7b", ["somebox"]),
        ("reach 172.16.9.9 directly", ["172.16.9.9"]),
        ("e.g. http://<host>:<port>", []),
        ("e.g. http://box.example:8080 or 192.0.2.10", []),
        ("e.g. mcgyvr-<host>-<unit>", []),
        ("http://localhost:8080 and http://127.0.0.1:8000", []),
        ("--api model=m,address=https://api.provider.test,api_key_env=K", []),
    ],
)
def test_the_shape_finder_finds_machine_names(text: str, expected: list[str]) -> None:
    assert _strangers(text, frozenset()) == expected
