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


# --- the writers (#285) -----------------------------------------------------
#
# ADR-0026 decided three fields change from a name to CONTENT and ADR-0027
# shipped the shape; ten of the 27 declared fields had no writer, so `PENDING`
# could not tell "not admitted" from "nothing computes it". These are the cases
# for what now computes them.


def test_the_prompt_digest_moves_when_the_user_message_does(identity: Any) -> None:
    """The whole defect. `bundle_sha256` hashes the SYSTEM half.

    Measured on `bench-py`'s 257 contracts: `bundle_sha256` is **one** value
    across `stock`, `norule`, `noscaffold` and `planonly`, because every one of
    those levers edits the user message. Four conditions, one digest, and the
    guard that reads it cannot tell a mislabelled cell from a correct one.
    """
    system = "You are a worker."
    before = identity.prompt_digest({"b001": (system, "write f(x)")})
    after = identity.prompt_digest({"b001": (system, "write f(x). Do not guess.")})
    assert before != after


def test_the_prompt_digest_covers_every_task_not_the_first(identity: Any) -> None:
    """A 498-task sweep is not described by task one."""
    base = {"b001": ("sys", "one"), "b002": ("sys", "two")}
    moved = {"b001": ("sys", "one"), "b002": ("sys", "two, changed")}
    assert identity.prompt_digest(base) != identity.prompt_digest(moved)
    assert identity.prompt_digest(base) == identity.prompt_digest(dict(base))


def test_the_prompt_digest_is_keyed_by_task_id(identity: Any) -> None:
    """Two tasks swapping renders is a different run, not the same one."""
    straight = {"b001": ("sys", "one"), "b002": ("sys", "two")}
    swapped = {"b001": ("sys", "two"), "b002": ("sys", "one")}
    assert identity.prompt_digest(straight) != identity.prompt_digest(swapped)


def test_the_prompt_digest_is_not_in_the_global_key(identity: Any) -> None:
    """D6 keys it WITHIN a condition, and the difference is not a nuance.

    The ablation changes the render on purpose, so `stock` and `norule` differ
    here by construction. In `KEY` that reads as two records that may not be
    laid beside each other — which would refuse every contrast the bench exists
    to draw. `require_comparable`'s per-condition loop is the mechanism, and it
    was already written; #285 supplies the writer, not a key entry.
    """
    assert "prompt_sha256" not in identity.KEY
    assert identity.PENDING_REASON["prompt_sha256"].startswith("keyed within")


def test_two_cells_naming_one_condition_with_two_renders_are_refused(
    identity: Any,
) -> None:
    """The D6 check, now that something writes the field it reads."""
    with pytest.raises(identity.IdentityError, match="prompt_sha256"):
        identity.require_comparable(
            [
                _manifest(condition="stock", prompt_sha256="aaa"),
                _manifest(condition="stock", prompt_sha256="bbb"),
            ]
        )


def test_two_conditions_may_differ_in_the_rendered_prompt(identity: Any) -> None:
    """And must, or the ablation did not happen."""
    identity.require_comparable(
        [
            _manifest(condition="stock", prompt_sha256="aaa"),
            _manifest(condition="norule", prompt_sha256="bbb"),
        ]
    )


# --- the bar ----------------------------------------------------------------


def _stage_python(into: Path) -> None:
    (into / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 88\n\n[tool.ruff.lint]\nselect = ["E", "F"]\n',
        encoding="utf-8",
    )


def _stage_python_wider(into: Path) -> None:
    (into / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 88\n\n[tool.ruff.lint]\nselect = ["E", "F", "B"]\n',
        encoding="utf-8",
    )


def test_the_bar_digest_moves_when_the_resolved_rule_set_does(identity: Any) -> None:
    """`gate_rungs` is five names across a 251-rule bar and a 66-rule one.

    Two selects that differ by one linter resolve to two rule sets, and this is
    the field that says so. Run against real ruff rather than a stub: what is
    being pinned is that ruff's own resolution is what gets hashed, and a stub
    would pin this test's idea of it.
    """
    narrow, why = identity.bar_digest(
        rungs=("acceptance",), language="python", stage_workspace=_stage_python
    )
    assert why is None and narrow is not None
    wide, why = identity.bar_digest(
        rungs=("acceptance",), language="python", stage_workspace=_stage_python_wider
    )
    assert why is None and wide is not None
    assert narrow != wide


def test_the_bar_digest_moves_with_the_rungs(identity: Any) -> None:
    one, _ = identity.bar_digest(
        rungs=("acceptance",), language="python", stage_workspace=_stage_python
    )
    five, _ = identity.bar_digest(
        rungs=("scope", "secrets", "structured", "adapters", "acceptance"),
        language="python",
        stage_workspace=_stage_python,
    )
    assert one != five


def test_the_bar_digest_is_per_language(identity: Any) -> None:
    """ADR-0026: no pooled figure across a stratum where the effect is
    heterogeneous, and the two arms' bars are the case it was written from."""
    assert identity.BAR_PROBE_FILE["python"] != identity.BAR_PROBE_FILE["jsts"]
    _, why = identity.bar_digest(
        rungs=("acceptance",), language="cobol", stage_workspace=_stage_python
    )
    assert why is not None and "cobol" in why


def test_a_bar_whose_resolver_will_not_answer_is_null_with_a_reason(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a bar is not the bar, and a digest over it would read as recorded.

    On a real dispatch this cannot fire — `score.require_toolchain` refuses a
    run with a missing rung tool before the first candidate — so this path is
    for off-rig callers, which is exactly who should not get a confident answer.
    """
    monkeypatch.setattr(identity, "_run", lambda *a, **k: None)
    found, why = identity.bar_digest(
        rungs=("acceptance",), language="python", stage_workspace=_stage_python
    )
    assert found is None
    assert why is not None and "ruff" in why


def test_a_staging_failure_is_a_reason_and_not_a_traceback(identity: Any) -> None:
    def explode(into: Path) -> None:
        raise RuntimeError("no eslint config to copy")

    found, why = identity.bar_digest(
        rungs=("acceptance",), language="python", stage_workspace=explode
    )
    assert found is None
    assert why is not None and "no eslint config to copy" in why


# --- the model --------------------------------------------------------------

SHOW = {
    "template": "{{ .System }}\n{{ .Prompt }}",
    "model_info": {
        "tokenizer.ggml.tokens": ["a", "b", "c"],
        "tokenizer.ggml.merges": ["a b"],
    },
}
TAGS = {"models": [{"name": "qwen2.5-coder:1.5b", "digest": "d7372fd828518a4d"}]}


def _endpoint(
    identity: Any, monkeypatch: pytest.MonkeyPatch, tags: Any, show: Any
) -> dict[str, Any]:
    """Answer the two ollama-native calls without a server."""
    sent: dict[str, Any] = {}

    def get(url: str, *, timeout: float) -> Any:
        sent["get"] = url
        return tags

    def post(url: str, body: dict[str, Any], *, timeout: float) -> Any:
        sent["post"] = (url, body)
        return show

    monkeypatch.setattr(identity, "_get_json", get)
    monkeypatch.setattr(identity, "_post_json", post)
    return sent


def test_the_model_probe_records_all_four_fields(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _endpoint(identity, monkeypatch, TAGS, SHOW)
    fields, reasons = identity.probe_model("http://srv2:11434", "qwen2.5-coder:1.5b")
    assert set(fields) == set(identity.MODEL_PROBE_FIELDS)
    assert not reasons
    assert fields["model_sha256"] == "d7372fd828518a4d"
    assert all(len(fields[f]) == 64 for f in fields if f != "model_sha256")


def test_the_probe_sends_verbose_because_the_flag_is_load_bearing(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without it the tokenizer arrays come back `null` rather than absent.

    Measured on `qwen2.5-coder:1.5b`: 0 tokens against 151,936. A probe that
    left the flag off would record "unobtainable" while the answer was one flag
    away, which reads as having checked — so the flag is pinned here rather than
    described in a comment.
    """
    sent = _endpoint(identity, monkeypatch, TAGS, SHOW)
    identity.probe_model("http://srv2:11434", "qwen2.5-coder:1.5b")
    _, body = sent["post"]
    assert body["verbose"] is True


def test_an_endpoint_that_will_not_answer_is_null_with_a_reason(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2: never a sentinel string, and never an absent key on a fresh run."""
    _endpoint(identity, monkeypatch, None, None)
    fields, reasons = identity.probe_model("http://nowhere:11434", "m")
    assert set(fields) == set(identity.MODEL_PROBE_FIELDS)
    assert all(v is None for v in fields.values())
    assert set(reasons) == set(identity.MODEL_PROBE_FIELDS)
    assert all("nowhere" in why for why in reasons.values())


def test_a_half_answering_endpoint_records_the_half_it_gave(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One field unobtainable is not four, and saying so is the point of D2."""
    _endpoint(identity, monkeypatch, TAGS, None)
    fields, reasons = identity.probe_model("http://srv2:11434", "qwen2.5-coder:1.5b")
    assert fields["model_sha256"] == "d7372fd828518a4d"
    assert "model_sha256" not in reasons
    assert fields["template_sha256"] is None
    assert "api/show" in reasons["template_sha256"]


def test_a_null_tokenizer_array_is_refused_rather_than_hashed(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`verbose` off returns null, and `digest(None)` would be a real-looking hash."""
    _endpoint(
        identity,
        monkeypatch,
        TAGS,
        {"template": "t", "model_info": {"tokenizer.ggml.tokens": None}},
    )
    fields, reasons = identity.probe_model("http://srv2:11434", "qwen2.5-coder:1.5b")
    assert fields["vocabulary_sha256"] is None
    assert "verbose" in reasons["vocabulary_sha256"]


def test_a_model_absent_from_the_listing_is_named(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _endpoint(identity, monkeypatch, {"models": []}, SHOW)
    fields, reasons = identity.probe_model("http://srv2:11434", "not-pulled")
    assert fields["model_sha256"] is None
    assert "not-pulled" in reasons["model_sha256"]
    assert fields["template_sha256"] is not None


# --- the two reasons a field is pending -------------------------------------


def test_every_pending_field_says_which_of_the_two_reasons(identity: Any) -> None:
    """The list conflated "not admitted" with "nothing writes it" (#285).

    Complete rather than defaulted: a field that falls through to "the usual" is
    a field nobody decided about, and this is the assertion that stops one
    arriving unexplained.
    """
    unexplained = [f for f in identity.PENDING if f not in identity.PENDING_REASON]
    assert not unexplained, (
        f"{unexplained} are pending for a reason nobody stated. Add them to "
        "PENDING_REASON, or admit them to KEY under #276's rule."
    )
    assert not set(identity.PENDING_REASON) - set(identity.PENDING)


def test_the_four_digests_are_no_longer_awaiting_a_writer(identity: Any) -> None:
    """The acceptance property, read off the module rather than off a PR body."""
    for field in (*identity.MODEL_PROBE_FIELDS, "bar_sha256"):
        assert identity.PENDING_REASON[field] == identity.AWAITING_ADMISSION
    for field in ("quantization", "context_length", "concurrency", "seed"):
        assert identity.PENDING_REASON[field] == identity.AWAITING_PROBE_SET


def test_a_verified_record_demotes_when_a_field_is_admitted(
    identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0027 D8's whole reason for computing the tag on read.

    Six manifests on disk are `verified` against `KEY` as it stands. The moment
    a digest is admitted they must demote **on their own** — a tag stamped into
    a file would go on claiming a fingerprint the run never carried. Proven by
    actually widening the key here rather than by waiting for the day it
    happens: if the six stayed `verified`, the tag would not be reading what it
    claims to read, and that is the failure this case exists to catch.
    """
    record = _manifest()
    assert identity.tag(record) == identity.VERIFIED
    monkeypatch.setattr(identity, "KEY", (*identity.KEY, "bar_sha256"))
    assert identity.tag(record) == identity.BACKFILLED
    assert identity.unfingerprinted(record) == ["bar_sha256"]
    assert identity.tag(dict(record, bar_sha256="beef")) == identity.VERIFIED
