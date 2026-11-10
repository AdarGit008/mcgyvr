"""The hub wire, defined once: the product's, the hub's by import.

The hub serves models to a member's rigs and the product rides them: relief
rungs (hitchhike), the ladder a rider reports, the units a host advertises,
the resources a rig lends, the relay that carries a ride, the ``/v1``
refusals a rider reads, and the agent channel a rig holds to the hub. Every
limit, pattern and code list both sides hold for that is defined here, once.
The product's modules import them (the rig's ``protocol`` and ``sessionwire``
name them under their own names, as the same objects). The hub reads them
through its pinned product as it drops its own copies: some it imports
already (the resource, identity-key and seal values among them), the agent
channel's it still spells itself, and each value it spells is held to the
published schemas by the product's tests until it reads it from here. What
is here:

* the agent channel: its version (:data:`PROTOCOL_VERSION`, and the UDP
  packets' :data:`UDP_VERSION`), the frame limits (``MAX_MESSAGE_BYTES``,
  ``MAX_FRAMES_PER_SECOND``, ``MAX_ERROR_TEXT``, ``HEARTBEAT_INTERVAL_S``),
  the counts a frame may carry (models, sessions, endpoints, features, peers,
  allowed IPs, devices, RTT samples, STUN endpoints), a model's, a head's, a
  probe's, a tunnel walk's and a port forward's bounds and the defaults the
  schema states for them (``MAX_*``, ``MIN_*``, ``DEFAULT_*``, ``PORT_MAP_*``),
  the roles (:data:`RIG_ROLES`, :data:`RigRole`), session states
  (:data:`SESSION_STATES`), relay outcomes (:data:`RELAY_OUTCOMES`) and the
  statuses a relayed response may carry (:data:`RELAY_STATUS`), the shapes of
  its text fields (:data:`MESSAGE_ID`, :data:`TAG`,
  :data:`MACHINE_ID`, :data:`AGENT_VERSION`, :data:`DIGEST`,
  :data:`SHORT_TAG`, :data:`RUNTIME`, :data:`ENDPOINT_HOST`,
  :data:`WIREGUARD_KEY`, :data:`IPV4`, :data:`IPV4_CIDR`,
  :data:`CONTENT_TYPE`, :data:`BASE64`, :data:`TOKEN`, :data:`TICKET`), and
  its codes: :class:`CloseCode`, the channel's :class:`ErrorCode`, a
  refusal's :class:`SessionCode`, all of them :data:`AGENT_ERROR_CODES`;
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
  (:data:`RUNG_BUSY`, :data:`MODEL_UNPLACED`, :data:`MODEL_NOT_FOUND`,
  :data:`OUT_OF_SCOPE`);
* the chat request fields the hub forwards to a unit
  (:data:`FORWARDED_FIELDS`, :data:`CHAT_TEMPLATE_KEYS`);
* a sealed ride's shapes: the envelope a request carries
  (:data:`SEALED_FIELD`, :data:`SEAL_VERSION`, ``SEAL_*`` patterns), the key a
  unit advertises and a relief rung lists (:data:`SEAL_KEY_FIELD`), what such
  a request and its answer leave in clear (:data:`SEALED_CLEAR_FIELDS`,
  :data:`SEALED_ANSWER_CLEAR_FIELDS`) and the refusal of a key no unit holds
  (:data:`SEAL_KEY_UNKNOWN`);
* the header naming who may serve a request (:data:`SCOPE_HEADER`,
  :data:`SCOPE_VALUES`, narrowest first: :func:`narrowest_scope`), and the
  pool each scope is served from
  (:data:`SCOPE_POOLS`, :func:`serving_pool`);
* where the hub lists the models a scope may use (:data:`MODELS_PATH` under
  :data:`API_ROOT`), each with its units' slots (:data:`MODEL_SLOTS`);
* the use cases (:data:`USE_CASES`) with the model category each is
  recommended (:data:`USE_CASE_CATEGORY`), the header a request names its own in
  (:data:`USE_CASE_HEADER`), and which use cases each pool serves
  (:data:`POOL_USE_CASES`, :func:`pool_serves`): the hub refuses the rest;
* the hub's published JSON Schemas (:data:`SCHEMAS`), shipped inside this
  package and read with :func:`schema_bytes` and :func:`schema`, and the
  version the rider schema is published at (:data:`RIDER_SCHEMA_VERSION`);
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
* a rig's identity key and the signature it puts on each session's tunnel
  key (:data:`IDENTITY_KEY_FIELD`, :data:`SESSION_KEY_SIG_FIELD`, their shapes
  :data:`IDENTITY_KEY` and :data:`IDENTITY_SIG`, the bytes signed
  :func:`session_key_message`), and the fingerprint people compare
  (:func:`identity_fingerprint`);
* the devices a head runs a model on (:data:`HEAD_DEVICE_KINDS`);
* how fast a device decodes by its memory bandwidth
  (:func:`decode_ms_per_gib`, with :data:`DECODE_EFFICIENCY`, and whether a
  device is of the vendor that was fitted on, :func:`fitted_on`);
* the ``port_map_report`` ``error`` tags of a forward the rig itself refuses
  (:data:`PORT_MAP_NOT_ALLOWED`, :data:`PORT_MAP_PERMANENT_ONLY`), which the
  hub tells apart from a router's refusal.

A pattern is held unanchored and matched whole (``fullmatch``); a JSON Schema
or a pydantic type writes it as ``^<pattern>$``.

Not here: a validator of a whole message. The hub's pydantic models and the
product's readers and builders (``mcgyvr.rig.protocol``,
``mcgyvr.rig.sessionwire``) stay two, each bounded by the values here, and
the hub renders the schemas from its models (the product's tests hold each
shared value to them). Nor the upstream path a relay fetches, which is the
agent's alone. Not yet here, so still spelled on both sides and held by the
schemas: the feature names an agent lists (``x-features``) and the UDP
packet formats (``x-udp``); ``mcgyvr.rig.udpwire`` runs in the tunnel
without this package, so it keeps its own copy of what it needs,
:data:`UDP_VERSION` among them, held to this one by test. A resource, a
reading and a host carry their own rules (``validate()``,
:func:`resources_fit`, :func:`readings_fit`) for both sides to call; their
values join the schemas once the hub publishes them.

Stdlib only, and nothing from ``mcgyvr.cli`` or ``mcgyvr.rig``: the offline
core and the hub import this module without either.
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from types import MappingProxyType
from typing import Any, Literal, get_args

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
#: Longest base64 text that still decodes to one relay chunk, rounded up to
#: whole four-character groups.
RELAY_MAX_CHUNK_B64 = 4 * -(-RELAY_MAX_CHUNK_BYTES // 3)
#: How a relayed call ends.
RELAY_OUTCOMES: tuple[str, ...] = (
    "complete",
    "error",
    "cancelled",
    "timeout",
    "too_large",
)

# --- the agent channel -------------------------------------------------------
# The websocket a rig's agent holds to the hub (the protocol schema): its
# envelope, the limits and shapes of the frames on it, and its close and error
# codes. The rig's ``protocol`` and ``sessionwire`` modules name these; the
# hub's pydantic models state the same bounds (its own copies, until its pin
# reaches these names).

#: The version an agent and a hub write in ``v`` and the only one they read:
#: another number is refused as ``unsupported_version``.
PROTOCOL_VERSION = 1
#: The version byte of the UDP packets beside the channel (binding, probe and
#: relay packets; the protocol schema's ``x-udp``). The rig's ``udpwire`` runs
#: in the tunnel without this package, so it keeps its own copy, held to this
#: one by the product's tests.
UDP_VERSION = 1
#: Largest frame, in bytes of UTF-8, either side reads or writes.
MAX_MESSAGE_BYTES = 64 * 1024
#: Frames per second one agent may send over its channel; the hub closes floods.
MAX_FRAMES_PER_SECOND = 100
#: Longest error text, in characters.
MAX_ERROR_TEXT = 500
#: The seconds a hub may set as the heartbeat interval in an ack, low and high.
HEARTBEAT_INTERVAL_S = (1, 3600)
#: Most models a hello may name, and most weight digests it may list.
MAX_MODELS = 64
#: Most live session ids a hello may list: the most sessions a rig runs at once.
MAX_SESSIONS_REPORTED = 4
#: Upper bound on a model file's size, and on the bytes one of its tensors takes.
MAX_MODEL_BYTES = 1 << 50
#: Upper bound on a model's layer count.
MAX_LAYERS = 4096
#: Upper bound on a model's embedding and head counts.
MAX_COUNT = 1 << 20
#: Upper bound on the key and value cache a model spends per token.
MAX_KV_BYTES_PER_TOKEN = 1 << 30
#: Most endpoints one offer or one peer may name.
MAX_ENDPOINTS = 8
#: Most features one offer may name.
MAX_FEATURES = 16
#: The roles a rig may offer in a session: at most both.
RigRole = Literal["head", "worker"]
RIG_ROLES: tuple[str, ...] = get_args(RigRole)

#: Most peers one tunnel or probe may name, allowed IPs one peer may carry,
#: devices one head may start on, and round-trip samples one report may carry.
MAX_PEERS = 15
MAX_ALLOWED_IPS = 4
MAX_DEVICES = 64
MAX_RTT_SAMPLES = 32
#: Largest round trip a report may carry, in microseconds.
MAX_RTT_US = 60_000_000
#: A head's context per slot, in tokens (also a model's trained context).
MIN_CTX = 256
MAX_CTX = 1 << 20
#: Largest one device's share in a tensor split.
MAX_TENSOR_SHARE = 1 << 20
#: Most layers a head may offload, and what a start gets when it names none.
MAX_GPU_LAYERS = 4096
DEFAULT_GPU_LAYERS = 999
#: The slots a start request gets when it leaves the field out (at most
#: :data:`MAX_SLOTS`).
DEFAULT_SLOTS = 1
#: A tunnel peer's keepalive, in seconds: the most, and the default.
MAX_KEEPALIVE_S = 600
DEFAULT_KEEPALIVE_S = 25
#: Highest port an endpoint may name; ports start at 1.
MAX_PORT = 65535
#: Longest log excerpt a session status carries, in characters.
LOG_EXCERPT_MAX_CHARS = 4000
#: Longest content type a relayed response names.
MAX_CONTENT_TYPE = 128
#: Highest percentage a report names (loss, progress).
MAX_PCT = 100
#: The HTTP statuses a relayed response may answer with: the lowest and the
#: highest.
RELAY_STATUS = (100, 599)
#: STUN-assisted probes: how many STUN endpoints one end may offer, how long
#: a probe stays open, how many echoes it sends and how far apart, and the
#: bulk payload and overall deadline used to measure throughput.
MAX_STUN_ENDPOINTS = 2
MIN_PROBE_TTL_S = 5
MAX_PROBE_TTL_S = 120
DEFAULT_PROBE_TTL_S = 30
MAX_PROBE_COUNT = 20
DEFAULT_PROBE_COUNT = 5
MIN_PROBE_INTERVAL_MS = 10
MAX_PROBE_INTERVAL_MS = 1000
DEFAULT_PROBE_INTERVAL_MS = 50
MAX_PROBE_BULK_BYTES = 256 * 1024
MIN_PROBE_DEADLINE_MS = 100
MAX_PROBE_DEADLINE_MS = 15_000
DEFAULT_PROBE_DEADLINE_MS = 5000
#: A tunnel's walk: seconds per candidate, and in all.
MAX_ATTEMPT_S = 30
MAX_CONNECT_TIMEOUT_S = 300
#: Largest rate a probe reports, in kbit/s (100 Gbit/s: a sanity bound).
MAX_RATE_KBPS = 100_000_000
#: The port forward: a block covers every tunnel port a rig may use at once,
#: its lease and its check, in seconds, and the states a report names.
PORT_MAP_PORTS = MAX_SESSIONS_REPORTED
MIN_PORT_MAP_LEASE_S = 120
MAX_PORT_MAP_LEASE_S = 86_400
DEFAULT_PORT_MAP_LEASE_S = 3600
MIN_PORT_CHECK_TTL_S = 5
MAX_PORT_CHECK_TTL_S = 60
DEFAULT_PORT_CHECK_TTL_S = 15
PORT_MAP_STATES: tuple[str, ...] = ("mapped", "failed", "released")
#: The states a session status may report.
SESSION_STATES: tuple[str, ...] = (
    "absent",
    "preparing",
    "prepared",
    "tunnel_up",
    "starting",
    "loading",
    "ready",
    "failed",
    "stopped",
)

#: The shapes the envelope's own fields take: message ids (which also name
#: sessions, requests and rigs), type tags (which also serve as error codes,
#: endpoint kinds and feature names), machine ids and agent versions.
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
TAG = re.compile(r"[a-z][a-z0-9_]{0,63}")
MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
AGENT_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")
#: The shapes of what an offer names: weight digests, architectures, runtimes
#: and endpoint hosts.
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SHORT_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
RUNTIME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}")
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
#: A WireGuard public key, an IPv4 address and an IPv4 network, as text.
WIREGUARD_KEY = re.compile(r"[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=")
IPV4 = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
IPV4_CIDR = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}")
#: A relayed response's content type, and a relay data frame's base64.
CONTENT_TYPE = re.compile(
    r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(; ?[A-Za-z0-9_-]+=[A-Za-z0-9_.-]+)?"
)
BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")
#: 16 random bytes as 32 hex digits: a probe or traversal token, a probe secret.
TOKEN = re.compile(r"[0-9a-f]{32}")
#: The ticket a relay grant carries, which binds a tunnel with the relay:
#: opaque to agents, URL-safe base64.
TICKET = re.compile(r"[A-Za-z0-9_-]{22,256}")


class CloseCode(enum.IntEnum):
    """The codes a hub closes the agent channel with, as the wire spells them.

    1008 is the websocket's own policy violation, and 4001 onwards are the
    hub's own reasons. Published as ``x-close-codes``.
    """

    POLICY = 1008  # the channel broke the websocket's rules, e.g. too many frames
    REVOKED = 4001  # the hub revoked this rig's token
    TIMEOUT = 4008  # this agent's heartbeats stopped reaching the hub
    SUPERSEDED = 4009  # another agent took this rig over with the same token


class ErrorCode(enum.StrEnum):
    """The channel's own error codes, sent in an ``error`` frame by either side.

    An ``error`` frame's code is an open set (any type tag), so this is what
    the two sides name about the channel itself; a refusal of a session or a
    relay carries a :class:`SessionCode`. Both together are
    :data:`AGENT_ERROR_CODES`.
    """

    BAD_MESSAGE = "bad_message"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNSUPPORTED_TYPE = "unsupported_type"
    EXPECTED_HELLO = "expected_hello"
    MACHINE_MISMATCH = "machine_mismatch"
    REVOKED = "revoked"
    TIMEOUT = "timeout"
    SUPERSEDED = "superseded"
    RATE_LIMITED = "rate_limited"


class SessionCode:
    """Codes a refusal carries to say why a rig would not take a request."""

    BUSY = "busy"
    NOT_CAPABLE = "not_capable"
    UNKNOWN_SESSION = "unknown_session"
    MODEL_MISSING = "model_missing"
    INSUFFICIENT_MEMORY = "insufficient_memory"
    TUNNEL_FAILED = "tunnel_failed"
    START_FAILED = "start_failed"
    NOT_READY = "not_ready"
    DUPLICATE = "duplicate"
    UPSTREAM_FAILED = "upstream_failed"
    TOO_LARGE = "too_large"
    CANCELLED = "cancelled"
    MODEL_MISMATCH = "model_mismatch"
    NO_PATH = "no_path"
    UNKNOWN_UNIT = "unknown_unit"
    #: A sealed ride that does not open: sealed to a key this agent no longer
    #: holds, tampered with, or no chat request once opened.
    BAD_SEAL = "bad_seal"
    #: The load stopped moving bytes for long enough that the head gave up.
    LOAD_STALLED = "load_stalled"
    #: A path to the peer does exist, but it lost every full-size packet: its
    #: MTU is too small to carry the tunnel.
    PATH_TOO_NARROW = "path_too_narrow"


#: Every error code the agent channel names, the channel's own first: the
#: protocol schema's ``x-error-codes`` (which lists them sorted).
AGENT_ERROR_CODES: tuple[str, ...] = (
    *(code.value for code in ErrorCode),
    *(value for name, value in vars(SessionCode).items() if name.isupper()),
)

#: The birthday-paradox hole punch: one side behind a symmetric (per-destination)
#: NAT, the other on a stable endpoint (cone NAT, port forward, owner-declared,
#: public). The non-symmetric side probes a bounded range of candidate ports on
#: the symmetric side's public IP while the symmetric side sends bursts at the
#: peer's stable endpoint, so its per-destination mapping lands inside the range.
#: The collision of the two sets is the birthday paradox: with BIRTHDAY_BURST_PORTS
#: bursts and BIRTHDAY_PROBE_PORTS probes the success chance is ~98% (the
#: published Tailscale curve, reproduced in the hub's ``tests/test_birthday.py``).
#: Endpoint kinds the hub emits for this rung (``Endpoint.kind`` is an open set).
BIRTHDAY_KIND = "birthday"  # probe the bounded range (the non-symmetric side)
# burst at the stable endpoint (the symmetric side)
BIRTHDAY_BURST_KIND = "birthday_burst"
#: The symmetric NAT's port space the model draws from, and the two counts the
#: hub sets on the wire: 256 bursts on the symmetric side, 1024 probes on the
#: non-symmetric side (~98%, see the module note).
BIRTHDAY_PORT_SPACE = 65536
BIRTHDAY_BURST_PORTS = 256
BIRTHDAY_PROBE_PORTS = 1024
#: The bounds on any one probe or burst count a rig may be asked for.
MIN_BIRTHDAY_PORTS = 1
MAX_BIRTHDAY_PORTS = 2048

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
        "seal_key_unknown": 503,
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
#: No unit holds the key a sealed request was sealed to: its host's agent started
#: again since the rider's last sync, with a new key.
SEAL_KEY_UNKNOWN = api_error("seal_key_unknown")
#: A request the hub refuses as malformed or outside its bounds; a rider seals
#: none such, refusing it itself as the hub would (:func:`mcgyvr.runner.sealed_for`).
INVALID_REQUEST = api_error("invalid_request")
#: The pool the request is served from has no slot for it now: a full pool,
#: not a broken unit.
POOL_BUSY = api_error("pool_busy")
#: The hub refused a ride because its host is outside the scope the request
#: named (:data:`SCOPE_HEADER`): asked again under the same scope, the same
#: host is refused again.
OUT_OF_SCOPE = api_error("out_of_scope")
#: The answers that say a relief rung cannot take a request now, sorted: the
#: hub names no host running the model (404 ``model_not_found``), the host's
#: machine is away (503 ``hitchhike_host_away``), the hub has not yet matched
#: this host to work (503 ``hitchhike_not_served_yet``), the host's unit
#: serves as many rides as it may (503 ``pool_busy``), and the host's unit no
#: longer holds the key a sealed request was sealed to (503
#: ``seal_key_unknown``: its agent started again with a new key, which the next
#: sync brings). One of them is a full rung, passed over at no cost.
RUNG_BUSY: tuple[tuple[int, str], ...] = tuple(
    sorted(
        api_error(code)
        for code in (
            "model_not_found",
            "hitchhike_host_away",
            "hitchhike_not_served_yet",
            "pool_busy",
            "seal_key_unknown",
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

# The bounds a chat request is held to before a unit is asked it: the hub holds a
# request in clear to them, and a host's agent holds a sealed one it has opened,
# which the hub cannot read (:func:`mcgyvr.seal.unit_body`).

#: Most messages in one request (and at least one).
CHAT_MAX_MESSAGES = 1024
#: Most tools offered in one request, and most tool calls in one message.
CHAT_MAX_TOOLS = 128
#: Most stop strings in one request (``stop`` is one string or a list of them).
CHAT_MAX_STOP = 8
#: Most alternatives a token's ``top_logprobs`` asks for.
CHAT_MAX_TOP_LOGPROBS = 20
#: Longest a message's ``name`` and its ``tool_call_id`` may be.
CHAT_MAX_NAME = 64
CHAT_MAX_TOOL_CALL_ID = 128
#: The roles a message may have.
MESSAGE_ROLES: tuple[str, ...] = ("system", "developer", "user", "assistant", "tool")
#: The fields of a message passed on; any other is dropped. ``role`` and ``content``
#: are required (``content`` may be null), ``content`` is text or a list of parts.
MESSAGE_FIELDS: tuple[str, ...] = (
    "role",
    "content",
    "name",
    "tool_calls",
    "tool_call_id",
)
#: The sampling fields held to a range, each with its lowest and highest value and
#: whether it is a whole number (an ``int``) rather than any number.
CHAT_RANGES: Mapping[str, tuple[float, float, bool]] = MappingProxyType(
    {
        "temperature": (0, 2, False),
        "top_p": (0, 1, False),
        "top_k": (0, 1000, True),
        "min_p": (0, 1, False),
        "presence_penalty": (-1e6, 1e6, False),
        "frequency_penalty": (-1e6, 1e6, False),
        "repeat_penalty": (-1e6, 1e6, False),
    }
)

#: The request header naming whose rigs may serve one request; without it the
#: member's own setting applies.
SCOPE_HEADER = "x-mcgyvr-scope"
#: The values :data:`SCOPE_HEADER` takes: the member's own rigs, their crews'
#: too, or anyone's.
SCOPE_OWN = "own"
SCOPE_CREW = "crew"
SCOPE_ANYONE = "anyone"
#: Narrowest first: each scope's rigs are also the next one's.
SCOPE_VALUES: tuple[str, ...] = (SCOPE_OWN, SCOPE_CREW, SCOPE_ANYONE)


def narrowest_scope(*scopes: str) -> str:
    """The narrowest of ``scopes`` (by :data:`SCOPE_VALUES`' order): the one
    whose rigs every other one also allows. Raises ValueError for a value
    that is not one of :data:`SCOPE_VALUES`, and for none at all."""
    return min(scopes, key=SCOPE_VALUES.index)


#: The hub's OpenAI-compatible root on its own address: a unit the hub serves
#: is asked there.
API_ROOT = "/v1"
#: Where the hub lists, under :data:`API_ROOT`, the models the request's scope
#: (:data:`SCOPE_HEADER`) may use now.
MODELS_PATH = f"{API_ROOT}/models"
#: The field of each listed model holding the request slots of every ready
#: unit of it, one whole number per unit.
MODEL_SLOTS = "slots"

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

#: Where the hub serves a request from. Three pools are named by their audience
#: (:data:`SCOPE_VALUES`): a member's own rigs, lent to nobody (``own``), a
#: crew's pool (``crew``) and the general pool, anyone's (``anyone``); beside
#: them a hitchhike ride and a ladder a host shares. A rig's pool is
#: :func:`rig_pool` of its audience and its mode (:data:`MODES`).
POOL_OWN = SCOPE_OWN
POOL_ANYONE = SCOPE_ANYONE
POOL_CREW = SCOPE_CREW
POOL_HITCHHIKE = "hitchhike"
POOL_SHARED_LADDER = "shared_ladder"
POOLS: tuple[str, ...] = (
    POOL_OWN,
    POOL_ANYONE,
    POOL_CREW,
    POOL_HITCHHIKE,
    POOL_SHARED_LADDER,
)
#: Each pool in words, as screens and messages name it: the general pool is
#: anyone's, so it is shown with its audience.
POOL_NAMES: Mapping[str, str] = MappingProxyType(
    {
        POOL_OWN: "own rigs",
        POOL_ANYONE: "general pool (anyone)",
        POOL_CREW: "crew pool",
        POOL_HITCHHIKE: "hitchhike",
        POOL_SHARED_LADDER: "shared ladder",
    }
)
#: The use cases each pool serves. A member's own rigs serve every use case;
#: the general pool serves models raw only; a crew's pool and a ride serve
#: every use case; a shared ladder is there for ``mcgyvr-code`` alone.
POOL_USE_CASES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        POOL_OWN: USE_CASES,
        POOL_ANYONE: (CODE, CHAT, AGENT),
        POOL_CREW: USE_CASES,
        POOL_HITCHHIKE: USE_CASES,
        POOL_SHARED_LADDER: (MCGYVR_CODE,),
    }
)

#: How a rig takes part on the hub, beside its audience (who may use it, one of
#: :data:`SCOPE_VALUES`): ``lend`` puts its hardware in its audience's pool,
#: where the hub plans what runs; ``hitchhike`` runs its owner's own units and
#: lets riders the hub matches use their spare slots. Under the ``own``
#: audience a rig lends to nobody, whatever its mode.
MODE_LEND = "lend"
MODE_HITCHHIKE = "hitchhike"
MODES: tuple[str, ...] = (MODE_LEND, MODE_HITCHHIKE)
#: The audiences each mode takes: a hitchhike rig is its owner's alone or
#: takes the riders the hub matches, never a crew's alone.
MODE_AUDIENCES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {MODE_LEND: SCOPE_VALUES, MODE_HITCHHIKE: (SCOPE_OWN, SCOPE_ANYONE)}
)


def rig_pool(audience: str, mode: str) -> str:
    """The pool a rig of ``audience`` (:data:`SCOPE_VALUES`) and ``mode``
    (:data:`MODES`) is in: :data:`POOL_OWN` under ``own``, whatever the mode;
    :data:`POOL_HITCHHIKE` for a hitchhike rig; else its audience's pool.

    Raises ValueError for a pair :data:`MODE_AUDIENCES` does not take.
    """
    if audience not in MODE_AUDIENCES.get(mode, ()):
        raise ValueError(
            f"a rig of mode {mode!r} takes audience "
            f"{' or '.join(MODE_AUDIENCES.get(mode, ()))}, not {audience!r}"
            if mode in MODES
            else f"{mode!r} is not a mode: {', '.join(MODES)}"
        )
    if audience == SCOPE_OWN:
        return POOL_OWN
    return POOL_HITCHHIKE if mode == MODE_HITCHHIKE else audience


#: The hub's sharing modes before audience and mode were two fields, each with
#: the audience and mode that replaced it. There is no alias: the hub refuses
#: an old one with the new spelling.
RETIRED_SHARING_MODES: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "solo": (SCOPE_OWN, MODE_LEND),
        "crew": (SCOPE_CREW, MODE_LEND),
        "pool": (SCOPE_ANYONE, MODE_LEND),
        "hitchhike": (SCOPE_ANYONE, MODE_HITCHHIKE),
    }
)
#: Words once used for an audience, each with the audience that replaced it:
#: the hub's old ``solo`` and ``pool`` (as :data:`RETIRED_SHARING_MODES` maps
#: them, less their mode) and the general pool's old name, ``general``. There is no alias: a value naming one is
#: refused with :func:`retired_audience`'s sentence.
RETIRED_AUDIENCES: Mapping[str, str] = MappingProxyType(
    {"solo": SCOPE_OWN, "pool": SCOPE_ANYONE, "general": SCOPE_ANYONE}
)


def retired_audience(value: str) -> str | None:
    """Why ``value`` is refused when it is an old word for an audience
    (:data:`RETIRED_AUDIENCES`), naming the one to write; None otherwise."""
    new = RETIRED_AUDIENCES.get(value)
    if new is None:
        return None
    return (
        f"`{value}` is no longer an audience: write `{new}` "
        f"(one of {', '.join(SCOPE_VALUES)})"
    )


def pool_serves(pool: str, use_case: str) -> bool:
    """Whether ``pool`` (one of :data:`POOLS`) serves ``use_case``.

    Raises KeyError for a pool that is not one of them.
    """
    return use_case in POOL_USE_CASES[pool]


#: The pool a request under each scope is served from when its model names no
#: ride: the pool of the same name (a member's own rigs, their crews' pool, and
#: the general pool, anyone's).
SCOPE_POOLS: Mapping[str, str] = MappingProxyType(
    {SCOPE_OWN: POOL_OWN, SCOPE_CREW: POOL_CREW, SCOPE_ANYONE: POOL_ANYONE}
)


def serving_pool(scope: str, model: str) -> str:
    """The pool a request for ``model`` under ``scope`` is served from.

    A relief rung's model (:data:`RUNG_PREFIX` and an offer) is a ride, served
    from :data:`POOL_HITCHHIKE` whatever the scope; any other model is served
    from the scope's pool (:data:`SCOPE_POOLS`). Raises KeyError for a scope
    that is not one of :data:`SCOPE_VALUES`.
    """
    pool = SCOPE_POOLS[scope]
    return POOL_HITCHHIKE if rung_offer(model) is not None else pool


# --- sealed rides ---------------------------------------------------------------
#
# A ride may be sealed end to end, rider to host: the rider seals its chat request
# to the key the host's unit advertises, the hub carries ciphertext and the host's
# agent opens it, posts it to the unit and seals the answer back. The cipher is the
# product's (:mod:`mcgyvr.seal`); the shapes below are what the hub holds a sealed
# request and a sealed answer to without opening either.

#: The field a sealed request carries its envelope in, at the top level of an
#: OpenAI chat completion request; and the field of a unit's advert, and of a relief
#: rung the hub lists, carrying the key a request to it is sealed to.
SEALED_FIELD = "sealed"
SEAL_KEY_FIELD = "seal"
#: The one envelope version, carried as ``v``: X25519 key agreement, HKDF-SHA256,
#: ChaCha20-Poly1305 (:data:`SEAL_SUITE`). Another suite is another version.
SEAL_VERSION = 1
SEAL_SUITE = "x25519-hkdf-sha256-chacha20poly1305"
#: A seal key's id: the first 16 bytes of the SHA-256 of its public key, in hex.
SEAL_KEY_ID = re.compile(r"[0-9a-f]{32}")
#: An X25519 public key: standard base64 of its 32 bytes.
SEAL_PUBLIC_KEY = re.compile(r"[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=")
#: A nonce: standard base64 of 12 bytes.
SEAL_NONCE = re.compile(r"[A-Za-z0-9+/]{16}")
#: A signature over a seal key by the rig's own identity key, standard base64 of
#: 64 bytes (Ed25519). Optional and not yet checked: the slot for rig identity.
SEAL_SIGNATURE = re.compile(r"[A-Za-z0-9+/]{85}[AQgw]==")
#: Ciphertext: standard base64, padded, of at least the 16-byte tag.
SEAL_CIPHERTEXT = re.compile(
    r"(?:[A-Za-z0-9+/]{4})+(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"
)
#: The longest ciphertext text a sealed request carries: the base64 of a relayed
#: request at its largest (:data:`RELAY_MAX_REQUEST_BYTES`).
SEAL_MAX_CIPHERTEXT = 4 * -(-RELAY_MAX_REQUEST_BYTES // 3)
#: The fields a sealed request may carry in clear beside its envelope, all the hub
#: needs to route and meter it: the model asked for, whether it streams and its
#: stream options. A sealed request carrying any other field is refused, so a client
#: that sealed a request and left its messages in clear is told rather than relayed.
SEALED_CLEAR_FIELDS: frozenset[str] = frozenset(
    {"model", "stream", "stream_options", SEALED_FIELD}
)
#: The fields of an answer's event (or of a whole answer) a host's agent leaves in
#: clear beside the sealed event: the name the answer goes out under, which the hub
#: rewrites as for any answer, and the token counts the hub charges by.
SEALED_ANSWER_CLEAR_FIELDS: tuple[str, ...] = ("model", "usage", "timings")
#: The fields of a seal key (an advert's, a rung's ``seal``): its id, its public
#: half and the optional signature over it (:data:`SEAL_SIGNATURE`).
SEAL_KEY_FIELDS: tuple[str, ...] = ("kid", "pub", "sig")
#: The fields of a sealed request's envelope, every one required: its version,
#: the id of the key it is sealed to, the rider's ephemeral public key, the nonce
#: and the ciphertext.
SEAL_ENVELOPE_FIELDS: tuple[str, ...] = ("v", "to", "epk", "nonce", "ct")
#: The fields of a sealed answer event's (or a whole answer's) envelope.
SEALED_ANSWER_ENVELOPE_FIELDS: tuple[str, ...] = ("nonce", "ct")
#: The fields of the body the hub relays to a host's agent for a sealed ride: the
#: clear fields (the unit's own model in place of the one asked for) and the hub's
#: cap on ``max_tokens``, which the agent holds the opened request to.
SEALED_FORWARDED_FIELDS: frozenset[str] = SEALED_CLEAR_FIELDS | {"max_tokens"}

#: The agent channel's schema: every frame between the hub and a rig's agent.
PROTOCOL_SCHEMA = "protocol.schema.json"
#: The rider REST API's schema, beside the agent channel, with the ``/v1``
#: error table.
RIDER_SCHEMA = "rider.schema.json"
#: The version each schema is published at (its ``$id`` ends ``/v<n>``): the
#: protocol's is :data:`PROTOCOL_VERSION`.
RIDER_SCHEMA_VERSION = 1
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
BACKEND_CUDA_NOTC = "cuda_notc"
BACKEND_METAL = "metal"
BACKEND_VULKAN = "vulkan"
BACKEND_ROCM = "rocm"
BACKEND_OPENVINO = "openvino"
BACKEND_SYCL = "sycl"
BACKEND_CPU = "cpu"
RESOURCE_BACKENDS: tuple[str, ...] = (
    BACKEND_CUDA,
    BACKEND_CUDA_NOTC,
    BACKEND_METAL,
    BACKEND_VULKAN,
    BACKEND_ROCM,
    BACKEND_OPENVINO,
    BACKEND_SYCL,
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
_MB_PER_GIB = 1024
#: How much of each kind one standby unit is, which a hub pays standby by:
#: one card, whether its memory is its own or the host's, so a unified device
#: is a card and never also memory; host memory per 16384 MiB (16 GiB) and
#: cores per 8. Cards count in cards, ``ram`` in MiB and ``cpu`` in cores.
STANDBY_UNIT_SIZE: Mapping[str, int] = MappingProxyType(
    {
        RESOURCE_GPU: 1,
        RESOURCE_UNIFIED: 1,
        RESOURCE_RAM: 16 * _MB_PER_GIB,
        RESOURCE_CPU: 8,
    }
)
#: The unit standby is counted in for each kind, by name, made from its size
#: (:data:`STANDBY_UNIT_SIZE`).
STANDBY_UNITS: Mapping[str, str] = MappingProxyType(
    {
        RESOURCE_GPU: "card",
        RESOURCE_UNIFIED: "card",
        RESOURCE_RAM: f"{STANDBY_UNIT_SIZE[RESOURCE_RAM] // _MB_PER_GIB}GiB",
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
    :data:`CARD_KINDS` among them), but for how many of a kind it reads: how
    many of each a rig has is its advert's to say (:data:`ONE_PER_RIG`).
    Whether each names an advertised resource, and its ``free_mb`` that
    resource's ``total_mb`` at most, is the hub's to hold against the advert
    it keeps, which reads nothing of a ``(kind, index)`` the advert did not
    name."""
    _fit(readings, ())


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
    lent whole, each once (None for every card the rig has, empty for none;
    always written, null included, so a missing key is no third meaning),
    ``ram_mb`` the host memory lent, in MiB, and ``cpu_cores`` the host cores
    lent.
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


# --- a rig's identity key ----------------------------------------------------------

#: The ``hello`` field carrying the rig's long-lived Ed25519 identity public key,
#: and the ``tunnel_up`` peer field the hub forwards it in. Optional: an agent
#: that predates it sends none, and a hub that predates it ignores it.
IDENTITY_KEY_FIELD = "identity_key"
#: The ``session_prepared`` field carrying the identity key's signature over
#: :func:`session_key_message`, and the ``tunnel_up`` peer field the hub
#: forwards it in beside the peer's tunnel key.
SESSION_KEY_SIG_FIELD = "public_key_sig"
#: An identity key: the 32 raw bytes of an Ed25519 public key in standard
#: base64 (44 characters, the last before the ``=`` holding 4 zero bits), the
#: shape WireGuard writes its own 32-byte keys in.
IDENTITY_KEY = re.compile(r"[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=")
#: How many characters an :data:`IDENTITY_KEY` is.
IDENTITY_KEY_CHARS = 44
#: A signature: the 64 raw bytes of an Ed25519 signature in standard base64
#: (88 characters, the last before the ``==`` holding 4 zero bits).
IDENTITY_SIG = re.compile(r"[A-Za-z0-9+/]{85}[AQgw]==")
#: What every signed tunnel key starts with, so a signature made for it is
#: never a signature over anything else the key might one day sign.
SESSION_KEY_CONTEXT = b"mcgyvr session tunnel key v1\x00"
#: How many base32 characters of the key's sha256 a fingerprint shows (80
#: bits), in groups of :data:`FINGERPRINT_GROUP`.
FINGERPRINT_CHARS = 16
FINGERPRINT_GROUP = 4


def session_key_message(session_id: str, public_key: str) -> bytes:
    """The bytes a rig's identity key signs for one session: the context, the
    session id and the WireGuard public key the rig answers that session with,
    each ended by a NUL. The session id binds the signature to the one session,
    so a hub cannot hand an old session's key to a new one."""
    for field, value in (("session_id", session_id), ("public_key", public_key)):
        _need(isinstance(value, str) and "\x00" not in value, field, "not plain text")
    return SESSION_KEY_CONTEXT + f"{session_id}\x00{public_key}\x00".encode()


def identity_key_bytes(identity_key: str) -> bytes:
    """The 32 raw bytes of an identity key; ValueError unless it is
    :data:`IDENTITY_KEY` in shape."""
    _need(
        isinstance(identity_key, str) and bool(IDENTITY_KEY.fullmatch(identity_key)),
        IDENTITY_KEY_FIELD,
        "not a base64 Ed25519 public key",
    )
    try:
        raw = base64.b64decode(identity_key, validate=True)
    except binascii.Error as exc:  # the pattern admits none; kept for the type
        raise ValueError(f"{IDENTITY_KEY_FIELD}: not base64") from exc
    return raw


def identity_fingerprint(identity_key: str) -> str:
    """The short form of an identity key people compare out of band: the first
    :data:`FINGERPRINT_CHARS` characters of the base32 of its sha256, in
    groups of :data:`FINGERPRINT_GROUP` joined by ``-``, e.g.
    ``ABCD-EFGH-IJKL-MNOP``. ValueError unless the key is in shape."""
    digest = hashlib.sha256(identity_key_bytes(identity_key)).digest()
    text = base64.b32encode(digest).decode()[:FINGERPRINT_CHARS]
    return "-".join(
        text[at : at + FINGERPRINT_GROUP]
        for at in range(0, FINGERPRINT_CHARS, FINGERPRINT_GROUP)
    )


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
_MS_PER_S = 1000

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


def fitted_on(kind: str, backend: str) -> bool:
    """Whether a resource of ``kind`` computing with ``backend`` is of the
    vendor the decode shares were fitted on (:data:`FITTED_ON`): a
    ``unified`` device on ``metal``, an Apple chip. The wire carries a
    resource's kind and backend, never its vendor; the product lends an Apple
    chip as a unified Metal device and an NVIDIA card as a gpu, so a hub
    passes ``vendor=FITTED_ON`` when this holds and another vendor's name
    when it does not."""
    return kind == RESOURCE_UNIFIED and backend == BACKEND_METAL


def decode_efficiency(
    bandwidth_gbps: float, quant: str, *, vendor: str
) -> float | None:
    """The decode efficiency for this bandwidth, quantisation and vendor, None
    when the quantisation has no class. The high-bandwidth ceiling holds for
    the vendor the shares were fitted on (:data:`FITTED_ON`) alone; the wire
    names no vendor, so a hub tells it by :func:`fitted_on`."""
    klass = quant_class(quant)
    if klass is None:
        return None
    eff = DECODE_EFFICIENCY[klass]
    if vendor == FITTED_ON and bandwidth_gbps >= HIGH_BANDWIDTH_GBPS:
        eff = min(eff, HIGH_BANDWIDTH_EFFICIENCY[klass])
    return eff


def decode_ms_per_gib(
    bandwidth_gbps: float, quant: str, *, vendor: str
) -> float | None:
    """Milliseconds a token takes per GiB of weights it reads, on a device of
    ``bandwidth_gbps`` (decimal GB/s) at the share of it
    :func:`decode_efficiency` states; None when the quantisation has no class
    or the bandwidth is not over 0. Each token reads every weight once, so a
    model of ``n`` GiB decodes a token in ``n`` times this."""
    eff = decode_efficiency(bandwidth_gbps, quant, vendor=vendor)
    if eff is None or not bandwidth_gbps > 0:
        return None
    return _MS_PER_S * BYTES_PER_GIB / (eff * bandwidth_gbps * BYTES_PER_DECIMAL_GB)


#: The ``port_map_report`` ``error`` (an open set of tags) of a forward its
#: owner has not allowed on the rig: the hub's ask is refused there, and no
#: rule by hand is the answer to it.
PORT_MAP_NOT_ALLOWED = "not_allowed"
#: The ``port_map_report`` ``error`` of a router that grants only permanent
#: leases, which the rig refuses unless its owner allowed a permanent one: a
#: rule added by hand on the router is the way left.
PORT_MAP_PERMANENT_ONLY = "permanent_only"
