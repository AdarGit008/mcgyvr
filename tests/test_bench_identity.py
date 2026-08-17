"""Run identity, and the two ways a table is refused (#265, ADR-0027).

The acceptance item this file exists for is *"a manifest mutated in any identity
field is refused by the guard, proven by a test per field"* — so the parametrised
case below iterates :data:`identity.KEY` itself rather than a list written out
here. A field added to the key without a mutation that refuses is a test failure,
which is the only arrangement under which the coverage claim stays true after
the next lane edits the key.

The second refusal is the one the old guard did not make. It compared
``manifest.get(key)`` across cells, so a field **no cell carried** yielded one
value and passed — `round` and `product_sha256` are the live case, carried by 6
of the 139 manifests on disk. Absence agreeing with absence reads as having
checked, and every pre-round table was reading that way.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def identity() -> Any:
    return _by_path("bench_identity_t", REPO / "tools" / "bench" / "identity.py")


def _manifest(**overrides: Any) -> dict[str, Any]:
    """One fully fingerprinted record — every keyed field obtained."""
    manifest = {
        "model": "qwen2.5-coder:1.5b",
        "endpoint": "http://srv2:11434",
        "serving_build": "0.32.5",
        "protocol": "openai",
        "tier": "bench-py",
        "condition": "stock",
        "greedy_temperature": 0.0,
        "max_output_tokens": 2048,
        "tasks_sha256": {"function_implementation": "abc123"},
        "gate_rungs": ["scope", "secrets", "structured", "adapters", "acceptance"],
        "round": "r1-commissioning",
        "product_sha256": "ed508e61",
    }
    manifest.update(overrides)
    return manifest


# A value of the right shape that is not the fixture's, per keyed field. Mutating
# a string to another string and a list to another list keeps the refusal about
# identity rather than about a type error.
OTHER: dict[str, Any] = {
    "model": "qwen2.5-coder:7b",
    "endpoint": "http://srv1:11434",
    "serving_build": "0.32.4",
    "protocol": "ollama",
    "tier": "bench-ts",
    "greedy_temperature": 0.7,
    "max_output_tokens": 512,
    "tasks_sha256": {"function_implementation": "def456"},
    "gate_rungs": ["acceptance"],
    "round": "r2",
    "product_sha256": "0000dead",
}


# --- a mutation in any keyed field is refused -------------------------------


def test_every_keyed_field_has_a_mutation_that_refuses(identity: Any) -> None:
    """The coverage claim, checked rather than asserted in a docstring."""
    uncovered = [f for f in identity.KEY if f not in OTHER]
    assert not uncovered, (
        f"{uncovered} joined the comparability key with no mutation case. A key "
        "that grows faster than its tests is a guard nobody has exercised."
    )


@pytest.mark.parametrize("field", sorted(OTHER))
def test_a_record_mutated_in_one_identity_field_is_refused(
    identity: Any, field: str
) -> None:
    with pytest.raises(identity.IdentityError, match=field):
        identity.require_comparable(
            [_manifest(), _manifest(condition="planonly", **{field: OTHER[field]})]
        )


def test_two_records_differing_only_in_the_contrast_axis_are_compared(
    identity: Any,
) -> None:
    """The guard must not refuse the difference the table exists to show."""
    identity.require_comparable([_manifest(), _manifest(condition="planonly")])


# --- absence is not agreement -----------------------------------------------


@pytest.mark.parametrize("state", ["absent", "null"])
def test_a_field_no_record_can_answer_refuses_rather_than_matching(
    identity: Any, state: str
) -> None:
    """The defect: two silences compared equal, and the table read as checked."""
    cells = []
    for condition in ("stock", "planonly"):
        manifest = _manifest(condition=condition)
        if state == "absent":
            del manifest["product_sha256"]
        else:
            manifest["product_sha256"] = None
        cells.append(manifest)
    with pytest.raises(identity.IdentityError, match="product_sha256"):
        identity.require_comparable(cells)


def test_the_waiver_is_a_parameter_and_never_a_default(identity: Any) -> None:
    """Reading pre-contract records is legitimate; doing it silently is not."""
    cells = [_manifest(condition=c) for c in ("stock", "planonly")]
    for cell in cells:
        del cell["round"]
        del cell["product_sha256"]
    with pytest.raises(identity.IdentityError):
        identity.require_comparable(cells)
    identity.require_comparable(cells, allow_unfingerprinted=True)


def test_one_record_is_not_refused_for_what_it_could_not_answer(
    identity: Any,
) -> None:
    """ADR-0024's consequence survives: an unknown build is still a rate.

    The defect is two records agreeing *by shared absence*. One record agrees
    with nothing, so there is no comparison to refuse — what the caller owes is
    a statement of what it could not check, which is `unfingerprinted`.
    """
    manifest = _manifest(serving_build=None)
    identity.require_comparable([manifest])
    assert identity.unfingerprinted(manifest) == ["serving_build"]


def test_the_three_states_are_distinguishable(identity: Any) -> None:
    manifest = _manifest(serving_build=None)
    del manifest["round"]
    assert identity.state(manifest, "model") == identity.OBTAINED
    assert identity.state(manifest, "serving_build") == identity.REFUSED
    assert identity.state(manifest, "round") == identity.ABSENT


# --- one condition, one render ----------------------------------------------


def test_one_condition_rendered_two_ways_is_refused(identity: Any) -> None:
    """ADR-0027 D6 — a check inside the axis needs no admission experiment."""
    cells = [
        _manifest(condition="stock", bundle_sha256="aaa"),
        _manifest(condition="stock", bundle_sha256="bbb"),
    ]
    with pytest.raises(identity.IdentityError, match="bundle_sha256"):
        identity.require_comparable(cells)


def test_two_conditions_may_render_differently(identity: Any) -> None:
    """Which is the entire point of an ablation, and must not be refused."""
    identity.require_comparable(
        [
            _manifest(condition="stock", bundle_sha256="aaa"),
            _manifest(condition="norule", bundle_sha256="bbb"),
        ]
    )


# --- the conventions --------------------------------------------------------


def test_the_digest_is_stable_under_key_order(identity: Any) -> None:
    """One convention, because three lanes would otherwise write three."""
    assert identity.digest({"a": 1, "b": [2, 3]}) == identity.digest(
        {"b": [2, 3], "a": 1}
    )
    assert identity.digest({"a": 1}) != identity.digest({"a": 2})
    assert len(identity.digest("x")) == 64


def test_the_contrast_axis_is_never_a_keyed_field(identity: Any) -> None:
    assert identity.CONTRAST not in identity.KEY
    with pytest.raises(identity.IdentityError, match="contrast axis"):
        identity.require_comparable([_manifest()], contrast="model")


def test_recorded_is_wider_than_keyed_and_the_gap_is_named(identity: Any) -> None:
    """#276: recording is unconditional, keying is earned by perturbation.

    The three digests ADR-0026 asked for sit in `PENDING` rather than in `KEY`,
    and that is the correct state rather than an omission — nothing writes them
    yet, and a field in the key that nothing writes is a check that cannot fire.
    """
    assert set(identity.KEY) <= set(identity.RECORDED)
    for field in ("model_sha256", "bar_sha256", "prompt_sha256"):
        assert field in identity.PENDING
        assert field not in identity.KEY


def test_bundle_sha256_is_recorded_and_not_keyed_by_decision(identity: Any) -> None:
    """ADR-0032 clause 6 (#291), which asked the question and answered it `no`.

    Unlike its neighbours in `PENDING` this one has a writer
    (`tools/breadth/measure.py:915`), so "nothing writes it" is not the reason —
    #276's admission rule is, and no perturbation run has been done. The gap it
    was raised to close is covered from the other end: `src/mcgyvr/prompts/*.md`
    entered `product.SURFACE`, so the prompt files move `product_sha256`, which
    is keyed.
    """
    assert "bundle_sha256" in identity.RECORDED
    assert "bundle_sha256" in identity.PENDING
    assert "bundle_sha256" not in identity.KEY
    assert "product_sha256" in identity.KEY


def test_drift_reads_absence_as_a_difference(identity: Any) -> None:
    """The resume check's question, and the same rule as the guard's."""
    complete = _manifest()
    partial = _manifest()
    del partial["serving_build"]
    assert identity.drift(complete, partial) == ["serving_build"]
    assert identity.drift(complete, _manifest()) == []
    assert identity.drift(complete, _manifest(model=OTHER["model"])) == ["model"]


def test_the_key_is_one_list_and_the_report_reads_it(identity: Any) -> None:
    """ADR-0027 D1 — five lists disagreed, and three lanes were queued to edit."""
    report = _by_path("bench_report_identity_t", REPO / "tools" / "bench" / "report.py")
    assert report.COMPARABLE is identity.KEY or tuple(report.COMPARABLE) == tuple(
        identity.KEY
    )
    assert tuple(report.BOUND_MATCH) == tuple(identity.BOUND_MATCH)


def test_the_bound_key_fields_are_all_in_the_comparability_key(
    identity: Any,
) -> None:
    """#276 corollary 3 — admitted by construction, since the rule is circular
    for the four fields it cannot hold fixed while varying."""
    assert set(identity.BOUND_MATCH) <= set(identity.KEY)


def test_the_three_tags_are_computed_from_what_the_record_carries(
    identity: Any,
) -> None:
    """ADR-0027 D8 — computed on read, so a widening key demotes rather than lies."""
    assert identity.tag(_manifest()) == identity.VERIFIED

    incomplete = _manifest()
    del incomplete["round"]
    assert identity.tag(incomplete) == identity.BACKFILLED

    unidentifiable = _manifest()
    del unidentifiable["model"]
    assert identity.tag(unidentifiable) == identity.NO_FINGERPRINT


def test_a_rig_sweep_without_a_condition_is_not_thereby_untrusted(
    identity: Any,
) -> None:
    """96 of the manifests on disk are sweeps that never had a condition.

    `read_cell` requires one, because a bench cell without a condition cannot be
    placed in a matrix. The tag must not inherit that: "not a bench run" and
    "cannot say what produced it" are different states.
    """
    sweep = _manifest()
    del sweep["condition"]
    assert identity.tag(sweep) != identity.NO_FINGERPRINT


def test_the_inventory_skips_records_that_are_not_machine_written(
    identity: Any, tmp_path: Path
) -> None:
    """Three directories hold hand-authored evidence whose `protocol` is prose."""
    machine = tmp_path / "machine"
    machine.mkdir()
    (machine / "run.json").write_text(json.dumps(_manifest()))
    authored = tmp_path / "authored"
    authored.mkdir()
    (authored / "run.json").write_text(
        json.dumps({"record": "evidence/1", "protocol": {"eval": "EvalPlus 0.3.1"}})
    )
    found = identity.inventory(tmp_path)
    assert [name for _, name, _ in found] == [identity.VERIFIED]


def test_a_manifest_on_disk_can_be_read_for_its_state(identity: Any) -> None:
    """The migration's precondition (ADR-0027 D8), run against real records.

    Not an assertion about how many are fingerprinted — that number is the
    campaign's to move. What is pinned is that the question is answerable from
    the manifest alone, which is what a tagging pass needs.
    """
    manifests = sorted(REPO.glob("records/measurements/**/run.json"))
    assert manifests, "no measurement records to read"
    for path in manifests[:20]:
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(recorded, dict):
            continue
        missing = identity.unfingerprinted(recorded)
        assert all(f in identity.KEY for f in missing)
