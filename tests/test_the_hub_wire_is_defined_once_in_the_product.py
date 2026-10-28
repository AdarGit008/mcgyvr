"""The hub wire is defined once, in the product, and the schemas hold it.

:mod:`mcgyvr.hubwire` holds every value the hub and the product both keep for
the wire the hub serves a rider: rung positions, the model-name pattern and a
relief rung's ``hitchhike@<offer>``, the ladder and unit-advert limits with the
ride-cap rule, the relay limits, the ``/v1`` error table and the pairs read off
it, the forwarded request fields, the scope header, and the hub's JSON Schemas
as package resources. The hub imports these names; the product's copies are
imports of them too.

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


def test_every_pair_the_product_reads_is_a_published_pair(
    rider: dict[str, Any],
) -> None:
    """The busy answers a sync writes into ``relief.yaml``, and the two the
    runner names itself: each is a code the hub publishes, with its status."""
    published = rider["x-openai-errors"]
    read = {*hubwire.RUNG_BUSY, hubwire.MODEL_UNPLACED, hubwire.MODEL_NOT_FOUND}
    assert [pair for pair in sorted(read) if published.get(pair[1]) != pair[0]] == []
    with pytest.raises(KeyError):
        hubwire.api_error("relay_warming_up")


def test_a_relief_rung_is_full_on_four_answers_a_full_ride_among_them() -> None:
    assert hubwire.RUNG_BUSY == (
        (404, "model_not_found"),
        (503, "hitchhike_host_away"),
        (503, "hitchhike_not_served_yet"),
        (503, "pool_busy"),
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


def test_a_relief_rungs_model_is_the_prefix_and_its_offer() -> None:
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
    written = yaml.safe_load(rungs.render(read, "HUB_KEY"))["relief"]
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


def _posted(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
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
    from mcgyvr.local_pool import source_map

    pool = source_map(parse(_SETUP))
    posted = _posted(monkeypatch, runner)
    tool = {"type": "function", "function": {"name": "f", "parameters": {}}}
    ask = runner.Request(
        prompt="hello",
        system="be brief",
        max_output_tokens=16,
        temperature=0.7,
        response_schema={"type": "object"},
        tools=(tool,),
    )
    # The reply is not the point: what was sent is.
    with contextlib.suppress(runner.RunnerError):
        runner.runner_for(pool.bind("local")).generate("coder-7b", ask)

    (payload,) = posted
    assert {"response_format", "tools", "max_tokens", "temperature"} <= set(payload)
    assert set(payload) - hubwire.FORWARDED_FIELDS == set()


def test_every_field_jev_sends_is_one_the_hub_forwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import decision
    from mcgyvr.config import parse
    from mcgyvr.decision import Noul
    from mcgyvr.local_pool import source_map

    pool = source_map(parse(_SETUP))
    posted = _posted(monkeypatch, decision)
    decision.classify(pool.bind("local"), "coder-7b", {"x": 1}, {"q": Noul("Q?")})

    (payload,) = posted
    assert {"logprobs", "top_logprobs", "chat_template_kwargs"} <= set(payload)
    assert set(payload) - hubwire.FORWARDED_FIELDS == set()
    assert set(payload["chat_template_kwargs"]) <= hubwire.CHAT_TEMPLATE_KEYS


def test_the_scope_header_is_one_header_and_its_values_are_three() -> None:
    assert hubwire.SCOPE_HEADER.lower() == hubwire.SCOPE_HEADER
    assert hubwire.SCOPE_HEADER.startswith("x-mcgyvr-")
    assert len(set(hubwire.SCOPE_VALUES)) == len(hubwire.SCOPE_VALUES) == 3


# --- which pool serves which use case -------------------------------------------


def test_the_setups_use_cases_are_the_wires() -> None:
    from mcgyvr import config

    if "coding" in config.USE_CASES:
        pytest.xfail(
            "config names `coding` until the four use cases land; then "
            "config imports USE_CASES from mcgyvr.hubwire"
        )
    assert config.USE_CASES is hubwire.USE_CASES


def test_each_use_case_is_recommended_a_category_a_raw_use_case_names() -> None:
    assert tuple(hubwire.USE_CASE_CATEGORY) == hubwire.USE_CASES
    assert hubwire.USE_CASE_CATEGORY[hubwire.MCGYVR_CODE] == hubwire.CODE
    raw = hubwire.POOL_USE_CASES[hubwire.POOL_GENERAL]
    assert set(hubwire.USE_CASE_CATEGORY.values()) == set(raw)


def test_every_pool_serves_only_use_cases_and_each_is_served_somewhere() -> None:
    assert tuple(hubwire.POOL_USE_CASES) == hubwire.POOLS
    served = {u for cases in hubwire.POOL_USE_CASES.values() for u in cases}
    assert served == set(hubwire.USE_CASES)


@pytest.mark.parametrize(
    ("pool", "served"),
    [
        (hubwire.POOL_GENERAL, {"code", "chat", "agent"}),
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
    with pytest.raises(KeyError):
        hubwire.pool_serves("anyone", hubwire.CHAT)


def test_the_use_case_header_sits_beside_the_scope_header() -> None:
    assert hubwire.USE_CASE_HEADER.islower()
    assert hubwire.USE_CASE_HEADER != hubwire.SCOPE_HEADER
    assert hubwire.USE_CASE_HEADER.startswith("x-mcgyvr-")


#: Text only the wire module may hold: each value it defines, as a literal.
_DEFINED_ONCE = (
    hubwire.MODEL_NAME.pattern,
    hubwire.LADDER_MODEL.pattern,
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
