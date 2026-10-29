"""The wire the hub serves a rider, defined once: the product's, the hub's by import.

The hub serves models to a member's rigs and the product rides them: relief
rungs (hitchhike), the ladder a rider reports, the units a host advertises,
the relay that carries a ride, and the ``/v1`` refusals a rider reads. Every
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
* what a rig lends, as resources (:class:`Resource`) on a host
  (:class:`Host`), and a heartbeat's reading of each
  (:class:`ResourceReading`, :func:`readings_fit`): their kinds
  (:data:`RESOURCE_KINDS`, the card kinds :data:`CARD_KINDS`), backends
  (:data:`RESOURCE_BACKENDS`), what a figure is (:data:`FIGURE_KINDS`), the
  host a rig runs on (:data:`HOST_OS`, :data:`HOST_ARCH`), how many one advert
  may name (:data:`MAX_RESOURCES`, :func:`resources_fit`), the legacy cards
  they make (:func:`cards_from_resources`) and the unit standby is counted in
  per kind (:data:`STANDBY_UNITS`);
* the hub's published JSON Schemas (:data:`SCHEMAS`), shipped inside this
  package and read with :func:`schema_bytes` and :func:`schema`.

A pattern is held unanchored and matched whole (``fullmatch``); a JSON Schema
or a pydantic type writes it as ``^<pattern>$``. Nothing here is a validator
of a whole message: the hub's pydantic models and the product's readers stay
two, and each value they share is held to the schemas by the product's tests.

Stdlib only, and nothing from ``mcgyvr.cli`` or ``mcgyvr.rig``: the offline
core and the hub import this module without either.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
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
#: The backend a resource computes with.
RESOURCE_BACKENDS: tuple[str, ...] = ("cuda", "metal", "vulkan", "rocm", "cpu")
#: What a resource's figures are: an estimate, or the rig's own reading. A
#: number on the wire says which it is.
FIGURE_KINDS: tuple[str, ...] = ("estimate", "reading")
#: The operating system and the architecture a rig's host names in its hello.
HOST_OS: tuple[str, ...] = ("linux", "darwin", "windows")
HOST_ARCH: tuple[str, ...] = ("x86_64", "arm64")
#: Most resources one advert may name.
MAX_RESOURCES = 32
#: Highest index a resource may have: a card's highest index.
MAX_RESOURCE_INDEX = 63
#: Most logical cores one ``cpu`` resource may lend.
MAX_RESOURCE_CORES = 1024
#: Longest host version a hello may name, in characters.
HOST_VERSION_MAX = 64
#: A resource's name is text a hub may show, as a card's is: no control
#: characters, no C1 controls, no bidi embedding, override or isolate marks;
#: at most :data:`RESOURCE_NAME_MAX` characters.
RESOURCE_NAME = re.compile("[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]+")
RESOURCE_NAME_MAX = 128
#: Largest memory figure a resource may carry, in MiB, as a card's.
RESOURCE_MAX_MB = 1 << 30
#: The unit standby is counted in for each kind: a card is a card whether its
#: memory is its own or the host's, so a unified device is a card and never
#: also memory; host memory is counted per 16 GiB and cores per 8. Names only:
#: what a unit earns is the hub's setting.
STANDBY_UNITS: Mapping[str, str] = MappingProxyType(
    {
        RESOURCE_GPU: "card",
        RESOURCE_UNIFIED: "card",
        RESOURCE_RAM: "16GiB",
        RESOURCE_CPU: "8cores",
    }
)


def _is_int(value: object) -> bool:
    return type(value) is int


@dataclass(frozen=True, kw_only=True)
class Resource:
    """One thing a rig lends, as its hello advertises it.

    ``index`` counts per kind; a card kind's index is its card index.
    ``total_mb`` is the MiB lent (0 for ``cpu``: memory lent beside cores is a
    ``ram`` resource) and ``free_mb`` the MiB free, once read. ``cores`` is set
    for ``cpu`` alone. ``shared_with_ram`` is true for ``unified`` alone: its
    memory is the host's, counted once. ``figure`` says whether
    ``bandwidth_gbps`` and ``total_mb`` are an estimate or a reading.

    A ``cpu`` resource serves whole models only, never a pipeline stage: it
    runs a small model end to end and holds no layers of a split one.
    """

    kind: str
    index: int
    name: str
    total_mb: int
    free_mb: int | None = None
    cores: int | None = None
    shared_with_ram: bool
    bandwidth_gbps: float | None = None
    figure: str
    backend: str

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this resource
        keeps every rule a hub holds it to."""
        _kind_and_index(self.kind, self.index)
        _need(
            isinstance(self.name, str)
            and len(self.name) <= RESOURCE_NAME_MAX
            and RESOURCE_NAME.fullmatch(self.name) is not None,
            "name",
            f"not 1 to {RESOURCE_NAME_MAX} printable characters",
        )
        _need(
            _is_int(self.total_mb) and 0 <= self.total_mb <= RESOURCE_MAX_MB,
            "total_mb",
            f"not 0 to {RESOURCE_MAX_MB} MiB",
        )
        cpu = self.kind == RESOURCE_CPU
        _need(not cpu or self.total_mb == 0, "total_mb", "not 0 for cpu")
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
        _need(
            type(self.shared_with_ram) is bool
            and self.shared_with_ram is (self.kind == RESOURCE_UNIFIED),
            "shared_with_ram",
            "not true for unified and false for every other kind",
        )
        bandwidth = self.bandwidth_gbps
        _need(
            bandwidth is None
            or (
                type(bandwidth) in (int, float)
                and math.isfinite(bandwidth)
                and bandwidth > 0
            ),
            "bandwidth_gbps",
            "not null or a finite number > 0",
        )
        _need(self.figure in FIGURE_KINDS, "figure", f"not one of {FIGURE_KINDS}")
        _need(
            self.backend in RESOURCE_BACKENDS,
            "backend",
            f"not one of {RESOURCE_BACKENDS}",
        )


def _need(ok: bool, field: str, why: str) -> None:
    if not ok:
        raise ValueError(f"{field}: {why}")


def _kind_and_index(kind: object, index: object) -> None:
    _need(kind in RESOURCE_KINDS, "kind", f"not one of {RESOURCE_KINDS}")
    _need(
        _is_int(index) and 0 <= index <= MAX_RESOURCE_INDEX,  # type: ignore[operator]
        "index",
        f"not 0 to {MAX_RESOURCE_INDEX}",
    )


def _unique_keys(items: Sequence[Resource] | Sequence[ResourceReading]) -> None:
    _need(len(items) <= MAX_RESOURCES, "resources", f"more than {MAX_RESOURCES}")
    keys = [(item.kind, item.index) for item in items]
    _need(len(set(keys)) == len(keys), "resources", "a kind and index twice")


@dataclass(frozen=True, kw_only=True)
class ResourceReading:
    """What a heartbeat reads of one advertised resource: its ``kind`` and
    ``index``, as the hello named it, and the MiB free now (``free_mb``)."""

    kind: str
    index: int
    free_mb: int

    def validate(self) -> None:
        """Raise ValueError, naming the field at fault, unless this reading
        keeps every rule a hub holds it to."""
        _kind_and_index(self.kind, self.index)
        _need(
            _is_int(self.free_mb) and 0 <= self.free_mb <= RESOURCE_MAX_MB,
            "free_mb",
            f"not 0 to {RESOURCE_MAX_MB} MiB",
        )


def readings_fit(readings: Sequence[ResourceReading]) -> None:
    """Raise ValueError unless one heartbeat may carry ``readings``: at most
    :data:`MAX_RESOURCES`, each ``(kind, index)`` once."""
    _unique_keys(readings)


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
        _need(self.os in HOST_OS, "os", f"not one of {HOST_OS}")
        _need(self.arch in HOST_ARCH, "arch", f"not one of {HOST_ARCH}")
        _need(
            isinstance(self.version, str)
            and len(self.version) <= HOST_VERSION_MAX
            and RESOURCE_NAME.fullmatch(self.version) is not None,
            "version",
            f"not 1 to {HOST_VERSION_MAX} printable characters",
        )


def resources_fit(resources: Sequence[Resource]) -> None:
    """Raise ValueError unless one advert may name ``resources``: at most
    :data:`MAX_RESOURCES`, each ``(kind, index)`` once, and each card index
    once across :data:`CARD_KINDS`. Each resource's own rules are
    :meth:`Resource.validate`'s."""
    _unique_keys(resources)
    cards = [r.index for r in resources if r.kind in CARD_KINDS]
    _need(len(set(cards)) == len(cards), "resources", "a card index twice")


def cards_from_resources(resources: Iterable[Resource]) -> list[dict[str, Any]]:
    """The legacy ``cards[]`` a hello carries, made from ``resources``.

    Each ``gpu`` and ``unified`` resource is one card at its index, by index,
    with its name and memory. A ``free_mb`` not read yet is all free: the
    next heartbeat's reading corrects it. Host memory and cores make no card.
    The hello's own card count limit still applies.

    Raises ValueError for a resource that breaks a rule
    (:meth:`Resource.validate`) and for a card index named twice.
    """
    cards: dict[int, dict[str, Any]] = {}
    for resource in resources:
        resource.validate()
        if resource.kind not in CARD_KINDS:
            continue
        if resource.index in cards:
            raise ValueError(f"cards: card index {resource.index} twice")
        cards[resource.index] = {
            "index": resource.index,
            "name": resource.name,
            "vram_total_mb": resource.total_mb,
            "vram_free_mb": (
                resource.total_mb if resource.free_mb is None else resource.free_mb
            ),
        }
    return [cards[index] for index in sorted(cards)]


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
