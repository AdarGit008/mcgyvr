"""A `jev:` block names the one unit every typed decision asks.

A typed decision is a question answered with a single token, never prose: the
gate's Jev rung, the reviewer's verdict, the fleet's wake routing, the ladder
manager's choices and the typed proposer. The `jev:` block is a role block
like `orchestrator:` and `verifier:` — a `unit`, and a `model` that defaults
to the unit's own — so one configured unit can answer all of them. Left
unbound it resolves to nothing, and every one of those callers asks what it
asked before the block existed.

The block is policy, not fleet: it lives in `policy.yaml` beside the other
role blocks, `mcgyvr setup` writes it unbound, and a `jev.unit` naming a unit
nobody declared is refused at load time, naming the key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import ROLE_UNIT_FIELDS, SCHEMA, ConfigSchemaError, parse
from mcgyvr.config import load as load_config
from mcgyvr.detect import Detection
from mcgyvr.fleet.files import _POLICY_KEYS
from mcgyvr.initialize import _sources_for, build, initialize
from mcgyvr.local_pool import source_map
from mcgyvr.propose import propose
from tests.machine_shapes import detection, shape, with_server

LADDER = """\
units:
  fast:
    address: http://localhost:18001
    model: example-coder:3b
    rig: local
  judge:
    address: http://localhost:18002
    model: example-judge:1b
    rig: local
ladder:
- fast
"""


def test_the_schema_holds_a_jev_role_block_right_after_the_verifier() -> None:
    names = [spec.name for spec in SCHEMA]
    assert names[names.index("verifier") + 1] == "jev"
    spec = next(spec for spec in SCHEMA if spec.name == "jev")
    assert spec.kind == "block"
    assert spec.block == ROLE_UNIT_FIELDS
    # The doc is the user's: it says which decisions the unit answers, and
    # what an unbound block leaves alone.
    assert "single-token" in spec.doc
    assert "today" in spec.doc


def test_the_jev_block_is_policy() -> None:
    assert "jev" in _POLICY_KEYS


def test_an_unbound_jev_block_resolves_to_no_model() -> None:
    assert source_map(parse(LADDER)).role_model("jev") is None


def test_a_bound_jev_unit_without_a_model_answers_on_the_units_own() -> None:
    body = LADDER + "jev:\n  unit: judge\n"
    assert source_map(parse(body)).role_model("jev") == "example-judge:1b"


def test_a_bound_jev_model_is_the_one_named() -> None:
    body = LADDER + "jev:\n  unit: judge\n  model: example-judge:1b-q8\n"
    assert source_map(parse(body)).role_model("jev") == "example-judge:1b-q8"


def test_a_jev_unit_nobody_declared_is_refused_naming_the_key() -> None:
    body = LADDER + "jev:\n  unit: nowhere\n"
    with pytest.raises(ConfigSchemaError, match=r"jev\.unit"):
        parse(body)


def _keyless_rig() -> Detection:
    machine = shape("one-card")
    taken = {server.kind for server in machine.servers}
    kind = next(kind for kind, _, _ in detect.PORT_CONVENTIONS if kind not in taken)
    return detection(with_server(machine, kind=kind, models=("example-model:small",)))


def test_init_writes_the_jev_block_unbound(tmp_path: Path) -> None:
    rig = _keyless_rig()
    data = build(rig, propose(sources=_sources_for(rig)))
    assert data["jev"] == {"unit": None, "model": None}

    result = initialize(tmp_path / "setup", detection=rig)
    assert result.written
    policy = (tmp_path / "setup" / "policy.yaml").read_text(encoding="utf-8")
    assert "\njev:" in policy
    assert source_map(load_config(tmp_path / "setup")).role_model("jev") is None
