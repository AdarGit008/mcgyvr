"""The wire the hub serves a rider, defined once: the product's, the hub's by import.

The hub serves models to a member's rigs and the product rides them: relief
rungs (hitchhike), the ladder a rider reports, the units a host advertises,
the resources a rig lends, the relay that carries a ride, and the ``/v1``
refusals a rider reads. Every
value both sides hold for that is here, once, and the hub builds its own types
from these names rather than writing them again:

* :data:`RUNG_POSITIONS`, where a relief rung's host model sits against the
  rider's ladder;
* :data:`MODEL_NAME`, the shape of a model name on the wire, and
  :data:`RUNG_PREFIX`, which with an offer's id (:data:`OFFER_ID`) names a
  relief rung's model (:func:`rung_model`, :func:`rung_offer`);
* the ladder a rider reports (``LADDER_*``);
* the units a host advertises (:data:`MAX_SLOTS`, :data:`MAX_UNITS`,
  ``UNIT_ADVERT_*``) and the rule a ride cap keeps (:func:`rider_cap_fits`);
* the relay's limits (``RELAY_MAX_*``);
* the ``/v1`` error codes with their one HTTP status each
  (:data:`API_ERROR_STATUS`), and the pairs the product reads off them
  (:data:`RUNG_BUSY`, :data:`MODEL_UNPLACED`, :data:`MODEL_NOT_FOUND`);
* the chat request fields the hub forwards to a unit
  (:data:`FORWARDED_FIELDS`, :data:`CHAT_TEMPLATE_KEYS`);
* the header naming who may serve a request (:data:`SCOPE_HEADER`,
  :data:`SCOPE_VALUES`);
* the use cases (:data:`USE_CASES`) with the model category each is
  recommended (:data:`USE_CASE_CATEGORY`), the header a request names its own in
  (:data:`USE_CASE_HEADER`), and which use cases each pool serves
  (:data:`POOL_USE_CASES`, :func:`pool_serves`): the hub refuses the rest;
* the hub's published JSON Schemas (:data:`SCHEMAS`), shipped inside this
  package and read with :func:`schema_bytes` and :func:`schema`;
* what a rig lends, as resources (:class:`Resource`) on a host
  (:class:`Host`), and a heartbeat's reading of each
  (:class:`ResourceReading`): their kinds (:data:`RESOURCE_KINDS`, the card
  kinds :data:`CARD_KINDS`, :func:`shares_ram`), backends
  (:data:`RESOURCE_BACKENDS`, each named ``BACKEND_*``), what a number is
  (:data:`FIGURE_KINDS`), the host a rig runs on (:data:`HOST_OS`,
  :data:`HOST_ARCH`, each named ``HOST_*`` and ``ARCH_*``), how many one
  advert or heartbeat may name (:data:`MAX_RESOURCES`, the kinds a rig names
  once, :data:`ONE_PER_RIG`, :func:`resources_fit`, :func:`readings_fit`),
  the legacy cards they make (:func:`cards_from_resources`,
  :func:`card_readings_from`), the unit standby is counted in per kind
  (:data:`STANDBY_UNITS`, its size :data:`STANDBY_UNIT_SIZE`) and the least a
  resource lends to count (:data:`LEND_FLOOR_MB`, :data:`LEND_FLOOR_CORES`,
  the oldest DDR generation host memory may be, :data:`RAM_DDR_MIN`, and
  :func:`counts_as_lent`);
* what a member chooses to lend on a rig (:class:`Lending`, carried as
  :data:`LENDING_FIELD`);
* the llama.cpp RPC protocol version a rig speaks (:class:`RpcProto`, carried
  as :data:`RPC_PROTO_FIELD`) and which workers a head may take
  (:func:`rpc_compatible`);
* the devices a head runs a model on (:data:`HEAD_DEVICE_KINDS`);
* how fast a device decodes by its memory bandwidth
  (:func:`decode_ms_per_gib`, with :data:`DECODE_EFFICIENCY`).

A pattern is held unanchored and matched whole (``fullmatch``); a JSON Schema
or a pydantic type writes it as ``^<pattern>$``. Nothing here is a validator
of a whole message: the hub's pydantic models and the product's readers stay
two, and each value they share is held to the schemas by the product's tests.
A resource, a reading and a host carry their own rules (``validate()``,
:func:`resources_fit`, :func:`readings_fit`) for both sides to call; their
values join the schemas once the hub publishes them.

Stdlib only, and nothing from ``mcgyvr.cli`` or ``mcgyvr.rig``: the offline
core and the hub import this module without either.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from types import MappingProxyType
from typing import Any

#: Where a relief rung's host model sits against the models of the rider's own
#: ladder, as the hub judges it: shown, never a place on the ladder.
RUNG_POSITIONS: tuple[str, ...] = ("above_ceiling", "below_floor", "within")

#: A model name on the wire: named, never addressed by path, so no separator
#: and no leading dot; 1 to 128 characters.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@-]{0,127}")
#: What a relief rung's model starts with: the hub's offer id follows.
RUNG_PREFIX = "hitchhike@"
#: An offer's id, as the hub writes it: 32 lowercase hex digits.
OFFER_ID = re.compile(r"[0-9a-f]{32}")

#: Most model rungs a reported ladder may have; it has at least one.
LADDER_MAX_RUNGS = 64
#: A reported rung's model: a model name, or a provider's path-like name
#: (``/`` and ``:`` allowed); 1 to 128 characters.
LADDER_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@/:-]{0,127}")
#: The families a reported rung may be of.
LADDER_FAMILIES: tuple[str, ...] = ("local", "api")
#: Largest model file a reported rung may name, in bytes.
LADDER_MAX_SIZE_BYTES = 1 << 50
#: Largest parameter count a reported rung may name, in billions.
LADDER_MAX_PARAMS_B = 100_000

#: Most slots one unit may have: a unit's concurrency, one session per slot.
MAX_SLOTS = 16
#: Most units one advert may name.
MAX_UNITS = 16
#: An agent sends its advert again at least this often, in seconds.
UNIT_ADVERT_INTERVAL_S = 60
#: An advert older than this is withdrawn, in seconds.
UNIT_ADVERT_STALE_S = 3 * UNIT_ADVERT_INTERVAL_S

#: Raw bytes one relay data frame carries at most.
RELAY_MAX_CHUNK_BYTES = 32 * 1024
#: Largest request body a relay carries, in bytes.
RELAY_MAX_REQUEST_BYTES = 1 << 20
#: Largest response a relay carries, in bytes.
RELAY_MAX_RESPONSE_BYTES = 64 << 20
#: Most data frames in flight before the sender waits for credit.
RELAY_MAX_WINDOW = 64
#: Longest a relayed request may run, in seconds.
RELAY_MAX_TIMEOUT_S = 3600
#: Highest sequence number a relay data frame may carry.
RELAY_MAX_SEQ = 1 << 31
#: Most prompt or completion tokens a relayed call may report at its end.
RELAY_MAX_TOKENS = 1 << 31

#: The ``error.code`` of a refused ``/v1`` request, each with its one HTTP
#: status. A client matches on the pair; the hub publishes the table in its
#: rider schema (``x-openai-errors``).
API_ERROR_STATUS: Mapping[str, int] = MappingProxyType(
    {
        "invalid_request": 400,
        "invalid_scope": 400,
        "ctx_out_of_range": 400,
        "invalid_api_key": 401,
        "insufficient_credits": 402,
        "not_giving": 403,
        "out_of_scope": 403,
        "signed_out": 403,
        "not_giving_hitchhike": 403,
        "model_not_found": 404,
        "request_too_large": 413,
        "rate_limit_exceeded": 429,
        "too_many_concurrent_requests": 429,
        "client_closed_request": 499,
        "session_failed": 502,
        "upstream_error": 502,
        "pool_busy": 503,
        "model_unplaced": 503,
        "model_loading": 503,
        "hitchhike_not_served_yet": 503,
        "hitchhike_host_away": 503,
        "model_metadata": 503,
        "no_head": 503,
        "insufficient_vram": 503,
        "busy": 503,
        "no_path": 503,
        "rpc_incompatible": 503,
        "too_slow": 503,
        "timeout": 504,
    }
)


def api_error(code: str) -> tuple[int, str]:
    """The ``(status, code)`` pair a ``/v1`` refusal with ``code`` carries.

    Raises KeyError for a code the table does not hold.
    """
    return (API_ERROR_STATUS[code], code)


#: The hub cannot place the asked model right now: width unavailable, not a
#: broken rung.
MODEL_UNPLACED = api_error("model_unplaced")
#: The address does not know the asked model.
MODEL_NOT_FOUND = api_error("model_not_found")
#: The answers that say a relief rung cannot take a request now, sorted: the
#: hub names no host running the model (404 ``model_not_found``), the host's
#: machine is away (503 ``hitchhike_host_away``), the hub has not yet matched
#: this host to work (503 ``hitchhike_not_served_yet``), and the host's unit
#: serves as many rides as it may (503 ``pool_busy``). One of them is a full
#: rung, passed over at no cost.
RUNG_BUSY: tuple[tuple[int, str], ...] = tuple(
    sorted(
        api_error(code)
        for code in (
            "model_not_found",
            "hitchhike_host_away",
            "hitchhike_not_served_yet",
            "pool_busy",
        )
    )
)

#: The chat completion request fields a request through the hub may carry:
#: the hub takes these and drops any other field on the way to the unit that
#: answers. ``max_completion_tokens`` is folded into ``max_tokens`` and ``n``
#: is taken only as 1, so neither is passed on as sent. ``logprobs``,
#: ``top_logprobs`` and ``chat_template_kwargs``, what a Jev unit needs, are
#: the set's and not yet the hub's: the hub forwards them once it builds its
#: request from this set.
FORWARDED_FIELDS: frozenset[str] = frozenset(
    {
        "model",
        "messages",
        "stream",
        "stream_options",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "seed",
        "stop",
        "presence_penalty",
        "frequency_penalty",
        "repeat_penalty",
        "response_format",
        "tools",
        "tool_choice",
        "n",
        "logprobs",
        "top_logprobs",
        "chat_template_kwargs",
    }
)
#: The keys of ``chat_template_kwargs`` the product sends, thinking turned off
#: so a one-token answer is the answer, and the only ones the hub passes to a
#: rig.
CHAT_TEMPLATE_KEYS: frozenset[str] = frozenset({"enable_thinking"})

#: The request header naming whose rigs may serve one request; without it the
#: member's own setting applies.
SCOPE_HEADER = "x-mcgyvr-scope"
#: The values :data:`SCOPE_HEADER` takes: the member's own rigs, their crews'
#: too, or anyone's.
SCOPE_VALUES: tuple[str, ...] = ("own", "crew", "anyone")

#: The use cases a setup runs: ``mcgyvr-code`` is the gated coding loop with
#: its opt-ins; ``code``, ``chat`` and ``agent`` serve a model raw.
MCGYVR_CODE = "mcgyvr-code"
CODE = "code"
CHAT = "chat"
AGENT = "agent"
USE_CASES: tuple[str, ...] = (MCGYVR_CODE, CODE, CHAT, AGENT)
#: The kind of model each use case is recommended: ``mcgyvr-code`` climbs a
#: ladder of coding models and ``code`` serves one raw, so both are ``code``.
USE_CASE_CATEGORY: Mapping[str, str] = MappingProxyType(
    {MCGYVR_CODE: CODE, CODE: CODE, CHAT: CHAT, AGENT: AGENT}
)
#: The request header naming the caller's use case, beside
#: :data:`SCOPE_HEADER`, so the hub can refuse one its pool does not serve.
USE_CASE_HEADER = "x-mcgyvr-use-case"

#: Where the hub serves a request from: a member's own rigs, lent to nobody,
#: the general pool, a crew's pool, a hitchhike ride, or a ladder a host shares.
POOL_SOLO = "solo"
POOL_GENERAL = "general"
POOL_CREW = "crew"
POOL_HITCHHIKE = "hitchhike"
POOL_SHARED_LADDER = "shared_ladder"
POOLS: tuple[str, ...] = (
    POOL_SOLO,
    POOL_GENERAL,
    POOL_CREW,
    POOL_HITCHHIKE,
    POOL_SHARED_LADDER,
)
#: The use cases each pool serves. A member's own rigs serve every use case;
#: the general pool serves models raw only; a crew's pool and a ride serve
#: every use case; a shared ladder is there for ``mcgyvr-code`` alone. The
#: hub's sharing modes map onto these: ``solo`` is :data:`POOL_SOLO`, ``pool``
#: is :data:`POOL_GENERAL`, ``crew`` and ``hitchhike`` are themselves.
POOL_USE_CASES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        POOL_SOLO: USE_CASES,
        POOL_GENERAL: (CODE, CHAT, AGENT),
        POOL_CREW: USE_CASES,
        POOL_HITCHHIKE: USE_CASES,
        POOL_SHARED_LADDER: (MCGYVR_CODE,),
    }
)


def pool_serves(pool: str, use_case: str) -> bool:
    """Whether ``pool`` (one of :data:`POOLS`) serves ``use_case``.

    Raises KeyError for a pool that is not one of them.
    """
    return use_case in POOL_USE_CASES[pool]


#: The agent channel's schema: every frame between the hub and a rig's agent.
PROTOCOL_SCHEMA = "protocol.schema.json"
#: The rider REST API's schema, beside the agent channel, with the ``/v1``
#: error table.
RIDER_SCHEMA = "rider.schema.json"
#: Every schema shipped here, by file name: the hub's ``schemas/`` names.
SCHEMAS: tuple[str, ...] = (PROTOCOL_SCHEMA, RIDER_SCHEMA)
#: The package folder the schemas are shipped in.
_SCHEMA_DIR = "hubwire_schemas"


def rung_model(offer: str) -> str:
    """The model a rider sends to ride the offer ``offer``.

    Raises ValueError when ``offer`` is not an offer id.
    """
    if not OFFER_ID.fullmatch(offer):
        raise ValueError(f"{offer!r} is not an offer id")
    return f"{RUNG_PREFIX}{offer}"


def rung_offer(model: str) -> str | None:
    """The offer id a relief rung's ``model`` names, or None when it names none."""
    if not model.startswith(RUNG_PREFIX):
        return None
    offer = model[len(RUNG_PREFIX) :]
    return offer if OFFER_ID.fullmatch(offer) else None


def rider_cap_fits(rider_cap: int, slots: int) -> bool:
    """Whether a unit of ``slots`` slots may take ``rider_cap`` rides at once:
    at least one, and fewer than its slots, so the host keeps one."""
    return 1 <= rider_cap < slots


def schema_bytes(name: str) -> bytes:
    """The schema ``name`` (one of :data:`SCHEMAS`) as shipped, byte for byte.

    Raises ValueError for a name that is not one of them.
    """
    if name not in SCHEMAS:
        raise ValueError(f"{name!r} is not one of {', '.join(SCHEMAS)}")
    return (resources.files("mcgyvr") / _SCHEMA_DIR / name).read_bytes()


def schema(name: str) -> dict[str, Any]:
    """The schema ``name`` (one of :data:`SCHEMAS`), parsed."""
    document: dict[str, Any] = json.loads(schema_bytes(name))
    return document


# --- what a rig lends -----------------------------------------------------------

#: What a rig lends, by kind: a discrete card, a device whose memory is the
#: host's (an integrated or Apple GPU), host memory, and host cores.
RESOURCE_GPU = "gpu"
RESOURCE_UNIFIED = "unified"
RESOURCE_RAM = "ram"
RESOURCE_CPU = "cpu"
RESOURCE_KINDS: tuple[str, ...] = (
    RESOURCE_GPU,
    RESOURCE_UNIFIED,
    RESOURCE_RAM,
    RESOURCE_CPU,
)
#: The kinds that are cards too: each is a legacy card at its index, so the two
#: share the card indexes (:func:`cards_from_resources`).
CARD_KINDS: tuple[str, ...] = (RESOURCE_GPU, RESOURCE_UNIFIED)
#: The backend a resource computes with. Host memory and cores compute with
#: ``cpu`` alone, and a card never does.
BACKEND_CUDA = "cuda"
BACKEND_METAL = "metal"
BACKEND_VULKAN = "vulkan"
BACKEND_ROCM = "rocm"
BACKEND_CPU = "cpu"
RESOURCE_BACKENDS: tuple[str, ...] = (
    BACKEND_CUDA,
    BACKEND_METAL,
    BACKEND_VULKAN,
    BACKEND_ROCM,
    BACKEND_CPU,
)
#: What a number is: an estimate, or the rig's own reading. Each number on the
#: wire says which it is.
FIGURE_ESTIMATE = "estimate"
FIGURE_READING = "reading"
FIGURE_KINDS: tuple[str, ...] = (FIGURE_ESTIMATE, FIGURE_READING)
#: The operating system and the architecture a rig's host names in its hello.
HOST_LINUX = "linux"
HOST_DARWIN = "darwin"
HOST_WINDOWS = "windows"
HOST_OS: tuple[str, ...] = (HOST_LINUX, HOST_DARWIN, HOST_WINDOWS)
ARCH_X86_64 = "x86_64"
ARCH_ARM64 = "arm64"
HOST_ARCH: tuple[str, ...] = (ARCH_X86_64, ARCH_ARM64)
#: Most resources one advert may name; of them, at most :data:`MAX_CARDS`
#: cards, and each kind of :data:`ONE_PER_RIG` once.
MAX_RESOURCES = 32
#: The kinds a rig names at most once: one device whose memory is the host's
#: (a host has one such memory to share), the host's memory and its cores.
ONE_PER_RIG: tuple[str, ...] = (RESOURCE_UNIFIED, RESOURCE_RAM, RESOURCE_CPU)
#: The kinds a heartbeat reads at most once: those of :data:`ONE_PER_RIG`
#: that are not cards.
_ONE_PER_HEARTBEAT = tuple(k for k in ONE_PER_RIG if k not in CARD_KINDS)
#: Most cards one hello or heartbeat may report.
MAX_CARDS = 16
#: Highest index a resource may have: a card's highest index.
MAX_RESOURCE_INDEX = 63
#: Most logical cores one ``cpu`` resource may lend.
MAX_RESOURCE_CORES = 1024
#: Highest DDR generation a ``ram`` resource may name (:attr:`Resource.ddr`).
MAX_RAM_DDR = 9
#: Highest memory bandwidth a resource may name, in GB/s.
MAX_BANDWIDTH_GBPS = 100_000.0
#: Longest host version a hello may name, in characters.
HOST_VERSION_MAX = 64
#: A resource's name is text a hub may show, as a card's is: no control
#: characters, no C1 controls, no bidi embedding, override or isolate marks;
#: at most :data:`RESOURCE_NAME_MAX` characters.
RESOURCE_NAME = re.compile("[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]+")
RESOURCE_NAME_MAX = 128
#: The invisible format characters a resource's name and a host's version may
#: not hold either (zero-width, direction marks, line and paragraph
#: separators, word joiners, byte order mark), held apart from
#: :data:`RESOURCE_NAME`, which is a card name's published pattern.
FORMAT_CHARACTERS = re.compile("[\u061c\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufeff]")
#: Largest memory figure a resource may carry, in MiB, as a card's.
RESOURCE_MAX_MB = 1 << 30
#: MiB in a GiB.
MB_PER_GIB = 1024
#: How much of each kind one standby unit is, which a hub pays standby by:
#: one card, whether its memory is its own or the host's, so a unified device
#: is a card and never also memory; host memory per 16384 MiB (16 GiB) and
#: cores per 8. Cards count in cards, ``ram`` in MiB and ``cpu`` in cores.
STANDBY_UNIT_SIZE: Mapping[str, int] = MappingProxyType(
    {
        RESOURCE_GPU: 1,
        RESOURCE_UNIFIED: 1,
        RESOURCE_RAM: 16 * MB_PER_GIB,
        RESOURCE_CPU: 8,
    }
)
#: The unit standby is counted in for each kind, by name, made from its size
#: (:data:`STANDBY_UNIT_SIZE`).
STANDBY_UNITS: Mapping[str, str] = MappingProxyType(
    {
        RESOURCE_GPU: "card",
        RESOURCE_UNIFIED: "card",
        RESOURCE_RAM: f"{STANDBY_UNIT_SIZE[RESOURCE_RAM] // MB_PER_GIB}GiB",
        RESOURCE_CPU: f"{STANDBY_UNIT_SIZE[RESOURCE_CPU]}cores",
    }
)
#: The least a resource must lend to count as lent: a hub counts a rig as
#: giving (standby, a starter) only while one of its resources reaches its
#: kind's floor, so a 1 MiB card or a single core earns nothing. Memory kinds
#: in MiB (:data:`LEND_FLOOR_MB`), ``cpu`` in cores (:data:`LEND_FLOOR_CORES`).
LEND_FLOOR_MB: Mapping[str, int] = MappingProxyType(
    {
        RESOURCE_GPU: 2048,
        RESOURCE_UNIFIED: 4096,
        RESOURCE_RAM: 8192,
    }
)
LEND_FLOOR_CORES = 2
#: The oldest DDR generation host memory may be and count as lent: DDR4.
RAM_DDR_MIN = 4


def shares_ram(kind: str) -> bool:
    """Whether a resource of ``kind`` lends memory that is the host's: a
    ``unified`` device's alone, which a hub counts once, as the card's."""
    return kind == RESOURCE_UNIFIED


def _is_int(value: object) -> bool:
    return type(value) is int


def _need(ok: bool, field: str, why: str) -> None:
    if not ok:
        raise ValueError(f"{field}: {why}")


def _one_of(value: object, values: tuple[str, ...], field: str) -> None:
    _need(type(value) is str and value in values, field, f"not one of {values}")


def _text(value: object, most: int, field: str) -> None:
    """Printable text a hub may show, 1 to ``most`` characters, with no
    invisible format character and no lone surrogate."""
    ok = (
        type(value) is str
        and len(value) <= most
        and RESOURCE_NAME.fullmatch(value) is not None
        and FORMAT_CHARACTERS.search(value) is None
    )
    if ok:
        assert isinstance(value, str)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            ok = False
    _need(ok, field, f"not 1 to {most} printable characters")


def _kind_and_index(kind: object, index: object) -> None:
    _one_of(kind, RESOURCE_KINDS, "kind")
    _need(
        _is_int(index) and 0 <= index <= MAX_RESOURCE_INDEX,  # type: ignore[operator]
        "index",
        f"not 0 to {MAX_RESOURCE_INDEX}",
    )


@dataclass(frozen=True, kw_only=True)
class Resource:
    """One thing a rig lends, as its hello advertises it.

    ``index`` counts per kind; a card kind's index is its card index.
    ``total_mb`` is the MiB lent, at least 1 (0 for ``cpu``: memory lent beside
    cores is a ``ram`` resource) and ``free_mb`` the MiB free, once read;
    ``figure`` says whether those two are an estimate or a reading. ``cores``
    is set for ``cpu`` alone. ``ddr`` is a ``ram`` resource's DDR generation
    (3, 4, 5, at most :data:`MAX_RAM_DDR`), None when the reader could not
    tell, and is set for ``ram`` alone. ``bandwidth_gbps`` is the memory
    bandwidth, when known, and ``bandwidth_figure`` says which it is, set
    with it alone. A ``unified`` device's memory is the host's
    (:func:`shares_ram`). A hub mirroring these rules refuses a non-finite
    bandwidth, as JSON's ``Infinity`` parses to one.

    A ``cpu`` resource serves whole models only, never a pipeline stage: it
    runs a small model end to end and holds no layers of a split one.
    """

    kind: str
    index: int
    name: str
    total_mb: int
    free_mb: int | None = None
    cores: int | None = None
    ddr: int | None = None
    bandwidth_gbps: float | None = None
    bandwidth_figure: str | None = None
    figure: str
    backend: str

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this resource
        keeps every rule a hub holds it to."""
        _kind_and_index(self.kind, self.index)
        _text(self.name, RESOURCE_NAME_MAX, "name")
        cpu = self.kind == RESOURCE_CPU
        least, most = (0, 0) if cpu else (1, RESOURCE_MAX_MB)
        _need(
            _is_int(self.total_mb) and least <= self.total_mb <= most,
            "total_mb",
            f"not {least} to {most} MiB for {self.kind}",
        )
        _need(
            self.free_mb is None
            or (_is_int(self.free_mb) and 0 <= self.free_mb <= self.total_mb),
            "free_mb",
            "not null or 0 to total_mb",
        )
        if cpu:
            _need(
                _is_int(self.cores)
                and self.cores is not None
                and 1 <= self.cores <= MAX_RESOURCE_CORES,
                "cores",
                f"not 1 to {MAX_RESOURCE_CORES} for cpu",
            )
        else:
            _need(self.cores is None, "cores", "set for a kind that is not cpu")
        if self.kind == RESOURCE_RAM:
            _need(
                self.ddr is None
                or (_is_int(self.ddr) and 1 <= self.ddr <= MAX_RAM_DDR),
                "ddr",
                f"not null or 1 to {MAX_RAM_DDR}",
            )
        else:
            _need(self.ddr is None, "ddr", "set for a kind that is not ram")
        bandwidth = self.bandwidth_gbps
        _need(
            bandwidth is None
            or (
                type(bandwidth) in (int, float)
                and 0 < bandwidth <= MAX_BANDWIDTH_GBPS  # NaN fails both
            ),
            "bandwidth_gbps",
            f"not null or a number over 0 to {MAX_BANDWIDTH_GBPS}",
        )
        if bandwidth is None:
            _need(
                self.bandwidth_figure is None,
                "bandwidth_figure",
                "set with no bandwidth_gbps",
            )
        else:
            _one_of(self.bandwidth_figure, FIGURE_KINDS, "bandwidth_figure")
        _one_of(self.figure, FIGURE_KINDS, "figure")
        _one_of(self.backend, RESOURCE_BACKENDS, "backend")
        host = self.kind in (RESOURCE_RAM, RESOURCE_CPU)
        _need(
            (self.backend == BACKEND_CPU) is host,
            "backend",
            "not cpu for ram and cpu, or cpu for a card",
        )


@dataclass(frozen=True, kw_only=True)
class ResourceReading:
    """What a heartbeat reads of one advertised memory resource: its ``kind``
    and ``index``, as the hello named it, and the MiB free now (``free_mb``).
    A ``cpu`` resource lends no memory, so it has no reading."""

    kind: str
    index: int
    free_mb: int

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this reading
        keeps every rule a hub holds it to."""
        _kind_and_index(self.kind, self.index)
        _need(self.kind != RESOURCE_CPU, "kind", "cpu, which has no memory to read")
        _need(
            _is_int(self.free_mb) and 0 <= self.free_mb <= RESOURCE_MAX_MB,
            "free_mb",
            f"not 0 to {RESOURCE_MAX_MB} MiB",
        )


def _fit(
    items: Sequence[Resource] | Sequence[ResourceReading], once: tuple[str, ...]
) -> None:
    _need(len(items) <= MAX_RESOURCES, "resources", f"more than {MAX_RESOURCES}")
    for item in items:
        item.validate()
    keys = [(item.kind, item.index) for item in items]
    _need(len(set(keys)) == len(keys), "resources", "a kind and index twice")
    cards = [item.index for item in items if item.kind in CARD_KINDS]
    _need(len(cards) <= MAX_CARDS, "resources", f"more than {MAX_CARDS} cards")
    _need(len(set(cards)) == len(cards), "resources", "a card index twice")
    for kind in once:
        _need(
            sum(item.kind == kind for item in items) <= 1,
            "resources",
            f"more than one {kind}",
        )


def resources_fit(resources: Sequence[Resource]) -> None:
    """Raise ValueError unless one advert may name ``resources``: at most
    :data:`MAX_RESOURCES`, each valid (:meth:`Resource.validate`), each
    ``(kind, index)`` once, at most :data:`MAX_CARDS` cards, each card index
    once across :data:`CARD_KINDS`, and at most one of each kind in
    :data:`ONE_PER_RIG`: one ``unified`` device, one ``ram``, one ``cpu``."""
    _fit(resources, ONE_PER_RIG)


def counts_as_lent(resource: Resource) -> bool:
    """Whether ``resource`` reaches its kind's lending floor: ``cpu`` lends at
    least :data:`LEND_FLOOR_CORES` cores, any other kind at least
    :data:`LEND_FLOOR_MB` of its kind. A hub counts a rig as giving only while
    one of its resources does; a product refuses to lend less.

    Host memory must also be DDR4 or newer (:data:`RAM_DDR_MIN`): a ``ram``
    resource whose generation is known to be older (``ddr`` 3 or less) never
    counts, whatever its size. One whose generation the reader could not tell
    (``ddr`` None) counts by its size alone. Linux reads the memory type from
    the firmware's SMBIOS table only as root, and the product asks for no
    sudo, so an unknown generation is the usual Linux answer and is not held
    against the rig; Windows reads it from WMI. An Apple Silicon Mac's memory
    is its ``unified`` device's, not ``ram``, so this rule never touches it."""
    if resource.kind == RESOURCE_CPU:
        return (resource.cores or 0) >= LEND_FLOOR_CORES
    ddr = resource.ddr
    if resource.kind == RESOURCE_RAM and ddr is not None and ddr < RAM_DDR_MIN:
        return False
    return resource.total_mb >= LEND_FLOOR_MB[resource.kind]


def readings_fit(readings: Sequence[ResourceReading]) -> None:
    """Raise ValueError unless one heartbeat may carry ``readings``, by the
    rules of :func:`resources_fit` (each card index once across
    :data:`CARD_KINDS` among them), but for how many unified devices: a card's
    reading is held by its index, and how many unified devices a rig has is
    its advert's to say. Whether each names an advertised resource, and its
    ``free_mb`` that resource's ``total_mb`` at most, is the hub's to hold
    against the advert it keeps, which reads nothing of one it does not."""
    _fit(readings, _ONE_PER_HEARTBEAT)


@dataclass(frozen=True, kw_only=True)
class Host:
    """The host a rig runs on, as its hello names it: ``os`` one of
    :data:`HOST_OS`, ``arch`` one of :data:`HOST_ARCH`, and the system's
    ``version``, 1 to :data:`HOST_VERSION_MAX` printable characters."""

    os: str
    arch: str
    version: str

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this host keeps
        every rule a hub holds it to."""
        _one_of(self.os, HOST_OS, "os")
        _one_of(self.arch, HOST_ARCH, "arch")
        _text(self.version, HOST_VERSION_MAX, "version")


def cards_from_resources(resources: Sequence[Resource]) -> list[dict[str, Any]]:
    """The legacy ``cards[]`` a hello carries, made from ``resources``.

    The advert must fit (:func:`resources_fit`, which raises ValueError). Each
    ``gpu`` and ``unified`` resource is one card at its index, by index, with
    its name and memory; a hub that reads only cards takes a unified device's
    memory for the card's own. A ``free_mb`` not read yet is all free: the
    next heartbeat's reading corrects it. Host memory and cores make no card.
    """
    resources_fit(resources)
    return [
        {
            "index": r.index,
            "name": r.name,
            "vram_total_mb": r.total_mb,
            "vram_free_mb": r.total_mb if r.free_mb is None else r.free_mb,
        }
        for r in sorted(resources, key=lambda r: r.index)
        if r.kind in CARD_KINDS
    ]


def card_readings_from(readings: Sequence[ResourceReading]) -> list[dict[str, int]]:
    """The legacy card readings a heartbeat carries, made from ``readings``.

    The readings must fit (:func:`readings_fit`, which raises ValueError).
    Each ``gpu`` and ``unified`` reading is one card's, by index, with the MiB
    free now; host memory makes none.
    """
    readings_fit(readings)
    return [
        {"index": r.index, "vram_free_mb": r.free_mb}
        for r in sorted(readings, key=lambda r: r.index)
        if r.kind in CARD_KINDS
    ]


# --- what a member chooses to lend ----------------------------------------------

#: The ack field carrying what a member chooses to lend on a rig
#: (:class:`Lending`), set on the hub, for the rig's agent to lend.
LENDING_FIELD = "lending"


def _lent_or_none(value: object, floor: int, most: int, field: str) -> None:
    """Refuse ``value`` unless it is 0, lending none, or ``floor`` to ``most``."""
    _need(
        _is_int(value) and (value == 0 or value in range(floor, most + 1)),
        field,
        f"not 0 or {floor} to {most}",
    )


@dataclass(frozen=True, kw_only=True)
class Lending:
    """What a member chooses to lend on one rig: ``cards``, the card indexes
    lent whole (None for every card the rig has, empty for none), ``ram_mb``
    the host memory lent, in MiB, and ``cpu_cores`` the host cores lent.
    Memory and cores are each 0, lending none, or at least their kind's
    lending floor (:data:`LEND_FLOOR_MB`, :data:`LEND_FLOOR_CORES`): an
    amount under it would count as nothing lent, so it is never asked for."""

    cards: tuple[int, ...] | None
    ram_mb: int
    cpu_cores: int

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this lending
        keeps every rule a hub holds it to."""
        cards = self.cards
        if cards is not None:
            _need(
                type(cards) is tuple and len(cards) <= MAX_CARDS,
                "cards",
                f"not null or at most {MAX_CARDS} card indexes",
            )
            _need(
                all(_is_int(i) and 0 <= i <= MAX_RESOURCE_INDEX for i in cards),
                "cards",
                f"an index not 0 to {MAX_RESOURCE_INDEX}",
            )
            _need(len(set(cards)) == len(cards), "cards", "an index twice")
        _lent_or_none(
            self.ram_mb, LEND_FLOOR_MB[RESOURCE_RAM], RESOURCE_MAX_MB, "ram_mb"
        )
        _lent_or_none(self.cpu_cores, LEND_FLOOR_CORES, MAX_RESOURCE_CORES, "cpu_cores")


# --- the RPC protocol a split model's workers speak -------------------------------

#: The advert and offer field naming the llama.cpp RPC protocol version a rig
#: speaks (:class:`RpcProto`).
RPC_PROTO_FIELD = "rpc_proto"

#: The largest value either part of an :class:`RpcProto` may hold: the hello
#: reply carries each as one byte (``rpc_msg_hello_rsp`` holds ``uint8_t
#: major, minor, patch`` in ``ggml/src/ggml-rpc/ggml-rpc.cpp``).
RPC_PROTO_MAX = 255


@dataclass(frozen=True, kw_only=True)
class RpcProto:
    """The llama.cpp RPC protocol version a rig speaks: ``major`` and
    ``minor``, each a whole number from 0 to :data:`RPC_PROTO_MAX`. Its patch
    is never compared, so it is not carried."""

    major: int
    minor: int

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless both are whole
        numbers from 0 to :data:`RPC_PROTO_MAX`."""
        for field in ("major", "minor"):
            value = getattr(self, field)
            _need(
                _is_int(value) and 0 <= value <= RPC_PROTO_MAX,
                field,
                f"not a whole number in 0..{RPC_PROTO_MAX}",
            )


def rpc_compatible(head: RpcProto, worker: RpcProto) -> bool:
    """Whether a head may take ``worker`` as an RPC worker: the same major, and
    the worker's minor no newer than the head's.

    This is llama.cpp's own handshake: the head (the RPC client) refuses a
    server whose major differs or whose minor is greater than its own
    (``negotiate_hello`` in ``ggml/src/ggml-rpc/ggml-rpc.cpp``,
    https://github.com/ggml-org/llama.cpp/blob/7ecb57f7adbea2928aa468ad2aecf05b10725ad4/ggml/src/ggml-rpc/ggml-rpc.cpp).
    A major changes on a break; a newer head speaks an older minor.
    """
    return worker.major == head.major and worker.minor <= head.minor


# --- the devices a head runs a model on -------------------------------------------

#: The kinds of device a ``head_start`` names: a card lent on the head's own
#: rig (``local``), a worker's card reached over the tunnel (``rpc``), and the
#: head's own host memory and cores (``cpu``), which serve a whole model only,
#: never a pipeline stage (see :class:`Resource`).
HEAD_DEVICE_LOCAL = "local"
HEAD_DEVICE_RPC = "rpc"
HEAD_DEVICE_CPU = "cpu"
HEAD_DEVICE_KINDS: tuple[str, ...] = (
    HEAD_DEVICE_LOCAL,
    HEAD_DEVICE_RPC,
    HEAD_DEVICE_CPU,
)


# --- how fast a device decodes, by its memory bandwidth ----------------------------

#: Bytes in the decimal GB a bandwidth in GB/s is stated in.
BYTES_PER_DECIMAL_GB = 1e9
#: Bytes in a GiB, the unit a model's weights are planned in.
BYTES_PER_GIB = 1 << 30
#: Milliseconds in a second.
MS_PER_S = 1000

#: Decode efficiency: measured text-generation speed over the speed the
#: bandwidth alone would allow, ``tg x model_GB / bandwidth_GBps``. Fitted to
#: llama.cpp's own Apple-silicon table, llama-bench tg128 of a dense 7B model at
#: F16, Q8_0 and Q4_0 over M1..M4 (llama.cpp discussion 4167,
#: https://github.com/ggml-org/llama.cpp/discussions/4167): medians 0.83 (F16),
#: 0.79 (Q8_0) and 0.69 (Q4_0), falling as the quantisation shrinks (dequant
#: cost) and as bandwidth rises (an 800 GB/s part is compute-bound on a 7B
#: model). The values below sit under those medians, so an estimate errs slow:
#: 0.75 for 16-bit and 8-bit weights, 0.60 for 4-bit to 6-bit ones (Q5/Q6 were
#: not measured; they take the 4-bit figure, the lower of the two they sit
#: between). From :data:`HIGH_BANDWIDTH_GBPS` up an Apple chip takes at most
#: :data:`HIGH_BANDWIDTH_EFFICIENCY` for its class: the 800 GB/s Ultra runs gave
#: 0.50..0.60 at Q8_0 (0.57..0.71 at F16), so 0.50, the lowest, and 0.36..0.45
#: at Q4_0 (median 0.42), so 0.40, under five of the six runs. The fit is Apple
#: silicon's under Metal; an NVIDIA card takes the same shares, unchecked under
#: CUDA. A current llama.cpp build runs about 1.2x faster than the build those
#: rows used; no allowance is made for it. A quantisation under 4 bits, or
#: 32-bit weights, was not measured, and gets no efficiency.
DECODE_EFFICIENCY: Mapping[str, float] = MappingProxyType({"8bit": 0.75, "4bit": 0.60})
HIGH_BANDWIDTH_GBPS = 800.0
HIGH_BANDWIDTH_EFFICIENCY: Mapping[str, float] = MappingProxyType(
    {"8bit": 0.50, "4bit": 0.40}
)
#: The vendor whose chips the efficiencies were fitted on, and the only one the
#: high-bandwidth ceiling was seen on.
FITTED_ON = "apple"
#: Quantisation names, by the efficiency class they decode at. Matched on the
#: name's start, case-insensitively, after a ``UD-`` prefix: ``Q4_K_M`` is
#: ``q4``, ``IQ4_XS`` is ``iq4``, ``UD-Q4_K_XL`` is ``q4``.
QUANT_CLASSES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "8bit": ("f16", "bf16", "q8"),
        "4bit": ("q4", "iq4", "mxfp4", "q5", "q6"),
    }
)
_QUANT_PREFIX = "ud-"


def quant_class(quant: str) -> str | None:
    """The efficiency class of a quantisation name, None when it has none."""
    name = quant.strip().lower().removeprefix(_QUANT_PREFIX)
    for klass, prefixes in QUANT_CLASSES.items():
        if name.startswith(prefixes):
            return klass
    return None


def decode_efficiency(
    bandwidth_gbps: float, quant: str, *, vendor: str = FITTED_ON
) -> float | None:
    """The decode efficiency for this bandwidth, quantisation and vendor, None
    when the quantisation has no class. The high-bandwidth ceiling holds for
    the vendor the shares were fitted on alone."""
    klass = quant_class(quant)
    if klass is None:
        return None
    eff = DECODE_EFFICIENCY[klass]
    if vendor == FITTED_ON and bandwidth_gbps >= HIGH_BANDWIDTH_GBPS:
        eff = min(eff, HIGH_BANDWIDTH_EFFICIENCY[klass])
    return eff


def decode_ms_per_gib(
    bandwidth_gbps: float, quant: str, *, vendor: str = FITTED_ON
) -> float | None:
    """Milliseconds a token takes per GiB of weights it reads, on a device of
    ``bandwidth_gbps`` (decimal GB/s) at the share of it
    :func:`decode_efficiency` states; None when the quantisation has no class
    or the bandwidth is not over 0. Each token reads every weight once, so a
    model of ``n`` GiB decodes a token in ``n`` times this."""
    eff = decode_efficiency(bandwidth_gbps, quant, vendor=vendor)
    if eff is None or not bandwidth_gbps > 0:
        return None
    return MS_PER_S * BYTES_PER_GIB / (eff * bandwidth_gbps * BYTES_PER_DECIMAL_GB)
