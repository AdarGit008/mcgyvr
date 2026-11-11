"""The hub wire is defined once, in the product, and the schemas hold it.

:mod:`mcgyvr.hubwire` holds every value the hub and the product both keep for
the hub wire: rung positions, the model-name pattern and a hitchhike rung's
``hitchhike@<offer>``, the ladder and unit-advert limits with the ride-cap
rule, the relay limits, the ``/v1`` error table and the pairs read off it, the
forwarded request fields, the scope header, the agent channel's versions,
limits, shapes and close and error codes, and the hub's JSON Schemas as
package resources. The hub imports these names as it drops its copies; the
rig's ``protocol`` and ``sessionwire`` name them as the same objects (held
here), and the one module that runs without the package, ``rig/udpwire.py``,
keeps the UDP version held to the wire's.

Held here: each value is the one the shipped schema says (every limit test
that held a copy to the schema moved here), ``hitchhike@<offer>`` formats and
parses, a rung listing in the schema's shape reads back through the product's
reader and writes the busy answers, and what the runner and Jev send is within
the fields the hub forwards. A hub checkout named by ``MCGYVR_HUB_REPO`` (or a
file by its own variable) is compared with the shipped schema byte for byte:
``tests/test_the_rig_agent_speaks_the_hubs_published_schema.py``.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
import yaml

from mcgyvr import hubwire
from tests import rig_schema
from tests.rigsyncs import FIRST, SECOND, rung


@pytest.fixture(scope="module")
def protocol() -> dict[str, Any]:
    return rig_schema.load(rig_schema.PROTOCOL)


@pytest.fixture(scope="module")
def rider() -> dict[str, Any]:
    return rig_schema.load(rig_schema.RIDER)


def _props(schema: dict[str, Any], name: str) -> dict[str, Any]:
    node: dict[str, Any] = schema["$defs"][name]["properties"]
    return node


def _branch(node: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in node:
        return next(b for b in node["anyOf"] if b.get("type") != "null")
    return node


# --- each value is the schema's ------------------------------------------------


def test_the_rung_positions_are_the_schemas(rider: dict[str, Any]) -> None:
    assert tuple(rider["$defs"]["RungPosition"]["enum"]) == hubwire.RUNG_POSITIONS


def test_every_model_name_the_protocol_takes_is_the_one_pattern(
    protocol: dict[str, Any],
) -> None:
    pattern = f"^{hubwire.MODEL_NAME.pattern}$"
    assert _props(protocol, "ModelInfo")["name"]["pattern"] == pattern
    assert _props(protocol, "AdvertisedUnit")["model"]["pattern"] == pattern


def test_the_ladder_limits_are_the_schemas(rider: dict[str, Any]) -> None:
    rungs = _props(rider, "LadderIn")["rungs"]
    assert (rungs["minItems"], rungs["maxItems"]) == (1, hubwire.LADDER_MAX_RUNGS)
    step = _props(rider, "LadderRungIn")
    assert step["model"]["pattern"] == f"^{hubwire.LADDER_MODEL.pattern}$"
    assert tuple(step["family"]["enum"]) == hubwire.LADDER_FAMILIES
    size = _branch(step["size_bytes"])
    assert (size["minimum"], size["maximum"]) == (1, hubwire.LADDER_MAX_SIZE_BYTES)
    params = _branch(step["params_b"])
    assert (params["exclusiveMinimum"], params["maximum"]) == (
        0,
        hubwire.LADDER_MAX_PARAMS_B,
    )


def test_the_unit_advert_limits_are_the_schemas(protocol: dict[str, Any]) -> None:
    assert protocol["x-max-units"] == hubwire.MAX_UNITS
    assert protocol["x-unit-advert-interval-s"] == hubwire.UNIT_ADVERT_INTERVAL_S
    assert protocol["x-unit-advert-stale-s"] == hubwire.UNIT_ADVERT_STALE_S
    assert _props(protocol, "UnitAdvertBody")["units"]["maxItems"] == hubwire.MAX_UNITS
    unit = _props(protocol, "AdvertisedUnit")
    assert (unit["slots"]["minimum"], unit["slots"]["maximum"]) == (
        1,
        hubwire.MAX_SLOTS,
    )
    assert (unit["free_slots"]["minimum"], unit["free_slots"]["maximum"]) == (
        0,
        hubwire.MAX_SLOTS,
    )
    # The schema bounds a ride cap alone; the rule against the unit's own
    # slots is :func:`hubwire.rider_cap_fits`, which the widest unit meets.
    cap = unit["rider_cap"]
    assert (cap["minimum"], cap["maximum"]) == (1, hubwire.MAX_SLOTS - 1)
    assert hubwire.rider_cap_fits(cap["maximum"], hubwire.MAX_SLOTS)
    assert not hubwire.rider_cap_fits(cap["maximum"] + 1, hubwire.MAX_SLOTS)


def test_the_relay_limits_are_the_schemas(protocol: dict[str, Any]) -> None:
    assert protocol["x-relay-max-chunk-bytes"] == hubwire.RELAY_MAX_CHUNK_BYTES
    assert protocol["x-relay-max-request-bytes"] == hubwire.RELAY_MAX_REQUEST_BYTES
    assert protocol["x-relay-max-response-bytes"] == hubwire.RELAY_MAX_RESPONSE_BYTES
    assert protocol["x-relay-max-window"] == hubwire.RELAY_MAX_WINDOW
    assert protocol["x-relay-max-timeout-s"] == hubwire.RELAY_MAX_TIMEOUT_S
    for name in ("RelayRequestBody", "UnitRelayRequestBody"):
        request = _props(protocol, name)
        assert request["body_bytes"]["maximum"] == hubwire.RELAY_MAX_REQUEST_BYTES
        assert request["timeout_s"]["maximum"] == hubwire.RELAY_MAX_TIMEOUT_S
        assert request["max_response_bytes"]["maximum"] == (
            hubwire.RELAY_MAX_RESPONSE_BYTES
        )
        assert request["window"]["maximum"] == hubwire.RELAY_MAX_WINDOW
    assert _props(protocol, "RelayCreditBody")["chunks"]["maximum"] == (
        hubwire.RELAY_MAX_WINDOW
    )
    assert _props(protocol, "RelayDataBody")["seq"]["maximum"] == hubwire.RELAY_MAX_SEQ
    end = _props(protocol, "RelayEndBody")
    for count in ("tokens_in", "tokens_out"):
        assert _branch(end[count])["maximum"] == hubwire.RELAY_MAX_TOKENS


def test_the_error_table_is_the_one_the_rider_schema_publishes(
    rider: dict[str, Any],
) -> None:
    assert dict(hubwire.API_ERROR_STATUS) == rider["x-openai-errors"]


def test_a_split_its_rigs_rpc_protocols_cannot_run_is_refused_as_no_path_is() -> None:
    """Both wait on a rig changing (an agent upgrade, a path opening), so both
    are a 503 the client may try again."""
    assert hubwire.api_error("rpc_incompatible") == (503, "rpc_incompatible")
    assert hubwire.API_ERROR_STATUS["no_path"] == 503


def test_every_pair_the_product_reads_is_a_published_pair(
    rider: dict[str, Any],
) -> None:
    """The busy answers a sync writes into ``hitchhike.yaml``, and the three the
    runner names itself: each is a code the hub publishes, with its status."""
    published = rider["x-openai-errors"]
    read = {
        *hubwire.RUNG_BUSY,
        hubwire.MODEL_UNPLACED,
        hubwire.MODEL_NOT_FOUND,
        hubwire.OUT_OF_SCOPE,
    }
    assert [pair for pair in sorted(read) if published.get(pair[1]) != pair[0]] == []
    with pytest.raises(KeyError):
        hubwire.api_error("relay_warming_up")


def test_a_hitchhike_rung_is_full_on_five_answers_a_full_ride_and_a_stale_key() -> None:
    assert hubwire.RUNG_BUSY == (
        (404, "model_not_found"),
        (503, "hitchhike_host_away"),
        (503, "hitchhike_not_served_yet"),
        (503, "pool_busy"),
        (503, "seal_key_unknown"),
    )
    assert hubwire.MODEL_UNPLACED == (503, "model_unplaced")
    assert hubwire.MODEL_NOT_FOUND == (404, "model_not_found")


def test_the_package_ships_exactly_the_schemas_it_names() -> None:
    from importlib import resources

    shipped = resources.files("mcgyvr") / "hubwire_schemas"
    assert sorted(p.name for p in shipped.iterdir()) == sorted(hubwire.SCHEMAS)
    for name in hubwire.SCHEMAS:
        assert hubwire.schema(name)["$schema"].endswith("2020-12/schema")
    with pytest.raises(ValueError, match="is not one of"):
        hubwire.schema_bytes("../pyproject.toml")


# --- hitchhike@<offer> ---------------------------------------------------------


def test_a_hitchhike_rungs_model_is_the_prefix_and_its_offer() -> None:
    model = hubwire.rung_model(FIRST)
    assert model == f"hitchhike@{FIRST}"
    assert hubwire.MODEL_NAME.fullmatch(model)
    assert hubwire.rung_offer(model) == FIRST


@pytest.mark.parametrize(
    "model",
    [
        "qwen2.5-coder-7b",
        "hitchhike@",
        f"hitchhike@{FIRST.upper()}",
        f"hitchhike@{FIRST}0",
        f"hitchhike-{FIRST}",
        f"Hitchhike@{FIRST}",
    ],
)
def test_a_model_naming_no_offer_parses_to_none(model: str) -> None:
    assert hubwire.rung_offer(model) is None


@pytest.mark.parametrize("offer", ["", "xyz", FIRST[:-1], FIRST + "\n"])
def test_a_rung_model_is_not_made_from_what_is_not_an_offer(offer: str) -> None:
    with pytest.raises(ValueError, match="is not an offer id"):
        hubwire.rung_model(offer)


@pytest.mark.parametrize(
    ("cap", "slots", "fits"),
    [(1, 2, True), (15, 16, True), (0, 2, False), (2, 2, False), (1, 1, False)],
)
def test_a_ride_cap_leaves_the_host_a_slot(cap: int, slots: int, fits: bool) -> None:
    assert hubwire.rider_cap_fits(cap, slots) is fits


# --- a listing round-trips -----------------------------------------------------


def test_a_listing_in_the_schemas_shape_reads_back_and_writes_the_busy_answers(
    rider: dict[str, Any],
) -> None:
    from mcgyvr.rig import rungs

    hub = "http://127.0.0.1:8080"
    offers = (FIRST, SECOND, "2" * 32)
    listing = {
        "ride": True,
        "privacy": "the host can read your prompts",
        "refresh_s": 60,
        "rungs": [
            rung(offer, f"{hub}/v1", position=position)
            for offer, position in zip(offers, hubwire.RUNG_POSITIONS, strict=True)
        ],
    }
    rig_schema.validate(listing, rider, "#/$defs/RungsOut")

    read = rungs.read(listing, hub)

    assert [(r.id, r.position) for r in read.rungs] == list(
        zip(offers, hubwire.RUNG_POSITIONS, strict=True)
    )
    assert [hubwire.rung_offer(r.model) for r in read.rungs] == list(offers)
    written = yaml.safe_load(rungs.render(read, "HUB_KEY"))["hitchhike"]
    for block in written.values():
        pairs = tuple((a["status"], a["code"]) for a in block["busy_answers"])
        assert pairs == hubwire.RUNG_BUSY


def test_a_listed_rung_naming_another_offer_is_refused() -> None:
    from mcgyvr.rig import rungs

    hub = "http://127.0.0.1:8080"
    entry = rung(FIRST, f"{hub}/v1")
    entry["model"] = hubwire.rung_model(SECOND)
    listing = {"ride": True, "privacy": "p", "refresh_s": 60, "rungs": [entry]}

    with pytest.raises(rungs.HubAnswerError, match="does not name this rung"):
        rungs.read(listing, hub)


# --- what the product sends is what the hub forwards ---------------------------

_SETUP = """\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
    width: 2
ladder: [local]
"""


def _posted(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    sent: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
        if sent is not None:
            sent.append(headers)
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "hi"},
                    "logprobs": {
                        "content": [
                            {"top_logprobs": [{"token": "Yes", "logprob": -0.1}]}
                        ]
                    },
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(module, "_post_json", post)
    return posted


def test_every_field_the_runner_sends_is_one_the_hub_forwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import runner
    from mcgyvr.config import parse
    from mcgyvr.ladder_map import unit_map

    pool = unit_map(parse(_SETUP))
    posted = _posted(monkeypatch, runner)
    ask = runner.Request(
        prompt="hello",
        system="be brief",
        max_output_tokens=16,
        temperature=0.7,
    )
    # The reply is not the point: what was sent is.
    with contextlib.suppress(runner.RunnerError):
        runner.runner_for(pool.bind("local")).generate("coder-7b", ask)

    (payload,) = posted
    assert {"max_tokens", "temperature"} <= set(payload)
    assert set(payload) - hubwire.FORWARDED_FIELDS == set()


def test_every_field_jev_sends_is_one_the_hub_forwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import decision
    from mcgyvr.config import parse
    from mcgyvr.decision import Noul
    from mcgyvr.ladder_map import unit_map

    pool = unit_map(parse(_SETUP))
    posted = _posted(monkeypatch, decision)
    decision.classify(pool.bind("local"), "coder-7b", {"x": 1}, {"q": Noul("Q?")})

    (payload,) = posted
    assert {"logprobs", "top_logprobs", "chat_template_kwargs"} <= set(payload)
    assert set(payload) - hubwire.FORWARDED_FIELDS == set()
    assert set(payload["chat_template_kwargs"]) <= hubwire.CHAT_TEMPLATE_KEYS


@pytest.mark.parametrize("use_case", [None, "code", "mcgyvr-code"])
def test_the_runner_and_jev_name_the_setups_use_case(
    monkeypatch: pytest.MonkeyPatch, use_case: str | None
) -> None:
    """Every chat request names the setup's use case, so a hub can refuse one
    its pool does not serve; unset, the setup's use case is ``mcgyvr-code``."""
    from mcgyvr import decision, runner
    from mcgyvr.config import parse
    from mcgyvr.decision import Noul
    from mcgyvr.ladder_map import unit_map

    setup = _SETUP if use_case is None else f"{_SETUP}use_case: {use_case}\n"
    pool = unit_map(parse(setup))
    sent: list[dict[str, str]] = []
    _posted(monkeypatch, runner, sent)
    _posted(monkeypatch, decision, sent)
    ask = runner.Request(prompt="hello", max_output_tokens=16)
    with contextlib.suppress(runner.RunnerError):
        runner.runner_for(pool.bind("local")).generate("coder-7b", ask)
    decision.classify(pool.bind("local"), "coder-7b", {"x": 1}, {"q": Noul("Q?")})

    named = use_case or hubwire.MCGYVR_CODE
    assert [h[hubwire.USE_CASE_HEADER] for h in sent] == [named, named]
    assert [h[hubwire.SCOPE_HEADER] for h in sent] == [hubwire.SCOPE_OWN] * 2


def test_the_scope_header_is_one_header_and_its_values_are_three() -> None:
    assert hubwire.SCOPE_HEADER.lower() == hubwire.SCOPE_HEADER
    assert hubwire.SCOPE_HEADER.startswith("x-mcgyvr-")
    assert len(set(hubwire.SCOPE_VALUES)) == len(hubwire.SCOPE_VALUES) == 3
    assert hubwire.SCOPE_VALUES == (
        hubwire.SCOPE_OWN,
        hubwire.SCOPE_CREW,
        hubwire.SCOPE_ANYONE,
    )


def test_each_scope_is_served_from_one_pool() -> None:
    assert tuple(hubwire.SCOPE_POOLS) == hubwire.SCOPE_VALUES
    assert dict(hubwire.SCOPE_POOLS) == {
        "own": hubwire.POOL_OWN,
        "crew": hubwire.POOL_CREW,
        "anyone": hubwire.POOL_ANYONE,
    }


@pytest.mark.parametrize("scope", ["own", "crew", "anyone"])
def test_a_rides_model_is_served_from_the_hitchhike_pool_whatever_its_scope(
    scope: str,
) -> None:
    ride = hubwire.rung_model(FIRST)

    assert hubwire.serving_pool(scope, ride) == hubwire.POOL_HITCHHIKE
    assert hubwire.serving_pool(scope, "coder-7b") == hubwire.SCOPE_POOLS[scope]
    with pytest.raises(KeyError):
        hubwire.serving_pool("everyone", "coder-7b")


# --- which pool serves which use case -------------------------------------------


def test_the_setups_use_cases_are_the_wires() -> None:
    from mcgyvr import config

    assert config.USE_CASES is hubwire.USE_CASES
    names = (config.MCGYVR_CODE, config.CODE, config.CHAT, config.AGENT)
    assert names == hubwire.USE_CASES


def test_recommend_places_each_use_case_by_the_wires_category() -> None:
    from mcgyvr import recommend
    from mcgyvr.knowledge import hub

    assert recommend.PROFILE_OF_USE_CASE is hubwire.USE_CASE_CATEGORY
    assert set(hubwire.USE_CASE_CATEGORY.values()) == set(hub.USE_CASES)


def test_each_use_case_is_recommended_a_category_a_raw_use_case_names() -> None:
    assert tuple(hubwire.USE_CASE_CATEGORY) == hubwire.USE_CASES
    assert hubwire.USE_CASE_CATEGORY[hubwire.MCGYVR_CODE] == hubwire.CODE
    raw = set(hubwire.USE_CASES) - {hubwire.MCGYVR_CODE}
    assert set(hubwire.USE_CASE_CATEGORY.values()) == raw


def test_every_pool_serves_only_use_cases_and_each_is_served_somewhere() -> None:
    assert tuple(hubwire.POOL_USE_CASES) == hubwire.POOLS
    served = {u for cases in hubwire.POOL_USE_CASES.values() for u in cases}
    assert served == set(hubwire.USE_CASES)


@pytest.mark.parametrize(
    ("pool", "served"),
    [
        (hubwire.POOL_OWN, {"mcgyvr-code", "code", "chat", "agent"}),
        (hubwire.POOL_ANYONE, {"mcgyvr-code", "code", "chat", "agent"}),
        (hubwire.POOL_CREW, {"mcgyvr-code", "code", "chat", "agent"}),
        (hubwire.POOL_HITCHHIKE, {"mcgyvr-code", "code", "chat", "agent"}),
        (hubwire.POOL_SHARED_LADDER, {"mcgyvr-code"}),
    ],
)
def test_a_pool_serves_its_use_cases_and_refuses_the_rest(
    pool: str, served: set[str]
) -> None:
    for use_case in hubwire.USE_CASES:
        assert hubwire.pool_serves(pool, use_case) is (use_case in served)
    with pytest.raises(KeyError):  # the general pool's old name is no pool
        hubwire.pool_serves("general", hubwire.CHAT)


@pytest.mark.parametrize("use_case", hubwire.USE_CASES)
@pytest.mark.parametrize("ride", [False, True])
@pytest.mark.parametrize("scope", hubwire.SCOPE_VALUES)
def test_every_pool_a_request_is_served_from_serves_every_use_case(
    scope: str, ride: bool, use_case: str
) -> None:
    """What the hub refuses with ``use_case_not_served``: the pool a request is
    served from (by its scope and model) not serving its use case. A member's
    own rigs, the general pool, a crew's pool and a ride each serve all four,
    so no use case is refused under any scope; the model a pool serves plays
    no part."""
    model = hubwire.rung_model(FIRST) if ride else "coder-7b"
    assert hubwire.pool_serves(hubwire.serving_pool(scope, model), use_case)


def test_a_use_case_no_pool_serves_is_refused_by_every_pool() -> None:
    """A header value that is not a use case (``coding``, the name replaced)
    is refused under any scope: no pool serves it."""
    assert all(not hubwire.pool_serves(p, "coding") for p in hubwire.POOLS)
    assert hubwire.scopes_serving("coding") == ()


@pytest.mark.parametrize("use_case", hubwire.USE_CASES)
def test_the_scopes_a_refusal_offers_are_those_whose_pool_serves_the_use_case(
    use_case: str,
) -> None:
    """One list, for the setup check's refusal and the hub's alike."""
    expected = tuple(
        s
        for s in hubwire.SCOPE_VALUES
        if hubwire.pool_serves(hubwire.SCOPE_POOLS[s], use_case)
    )
    assert hubwire.scopes_serving(use_case) == expected == hubwire.SCOPE_VALUES


def test_a_scope_whose_pool_stops_serving_a_use_case_is_not_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrow = {**hubwire.POOL_USE_CASES, hubwire.POOL_ANYONE: ("code", "chat", "agent")}
    monkeypatch.setattr(hubwire, "POOL_USE_CASES", narrow)

    assert hubwire.scopes_serving(hubwire.MCGYVR_CODE) == (
        hubwire.SCOPE_OWN,
        hubwire.SCOPE_CREW,
    )


def test_a_use_case_refused_is_a_403_beside_out_of_scope_and_not_a_full_rung() -> None:
    """Asked again under the same scope and model, it is refused again, as a
    host outside the scope is: not an answer a rung passes over as full."""
    assert hubwire.USE_CASE_NOT_SERVED == (403, "use_case_not_served")
    assert hubwire.OUT_OF_SCOPE[0] == hubwire.USE_CASE_NOT_SERVED[0]
    assert hubwire.USE_CASE_NOT_SERVED not in hubwire.RUNG_BUSY


def test_the_use_case_header_sits_beside_the_scope_header() -> None:
    assert hubwire.USE_CASE_HEADER.islower()
    assert hubwire.USE_CASE_HEADER != hubwire.SCOPE_HEADER
    assert hubwire.USE_CASE_HEADER.startswith("x-mcgyvr-")


# --- the agent channel -----------------------------------------------------------


def test_the_channels_versions_and_frame_limits_are_the_schemas(
    protocol: dict[str, Any], rider: dict[str, Any]
) -> None:
    assert protocol["x-protocol-version"] == hubwire.PROTOCOL_VERSION
    assert protocol["$id"].endswith(f"/v{hubwire.PROTOCOL_VERSION}.schema.json")
    assert rider["$id"].endswith(f"/v{hubwire.RIDER_SCHEMA_VERSION}.schema.json")
    assert protocol["x-udp"]["version"] == hubwire.UDP_VERSION
    assert protocol["x-max-message-bytes"] == hubwire.MAX_MESSAGE_BYTES
    assert protocol["x-max-frames-per-second"] == hubwire.MAX_FRAMES_PER_SECOND
    assert protocol["x-log-excerpt-max-chars"] == hubwire.LOG_EXCERPT_MAX_CHARS
    assert _props(protocol, "ErrorBody")["message"]["maxLength"] == (
        hubwire.MAX_ERROR_TEXT
    )
    beat = _branch(_props(protocol, "AckBody")["heartbeat_interval_s"])
    assert (beat["minimum"], beat["maximum"]) == hubwire.HEARTBEAT_INTERVAL_S
    envelope = _props(protocol, "Envelope")
    assert envelope["id"]["pattern"] == f"^{hubwire.MESSAGE_ID.pattern}$"
    assert envelope["type"]["pattern"] == f"^{hubwire.TAG.pattern}$"
    status = _props(protocol, "RelayResponseBody")["status"]
    assert (status["minimum"], status["maximum"]) == hubwire.RELAY_STATUS


def test_the_udp_wire_keeps_the_wires_version_and_ticket() -> None:
    """``rig/udpwire.py`` runs in the tunnel without the package, so it cannot
    import the version or the relay ticket's shape: its copies are held here."""
    from mcgyvr.rig import udpwire

    assert udpwire.VERSION == hubwire.UDP_VERSION
    assert udpwire.TICKET.pattern == hubwire.TICKET.pattern


def test_the_channels_close_and_error_codes_are_the_schemas(
    protocol: dict[str, Any],
) -> None:
    assert protocol["x-close-codes"] == {
        code.name.lower(): code.value for code in hubwire.CloseCode
    }
    codes = hubwire.AGENT_ERROR_CODES
    assert len(set(codes)) == len(codes)
    assert sorted(codes) == protocol["x-error-codes"]
    assert hubwire.SessionCode.BAD_SEAL in codes


#: The rig's names for the agent channel's values, each the wire's own object:
#: ``(module, its name, hubwire's name)``.
_RIG_NAMES = (
    *(
        ("protocol", name, name)
        for name in (
            "PROTOCOL_VERSION",
            "MAX_MESSAGE_BYTES",
            "MAX_FRAMES_PER_SECOND",
            "MAX_ERROR_TEXT",
            "HEARTBEAT_INTERVAL_S",
            "MAX_MODELS",
            "MAX_SESSIONS_REPORTED",
            "MAX_MODEL_BYTES",
            "MAX_LAYERS",
            "MAX_COUNT",
            "MAX_KV_BYTES_PER_TOKEN",
            "MESSAGE_ID",
            "TAG",
            "MACHINE_ID",
            "AGENT_VERSION",
            "CloseCode",
            "ErrorCode",
            "MODEL_NAME",
            "DIGEST",
            "SHORT_TAG",
            "RUNTIME",
            "ENDPOINT_HOST",
            "MAX_ENDPOINTS",
            "MAX_FEATURES",
        )
    ),
    ("protocol", "ROLES", "RIG_ROLES"),
    ("sessionwire", "ROLES", "RIG_ROLES"),
    ("sessionwire", "Role", "RigRole"),
    ("sessionwire", "STATES", "SESSION_STATES"),
    ("sessionwire", "SESSION_ID", "MESSAGE_ID"),
    ("sessionwire", "HOST", "ENDPOINT_HOST"),
    *(
        ("sessionwire", name, name)
        for name in (
            "MAX_ENDPOINTS",
            "MAX_PEERS",
            "MAX_ALLOWED_IPS",
            "MAX_DEVICES",
            "MAX_RTT_SAMPLES",
            "MAX_RTT_US",
            "MIN_CTX",
            "MAX_CTX",
            "MAX_TENSOR_SHARE",
            "MAX_GPU_LAYERS",
            "DEFAULT_GPU_LAYERS",
            "DEFAULT_SLOTS",
            "MAX_KEEPALIVE_S",
            "DEFAULT_KEEPALIVE_S",
            "MAX_PORT",
            "LOG_EXCERPT_MAX_CHARS",
            "MAX_CONTENT_TYPE",
            "MAX_PCT",
            "RELAY_STATUS",
            "RELAY_MAX_CHUNK_B64",
            "MAX_STUN_ENDPOINTS",
            "MIN_PROBE_TTL_S",
            "MAX_PROBE_TTL_S",
            "DEFAULT_PROBE_TTL_S",
            "MAX_PROBE_COUNT",
            "DEFAULT_PROBE_COUNT",
            "MIN_PROBE_INTERVAL_MS",
            "MAX_PROBE_INTERVAL_MS",
            "DEFAULT_PROBE_INTERVAL_MS",
            "MAX_PROBE_BULK_BYTES",
            "MIN_PROBE_DEADLINE_MS",
            "MAX_PROBE_DEADLINE_MS",
            "DEFAULT_PROBE_DEADLINE_MS",
            "MAX_ATTEMPT_S",
            "MAX_CONNECT_TIMEOUT_S",
            "MAX_RATE_KBPS",
            "PORT_MAP_PORTS",
            "MIN_PORT_MAP_LEASE_S",
            "MAX_PORT_MAP_LEASE_S",
            "DEFAULT_PORT_MAP_LEASE_S",
            "MIN_PORT_CHECK_TTL_S",
            "MAX_PORT_CHECK_TTL_S",
            "DEFAULT_PORT_CHECK_TTL_S",
            "PORT_MAP_STATES",
            "RELAY_OUTCOMES",
            "MODEL_NAME",
            "DIGEST",
            "WIREGUARD_KEY",
            "IPV4",
            "IPV4_CIDR",
            "CONTENT_TYPE",
            "BASE64",
            "TOKEN",
            "TICKET",
            "SessionCode",
        )
    ),
)


@pytest.mark.parametrize(("module", "name", "wire"), _RIG_NAMES)
def test_each_rig_name_for_a_channel_value_is_the_wires_own(
    module: str, name: str, wire: str
) -> None:
    import importlib

    rig = importlib.import_module(f"mcgyvr.rig.{module}")
    assert getattr(rig, name) is getattr(hubwire, wire)


#: Text only the wire module may hold: each value it defines, as a literal.
#: The relay ticket's shape is left out: ``rig/udpwire.py`` runs without the
#: package and keeps its own.
_DEFINED_ONCE = (
    hubwire.MODEL_NAME.pattern,
    hubwire.RESOURCE_NAME.pattern,
    hubwire.LADDER_MODEL.pattern,
    *(
        shape.pattern
        for shape in (
            hubwire.MESSAGE_ID,
            hubwire.TAG,
            hubwire.MACHINE_ID,
            hubwire.AGENT_VERSION,
            hubwire.DIGEST,
            hubwire.SHORT_TAG,
            hubwire.RUNTIME,
            hubwire.ENDPOINT_HOST,
            hubwire.WIREGUARD_KEY,
            hubwire.IPV4,
            hubwire.IPV4_CIDR,
            hubwire.CONTENT_TYPE,
            hubwire.BASE64,
            hubwire.TOKEN,
        )
    ),
    *(f"{quote}{hubwire.RUNG_PREFIX}" for quote in "\"'"),
    hubwire.SCOPE_HEADER,
    hubwire.USE_CASE_HEADER,
    *(
        f"{quote}{word}{quote}"
        for quote in "\"'"
        for word in (
            *hubwire.RUNG_POSITIONS,
            *(code for _, code in (*hubwire.RUNG_BUSY, hubwire.MODEL_UNPLACED)),
        )
    ),
)


def test_no_other_module_spells_a_wire_value() -> None:
    """The runner, the hub client, the session wire and config import these
    values; a module that spelled one again would be a copy that drifts.
    Of the ``/v1`` codes, the ones the product reads are held to it: others,
    such as ``timeout``, are words of the agent channel too."""
    from tests._paths import SRC

    found = sorted(
        (str(path.relative_to(SRC)), text)
        for path in SRC.rglob("*.py")
        if path.name != "hubwire.py"
        for text in _DEFINED_ONCE
        if text in path.read_text(encoding="utf-8")
    )
    assert found == []
