"""A hub head is sent its fields only when it names the feature, and sized by one rule.

A hub head heads a session from the hub's own host with no card: every layer on
workers, the output layer on a CPU rpc-server on its loopback, up to
``HUB_HEAD_MAX_SLOTS`` slots decoded in waves at a micro-batch sized to the
workers' uplink. The wire names it once (``mcgyvr.hubwire``): the features
``hub_head`` and ``probe_bulk_2m``, the ``head_start`` fields ``output_local``,
``waves`` and ``ubatch``, its slots, the ``tunnel_up`` peer field ``listen``,
the bigger probe bulk, and the rules both sides size it by
(:func:`hubwire.head_waves_fit`, :func:`hubwire.fit_beyond`,
:func:`hubwire.hub_head_ubatch`).

Nothing changes for a rig that does not name the feature: a body without the
new fields reads as before, and one with them reads exactly as without (the
fields are left unread, the rule every optional field keeps: the hub uses a
feature only with an agent that lists it). Each expected number of the rules
is worked out next to it from the rule it comes from.
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import inventory, probe, protocol
from mcgyvr.rig import sessionwire as w
from mcgyvr.serving import vramfit
from tests import rig_schema
from tests.test_a_rigs_hello_answers_what_each_models_cache_takes_on_the_hubs_grid import (  # noqa: E501
    DENSE,
    RECURRENT,
    SLIDING,
)

HUB_HEAD = (hubwire.FEATURE_HUB_HEAD,)
BULK_2M = (hubwire.FEATURE_PROBE_BULK_2M,)
MIB = hubwire.BYTES_PER_MIB
KEY = "A" * 42 + "Q="
TOKEN = "00112233445566778899aabbccddeeff"
#: One token's activations on a worker's uplink for a model of hidden size 2,560
#: carried as f32: 2,560 x 4 B.
TOKEN_BYTES = 10_240


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return rig_schema.load()


def _envelope(kind: str, body: dict[str, Any]) -> protocol.Envelope:
    return protocol.decode(json.dumps({"v": 1, "type": kind, "id": "c1", "body": body}))


def _head_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "session_id": "s1",
        "model": {"name": "m.gguf"},
        "ctx": 4096,
        "devices": [
            {"kind": "rpc", "host": "10.0.0.2", "port": 50052},
            {"kind": "rpc", "host": "10.0.0.3", "port": 50052},
        ],
        "tensor_split": [1, 1],
    }
    body.update(changes)
    return body


def _up_body(**peer: Any) -> dict[str, Any]:
    return {
        "session_id": "s1",
        "address": "198.51.100.2/24",
        "listen_port": 51820,
        "peers": [
            {
                "rig_id": "r1",
                "public_key": KEY,
                "allowed_ips": ["198.51.100.1/32"],
                **peer,
            }
        ],
    }


def _run_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "probe_id": "pr",
        "peers": [
            {
                "rig_id": "r1",
                "secret": TOKEN,
                "endpoints": [{"host": "192.0.2.20", "port": 1, "kind": "reflexive"}],
            }
        ],
    }
    body.update(changes)
    return body


def _refused(read: Any, field: str) -> None:
    with pytest.raises(protocol.ProtocolError) as refused:
        read()
    assert refused.value.code == "bad_message"
    assert refused.value.message.startswith(f"body.{field}:"), refused.value.message


HUB_FIELDS = {"output_local": True, "waves": 4, "ubatch": 29}


# --- nothing changes for a rig that does not name the feature ----------------------


def test_a_start_without_the_new_fields_reads_as_before_whatever_the_rig_names() -> (
    None
):
    plain = w.read_head_start(_envelope("head_start", _head_body(slots=16)))
    assert (plain.slots, plain.output_local, plain.waves, plain.ubatch) == (
        16,
        False,
        None,
        None,
    )
    named = w.read_head_start(
        _envelope("head_start", _head_body(slots=16)), features=HUB_HEAD
    )
    assert named == plain


def test_a_rig_without_the_feature_leaves_the_hub_head_fields_unread() -> None:
    plain = w.read_head_start(_envelope("head_start", _head_body(slots=8)))
    sent = w.read_head_start(_envelope("head_start", _head_body(slots=8, **HUB_FIELDS)))
    assert sent == plain
    # even ill-formed ones: an old rig never looked at them, nor does this one
    odd = _head_body(slots=8, output_local="yes", waves=0, ubatch=10_000)
    assert w.read_head_start(_envelope("head_start", odd)) == plain


def test_a_rig_without_the_feature_still_takes_at_most_max_slots() -> None:
    body = _head_body(slots=hubwire.MAX_SLOTS + 1)
    _refused(lambda: w.read_head_start(_envelope("head_start", body)), "slots")
    _refused(
        lambda: w.read_head_start(_envelope("head_start", body), features=BULK_2M),
        "slots",
    )


def test_a_peer_without_the_feature_reads_as_before_with_listen_or_without() -> None:
    plain = w.read_tunnel_up(_envelope("tunnel_up", _up_body()))
    assert plain.peers[0].listen is False
    assert w.read_tunnel_up(_envelope("tunnel_up", _up_body(listen=True))) == plain
    assert w.read_tunnel_up(_envelope("tunnel_up", _up_body(listen="x"))) == plain
    named = w.read_tunnel_up(_envelope("tunnel_up", _up_body()), features=HUB_HEAD)
    assert named == plain


def test_a_rig_without_the_bulk_feature_takes_the_old_bulk_and_no_more() -> None:
    top = hubwire.MAX_PROBE_BULK_BYTES
    run = w.read_probe_run(_envelope("probe_run", _run_body(bulk_bytes=top)))
    assert run.bulk_bytes == top
    _refused(
        lambda: w.read_probe_run(_envelope("probe_run", _run_body(bulk_bytes=top + 1))),
        "bulk_bytes",
    )
    _refused(
        lambda: w.read_probe_run(
            _envelope("probe_run", _run_body(bulk_bytes=top + 1)), features=HUB_HEAD
        ),
        "bulk_bytes",
    )


def test_every_old_bound_and_default_keeps_its_value() -> None:
    assert hubwire.MAX_SLOTS == 16
    assert hubwire.DEFAULT_SLOTS == 1
    assert hubwire.MAX_PROBE_BULK_BYTES == 256 * 1024
    assert hubwire.HEAD_UBATCH == 512
    assert hubwire.FIT_SLOTS == (1, 2, 4, 8, 16)
    assert hubwire.MAX_FEATURES == 16
    assert len(hubwire.FEATURES) <= hubwire.MAX_FEATURES
    # a field left out reads as before: the dataclasses' new fields default off
    head = dataclasses.fields(w.HeadStart)
    assert {f.name: f.default for f in head if f.name in HUB_FIELDS} == {
        "output_local": False,
        "waves": None,
        "ubatch": None,
    }
    assert next(f for f in dataclasses.fields(w.TunnelPeer) if f.name == "listen")
    assert w.TunnelPeer.__dataclass_fields__["listen"].default is False


# --- the new constants and names -----------------------------------------------------


def test_the_hub_heads_names_and_bounds() -> None:
    assert hubwire.FEATURE_HUB_HEAD == "hub_head"
    assert hubwire.FEATURE_PROBE_BULK_2M == "probe_bulk_2m"
    assert hubwire.HUB_HEAD_MAX_SLOTS == 64
    assert hubwire.HUB_PROBE_BULK_BYTES == 2 * 1024 * 1024
    assert hubwire.HEAD_OUTPUT_LOCAL_FIELD == "output_local"
    assert (hubwire.HEAD_WAVES_FIELD, hubwire.HEAD_UBATCH_FIELD) == ("waves", "ubatch")
    assert hubwire.TUNNEL_LISTEN_FIELD == "listen"
    # waves turn on at two; the fork runs at most its scheduler's input copies,
    # 4 in a default build
    assert (hubwire.MIN_WAVES, hubwire.MAX_WAVES) == (2, 4)
    assert {hubwire.FEATURE_HUB_HEAD, hubwire.FEATURE_PROBE_BULK_2M} <= set(
        hubwire.FEATURES
    )


# --- a rig that names the feature reads and checks the fields ------------------------


def test_a_hub_head_reads_its_fields() -> None:
    start = w.read_head_start(
        _envelope("head_start", _head_body(slots=32, **HUB_FIELDS)), features=HUB_HEAD
    )
    assert (start.slots, start.output_local, start.waves, start.ubatch) == (
        32,
        True,
        4,
        29,
    )
    top = w.read_head_start(
        _envelope("head_start", _head_body(slots=hubwire.HUB_HEAD_MAX_SLOTS)),
        features=HUB_HEAD,
    )
    assert top.slots == hubwire.HUB_HEAD_MAX_SLOTS
    for local in (False, None):
        nulls = _head_body(slots=4, output_local=local, waves=None, ubatch=None)
        read = w.read_head_start(_envelope("head_start", nulls), features=HUB_HEAD)
        assert (read.output_local, read.waves, read.ubatch) == (False, None, None)
    peer = w.read_tunnel_up(
        _envelope("tunnel_up", _up_body(listen=None)), features=HUB_HEAD
    )
    assert peer.peers[0].listen is False


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"slots": hubwire.HUB_HEAD_MAX_SLOTS + 1}, "slots"),
        ({"slots": 0}, "slots"),
        ({"output_local": 1}, "output_local"),
        ({"output_local": "true"}, "output_local"),
        ({"slots": 32, "waves": 1}, "waves"),
        ({"slots": 64, "waves": hubwire.MAX_WAVES + 1}, "waves"),
        ({"slots": 32, "waves": True}, "waves"),
        ({"slots": 32, "waves": 4.0}, "waves"),
        ({"slots": 3, "waves": 4}, "waves"),  # more waves than slots
        ({"slots": 64, "waves": 4, "ubatch": 15}, "ubatch"),  # 16 slots a wave
        ({"ubatch": 0}, "ubatch"),
        ({"ubatch": hubwire.HEAD_UBATCH + 1}, "ubatch"),
        ({"ubatch": "32"}, "ubatch"),
        # one wave's slots (ceil(32 / 2) = 16) above the micro-batch: the fork
        # would turn waves off
        ({"slots": 32, "waves": 2, "ubatch": 15}, "ubatch"),
    ],
)
def test_a_hub_head_refuses_a_field_out_of_its_kind_or_range_by_name(
    changes: dict[str, Any], field: str
) -> None:
    body = _head_body(**changes)
    _refused(
        lambda: w.read_head_start(_envelope("head_start", body), features=HUB_HEAD),
        field,
    )


def test_a_hub_head_reads_a_listen_peer_and_refuses_one_on_a_ring_link() -> None:
    up = w.read_tunnel_up(
        _envelope("tunnel_up", _up_body(listen=True)), features=HUB_HEAD
    )
    assert up.peers[0].listen is True
    assert up.peers[0].endpoints == ()
    off = w.read_tunnel_up(
        _envelope("tunnel_up", _up_body(listen=False)), features=HUB_HEAD
    )
    assert off.peers[0].listen is False
    _refused(
        lambda: w.read_tunnel_up(
            _envelope("tunnel_up", _up_body(listen="yes")), features=HUB_HEAD
        ),
        "peers.listen",
    )
    ring = {"listen": True, "ring": {"dial_ports": [50052]}}
    _refused(
        lambda: w.read_tunnel_up(
            _envelope("tunnel_up", _up_body(**ring)), features=HUB_HEAD
        ),
        "peers.listen",
    )
    # a ring peer that does not listen is read as before
    plain_ring = {"ring": {"dial_ports": [50052]}}
    read = w.read_tunnel_up(
        _envelope("tunnel_up", _up_body(**plain_ring)), features=HUB_HEAD
    )
    assert read.peers[0].ring is not None and read.peers[0].listen is False


def test_a_rig_with_the_bulk_feature_takes_up_to_two_mib() -> None:
    top = hubwire.HUB_PROBE_BULK_BYTES
    run = w.read_probe_run(
        _envelope("probe_run", _run_body(bulk_bytes=top)), features=BULK_2M
    )
    assert run.bulk_bytes == top
    _refused(
        lambda: w.read_probe_run(
            _envelope("probe_run", _run_body(bulk_bytes=top + 1)), features=BULK_2M
        ),
        "bulk_bytes",
    )


# --- the published schema says the same ----------------------------------------------


def _props(schema: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = schema["$defs"][name]["properties"]
    return found


def _branch(node: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = next(b for b in node["anyOf"] if b.get("type") != "null")
    return found


def test_the_schema_publishes_the_new_fields_optional_and_off(
    schema: dict[str, Any],
) -> None:
    assert {hubwire.FEATURE_HUB_HEAD, hubwire.FEATURE_PROBE_BULK_2M} <= set(
        schema["x-features"]
    )
    head = schema["$defs"]["HeadStartBody"]
    props = head["properties"]
    assert (props["slots"]["minimum"], props["slots"]["maximum"]) == (
        1,
        hubwire.HUB_HEAD_MAX_SLOTS,
    )
    assert props["slots"]["default"] == hubwire.DEFAULT_SLOTS
    # optional and null by default, so a hub that leaves out what is None sends
    # every start as before
    local = props[hubwire.HEAD_OUTPUT_LOCAL_FIELD]
    assert (_branch(local)["type"], local["default"]) == ("boolean", None)
    waves = props[hubwire.HEAD_WAVES_FIELD]
    assert waves["default"] is None
    assert (_branch(waves)["minimum"], _branch(waves)["maximum"]) == (
        hubwire.MIN_WAVES,
        hubwire.MAX_WAVES,
    )
    ubatch = props[hubwire.HEAD_UBATCH_FIELD]
    assert ubatch["default"] is None
    assert (_branch(ubatch)["minimum"], _branch(ubatch)["maximum"]) == (
        1,
        hubwire.HEAD_UBATCH,
    )
    new = {hubwire.HEAD_OUTPUT_LOCAL_FIELD, hubwire.HEAD_WAVES_FIELD}
    assert not (new | {hubwire.HEAD_UBATCH_FIELD}) & set(head["required"])
    peer = schema["$defs"]["TunnelPeer"]
    listen = peer["properties"][hubwire.TUNNEL_LISTEN_FIELD]
    assert (_branch(listen)["type"], listen["default"]) == ("boolean", None)
    assert hubwire.TUNNEL_LISTEN_FIELD not in peer["required"]
    bulk = _props(schema, "ProbeRunBody")["bulk_bytes"]
    assert (bulk["maximum"], bulk["default"]) == (hubwire.HUB_PROBE_BULK_BYTES, 0)
    # both caps are on record: the old one for a rig without probe_bulk_2m
    assert schema["x-probe-max-bulk-bytes"] == hubwire.MAX_PROBE_BULK_BYTES
    status = schema["$defs"]["SessionStatusBody"]
    t_out = status["properties"][hubwire.T_OUT_MS_FIELD]
    assert t_out["default"] is None
    assert _branch(t_out) == {
        "type": "number",
        "minimum": 0,
        "maximum": hubwire.MAX_T_OUT_MS,
    }
    threads = status["properties"][hubwire.T_OUT_THREADS_FIELD]
    assert threads["default"] is None
    assert (_branch(threads)["minimum"], _branch(threads)["maximum"]) == (
        1,
        hubwire.MAX_RESOURCE_CORES,
    )
    new_status = {hubwire.T_OUT_MS_FIELD, hubwire.T_OUT_THREADS_FIELD}
    assert not new_status & set(status["required"])
    # a hub head is role head on the wire: the roles stay a closed set of two
    assert hubwire.RIG_ROLES == ("head", "worker")


def test_the_schema_keeps_max_slots_for_unit_adverts_and_cache_answers(
    schema: dict[str, Any],
) -> None:
    unit = _props(schema, "AdvertisedUnit")
    assert unit["slots"]["maximum"] == hubwire.MAX_SLOTS
    assert unit["free_slots"]["maximum"] == hubwire.MAX_SLOTS
    assert _props(schema, "CacheFit")["slots"]["items"]["maximum"] == hubwire.MAX_SLOTS


def test_what_a_hub_sends_a_hub_head_is_valid_and_so_is_what_it_sent_before(
    schema: dict[str, Any],
) -> None:
    for kind, body in (
        ("head_start", _head_body()),
        ("head_start", _head_body(slots=64, output_local=True, waves=4, ubatch=29)),
        ("tunnel_up", _up_body()),
        ("tunnel_up", _up_body(listen=True)),
        ("probe_run", _run_body(bulk_bytes=hubwire.HUB_PROBE_BULK_BYTES)),
    ):
        rig_schema.validate(
            {"v": 1, "type": kind, "id": "c1", "body": body},
            schema,
            "#/$defs/HubMessage",
        )
    for kind, body in (
        ("head_start", _head_body(slots=65)),
        ("head_start", _head_body(waves=1)),
        ("head_start", _head_body(ubatch=513)),
        ("tunnel_up", _up_body(listen="yes")),
        ("probe_run", _run_body(bulk_bytes=hubwire.HUB_PROBE_BULK_BYTES + 1)),
    ):
        with pytest.raises(rig_schema.SchemaError):
            rig_schema.validate(
                {"v": 1, "type": kind, "id": "c1", "body": body},
                schema,
                "#/$defs/HubMessage",
            )


# --- the rule a hub head's waves and micro-batch keep --------------------------------


@pytest.mark.parametrize(
    ("slots", "waves", "ubatch"),
    [
        (1, None, None),
        (64, None, None),
        (32, 4, 8),
        (33, 4, 9),
        (64, 4, 16),  # 4 waves of 64 slots: 16 slots a wave
        (64, 4, None),
        (2, 2, 1),
    ],
)
def test_waves_and_a_micro_batch_that_hold_a_wave_fit(
    slots: int, waves: int | None, ubatch: int | None
) -> None:
    hubwire.head_waves_fit(slots=slots, waves=waves, ubatch=ubatch)


@pytest.mark.parametrize(
    ("slots", "waves", "ubatch", "field"),
    [
        (0, None, None, "slots"),
        (65, None, None, "slots"),
        (True, None, None, "slots"),
        (4, None, 0, "ubatch"),
        (4, None, 513, "ubatch"),
        (4, 1, None, "waves"),
        (4, 5, None, "waves"),
        (64, 5, None, "waves"),  # the fork would run 4
        (64, 8, 16, "waves"),
        (64, 4, 15, "ubatch"),  # ceil(64 / 4) = 16 slots a wave
        (32, 4, 7, "ubatch"),  # ceil(32 / 4) = 8 slots a wave
        (33, 4, 8, "ubatch"),  # ceil(33 / 4) = 9, the fork's rounding
    ],
)
def test_waves_or_a_micro_batch_that_do_not_are_refused_by_name(
    slots: Any, waves: Any, ubatch: Any, field: str
) -> None:
    with pytest.raises(ValueError, match=f"^{field}: "):
        hubwire.head_waves_fit(slots=slots, waves=waves, ubatch=ubatch)


# --- the micro-batch rule ------------------------------------------------------------


def _ub(rtt_ms: int, mbit: int, *, slots: int = 32, waves: int | None = 4) -> int:
    return hubwire.hub_head_ubatch(
        slots=slots,
        waves=waves,
        rtt_us=rtt_ms * 1000,
        uplink_kbps=mbit * 1000,
        token_bytes=TOKEN_BYTES,
    )


def test_the_micro_batch_at_two_worked_points() -> None:
    # 32 slots in 4 waves, 120 ms: floor(0.120 s x 20 Mbit/s / 81,920 bit)
    # = floor(29.3) = 29, and at 10 Mbit/s floor(14.6) = 14
    assert _ub(120, 20) == 29
    assert _ub(120, 10) == 14


def test_the_micro_batch_never_drops_below_a_wave_nor_rises_past_the_heads() -> None:
    # max(ceil(slots / waves), ...): 32 / 4 = 8 on an uplink too thin
    assert _ub(120, 0) == 8
    assert _ub(120, 1) == 8
    # ... and min(512, ...): a fat uplink gets every head's -ub of today, 512
    assert _ub(120, 1000) == hubwire.HEAD_UBATCH
    # no waves: one tick holds every slot
    assert _ub(120, 0, waves=None) == 32
    # a wave count that does not divide the slots rounds up, as the fork does
    assert _ub(120, 0, slots=33) == 9


def test_the_micro_batchs_prompt_tokens_cross_the_uplink_within_one_round_trip() -> (
    None
):
    # a chunk of c tokens costs c x 10,240 B x 8 / U on the uplink: c = 32 at
    # 20 Mbit/s is 131 ms, so the rule's 29 must fit in 120 ms
    assert round(32 * TOKEN_BYTES * 8 / 20e6 * 1000) == 131
    for rtt_ms in (20, 60, 120, 131, 250):
        for mbit in (5, 10, 20, 50, 100):
            ub = _ub(rtt_ms, mbit)
            if 8 < ub < hubwire.HEAD_UBATCH:
                assert ub * TOKEN_BYTES * 8 / (mbit * 1e6) <= rtt_ms / 1000
                assert (ub + 1) * TOKEN_BYTES * 8 / (mbit * 1e6) > rtt_ms / 1000


def test_every_micro_batch_the_rule_gives_passes_the_waves_rule() -> None:
    for slots in (1, 2, 7, 16, 32, 33, 64):
        for waves in (None, 2, 3, 4):
            if waves is not None and waves > slots:
                continue
            for mbit in (0, 1, 10, 20, 100, 10_000):
                ub = _ub(120, mbit, slots=slots, waves=waves)
                hubwire.head_waves_fit(slots=slots, waves=waves, ubatch=ub)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"slots": 65}, "slots"),
        ({"waves": 1}, "waves"),
        ({"waves": 5}, "waves"),
        ({"rtt_us": -1}, "rtt_us"),
        ({"rtt_us": hubwire.MAX_RTT_US + 1}, "rtt_us"),
        ({"uplink_kbps": -1}, "uplink_kbps"),
        ({"uplink_kbps": hubwire.MAX_RATE_KBPS + 1}, "uplink_kbps"),
        ({"token_bytes": 0}, "token_bytes"),
    ],
)
def test_the_micro_batch_rule_refuses_an_input_out_of_range(
    changes: dict[str, Any], field: str
) -> None:
    inputs: dict[str, Any] = {
        "slots": 32,
        "waves": 4,
        "rtt_us": 120_000,
        "uplink_kbps": 20_000,
        "token_bytes": TOKEN_BYTES,
    }
    inputs.update(changes)
    with pytest.raises(ValueError, match=f"^{field}: "):
        hubwire.hub_head_ubatch(**inputs)


# --- the cache above MAX_SLOTS slots -------------------------------------------------


def _law(row: dict[str, Any], ctx: int, slots: int) -> tuple[int, int]:
    """The product's own cache law at ``ctx`` a slot over ``slots`` slots, in MiB
    rounded up as a rig answers (``inventory.cache_fit``), and the excess a run of
    blocks holds over its share."""

    def cache(layers: list[dict[str, Any]] | None) -> int:
        return vramfit.kv_bytes(
            row,
            ctx * slots,
            n_seq_max=slots,
            n_ubatch=hubwire.HEAD_UBATCH,
            cache_type_k=hubwire.HEAD_KV_CACHE_TYPE,
            cache_type_v=hubwire.HEAD_KV_CACHE_TYPE,
            layers=layers,
        )["total"]

    whole = cache(None) + vramfit.rs_bytes(row, n_seq_max=slots)["total"]
    costs = [0] * row["n_layer"]
    for layer in row["kv_layers"]:
        costs[layer["layer"]] += cache([layer])
    for block in row.get("recurrent_blocks", ()):
        costs[block] += vramfit.rs_bytes(
            row, n_seq_max=slots, recurrent_layers_on_device=1
        )["total"]
    excess = inventory._run_excess(costs, whole)
    return math.ceil(whole / MIB), math.ceil(excess / MIB)


def _cut(fit: hubwire.CacheFit, widest: int) -> hubwire.CacheFit:
    """``fit`` as a rig that answers up to ``widest`` slots would send it."""
    keep = [j for j, s in enumerate(fit.slots) if s <= widest]
    return hubwire.CacheFit(
        slots=tuple(fit.slots[j] for j in keep),
        ctx=fit.ctx,
        cache_mib=tuple(tuple(row[j] for j in keep) for row in fit.cache_mib),
        excess_mib=tuple(tuple(row[j] for j in keep) for row in fit.excess_mib),
    )


@pytest.mark.parametrize("row", [DENSE, SLIDING, RECURRENT], ids=lambda r: r["arch"])
@pytest.mark.parametrize(
    ("widest", "slots"),
    [(w, s) for w in (16, 8) for s in (9, 12, 17, 24, 32, 48, 64) if s > w],
)
def test_the_cache_above_the_widest_answer_holds_the_products_own_law(
    row: dict[str, Any], widest: int, slots: int
) -> None:
    # fit_beyond against the product's own cache law, from a rig that answers up
    # to 16 slots and from one that answers up to 8
    full = inventory.cache_fit(row)
    assert full is not None
    fit = _cut(full, widest)
    for ctx in fit.ctx:
        found = hubwire.fit_beyond(fit, ctx, slots)
        assert found is not None
        total, excess = (value // MIB for value in found)
        want_total, want_excess = _law(row, ctx, slots)
        # never below the law, and above it by the scaled rounding of the
        # widest answer only: under a MiB per widest count of slots
        slack = math.ceil(slots / widest)
        assert want_total <= total <= want_total + slack, (ctx, total)
        assert want_excess <= excess <= want_excess + slack, ctx


def test_the_cache_up_to_max_slots_is_the_rigs_own_answer() -> None:
    fit = inventory.cache_fit(DENSE)
    assert fit is not None
    for ctx in (1, 2048, 4096, 40960):
        for slots in range(1, hubwire.MAX_SLOTS + 1):
            assert hubwire.fit_beyond(fit, ctx, slots) == fit.at(ctx, slots)


def test_the_cache_above_max_slots_scales_the_16_slot_answer() -> None:
    fit = hubwire.CacheFit(
        slots=(8, 16),
        ctx=(2048, 4096),
        cache_mib=((50, 100), (90, 181)),
        excess_mib=((1, 3), (2, 5)),
    )
    # 4096 a slot: 181 MiB x 32 / 16 = 362, 5 x 2 = 10; x 64 / 16: 724, 20
    assert hubwire.fit_beyond(fit, 4096, 32) == (362 * MIB, 10 * MIB)
    assert hubwire.fit_beyond(fit, 4096, 64) == (724 * MIB, 20 * MIB)
    # 17 slots: rounded up, ceil(181 x 17 / 16) = 193, ceil(5 x 17 / 16) = 6
    assert hubwire.fit_beyond(fit, 4096, 17) == (193 * MIB, 6 * MIB)
    # a smaller context takes the cheapest answer reaching it, as at() does
    assert hubwire.fit_beyond(fit, 1000, 32) == (200 * MIB, 6 * MIB)
    # no answer reaches the context: none
    assert hubwire.fit_beyond(fit, 8192, 32) is None


def test_the_cache_above_the_widest_answer_grows_from_it_when_16_is_absent() -> None:
    # a rig answers the counts a hub halves its target through, so 16 can be
    # absent: grow from the largest count answered
    narrow = hubwire.CacheFit(
        slots=(1, 8), ctx=(4096,), cache_mib=((10, 80),), excess_mib=((0, 1),)
    )
    assert hubwire.fit_beyond(narrow, 4096, 8) == narrow.at(4096, 8)
    # 80 MiB x 32 / 8 = 320, 1 x 4 = 4; 12 slots: ceil(120), ceil(1.5) = 2
    assert hubwire.fit_beyond(narrow, 4096, 32) == (320 * MIB, 4 * MIB)
    assert hubwire.fit_beyond(narrow, 4096, 12) == (120 * MIB, 2 * MIB)
    assert narrow.at(4096, 12) is None  # what a rig head's plan still reads


@pytest.mark.parametrize("slots", [0, hubwire.HUB_HEAD_MAX_SLOTS + 1, True])
def test_the_cache_rule_refuses_slots_out_of_range(slots: Any) -> None:
    fit = inventory.cache_fit(DENSE)
    assert fit is not None
    with pytest.raises(ValueError, match=r"^slots: "):
        hubwire.fit_beyond(fit, 4096, slots)


# --- a hub head reports its output stage's time --------------------------------------


def test_a_status_without_an_output_time_is_written_as_before(
    schema: dict[str, Any],
) -> None:
    frame = w.session_status("q1", session_id="s1", state="ready", role="head")
    body = json.loads(frame)["body"]
    assert body == {"session_id": "s1", "state": "ready", "role": "head"}
    rig_schema.validate(json.loads(frame), schema, "#/$defs/AgentMessage")


def test_a_hub_head_writes_its_output_time_and_threads(schema: dict[str, Any]) -> None:
    frame = w.session_status(
        None, session_id="s1", state="ready", t_out_ms=61.5, t_out_threads=4
    )
    body = json.loads(frame)["body"]
    assert (body[hubwire.T_OUT_MS_FIELD], body[hubwire.T_OUT_THREADS_FIELD]) == (
        61.5,
        4,
    )
    rig_schema.validate(json.loads(frame), schema, "#/$defs/AgentMessage")
    whole = w.session_status(None, session_id="s1", state="ready", t_out_ms=60)
    assert json.loads(whole)["body"][hubwire.T_OUT_MS_FIELD] == 60.0
    for bad in (
        {"t_out_ms": hubwire.MAX_T_OUT_MS + 1},
        {"t_out_ms": 1e9},
    ):
        message = {
            "v": 1,
            "type": "session_status",
            "id": "a1",
            "body": {"session_id": "s1", "state": "ready", **bad},
        }
        with pytest.raises(rig_schema.SchemaError):
            rig_schema.validate(message, schema, "#/$defs/AgentMessage")


@pytest.mark.parametrize(
    ("t_out_ms", "t_out_threads", "field"),
    [
        (-0.1, None, "t_out_ms"),
        (hubwire.MAX_T_OUT_MS + 0.5, None, "t_out_ms"),
        (float("nan"), None, "t_out_ms"),
        (float("inf"), None, "t_out_ms"),
        (True, None, "t_out_ms"),
        ("60", None, "t_out_ms"),
        (60.0, 0, "t_out_threads"),
        (60.0, hubwire.MAX_RESOURCE_CORES + 1, "t_out_threads"),
        (60.0, 4.0, "t_out_threads"),
        (60.0, True, "t_out_threads"),
        (None, 4, "t_out_threads"),  # threads only beside a time
    ],
)
def test_an_output_time_out_of_its_kind_or_range_is_refused_by_name(
    t_out_ms: Any, t_out_threads: Any, field: str
) -> None:
    with pytest.raises(ValueError, match=f"^{field}: "):
        hubwire.t_out_fits(t_out_ms, t_out_threads)
    with pytest.raises(ValueError, match=f"^{field}: "):
        w.session_status(
            None,
            session_id="s1",
            state="ready",
            t_out_ms=t_out_ms,
            t_out_threads=t_out_threads,
        )


def test_an_output_time_in_range_fits() -> None:
    for t_out_ms, threads in ((None, None), (0, None), (0.0, 1), (60_000, 1024)):
        hubwire.t_out_fits(t_out_ms, threads)


# --- the longer probe train, for a rig that names probe_bulk_2m only ----------------


def _probes(features: tuple[str, ...] = ()) -> probe.Probes:
    return probe.Probes(
        send=lambda frame: True,
        port=lambda: None,
        hosts=lambda: ("192.0.2.10",),
        bind_host="127.0.0.1",
        features=features,
    )


def test_the_probe_train_bound_is_lifted_only_for_a_rig_that_names_the_feature() -> (
    None
):
    # MAX_TRAIN comes from the 256 KiB cap over the 36-byte smallest packet
    assert probe.MAX_TRAIN == -(-256 * 1024 // 36)
    assert probe.MAX_TRAIN_BULK_2M == -(-2 * 1024 * 1024 // 36)
    assert _probes()._max_train == probe.MAX_TRAIN
    assert _probes(HUB_HEAD)._max_train == probe.MAX_TRAIN
    assert _probes(BULK_2M)._max_train == probe.MAX_TRAIN_BULK_2M


def test_a_probe_run_of_two_mib_is_read_only_by_a_rig_that_names_the_feature() -> None:
    run = _envelope("probe_run", _run_body(bulk_bytes=hubwire.HUB_PROBE_BULK_BYTES))
    with pytest.raises(protocol.ProtocolError) as refused:
        _probes().run(run)
    assert refused.value.message.startswith("body.bulk_bytes:")
    # read: then refused only because no such probe is open
    answer = _probes(BULK_2M).run(run)
    assert answer is not None and json.loads(answer)["body"]["code"] == "not_ready"
