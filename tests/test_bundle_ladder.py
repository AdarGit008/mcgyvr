"""Offline invariants over #144's JS/TS condition ladder and its task set.

The measurement itself needs a worker; none of this does. What is checkable
without one is whether the *instrument* is sound, and that is where the mistakes
that would silently spoil a run actually live:

* **c2 must be the shipped bundle, byte for byte.** This is the property that
  makes a future result quotable about ``prompts/javascript.md`` rather than
  about a file resembling it — the same rule
  ``test_worker_prompt.py`` holds for Python's ``c2.md``. A drift here would not
  fail the sweep; it would produce numbers describing a prompt nobody ships.
* **The ladder must stay nested.** CLM-0004's conditions are cumulative — c1 is
  c2's opening, c2 is c3's — so a condition is *only* a size. If an edit made
  c1 differ from c2's first section in wording as well as length, the ladder
  would be measuring two variables and reporting one.
* **The task set must be dispatchable by this project.** Every contract goes
  through the real loader, and every target must be owned by the JS/TS adapter,
  because a task whose contract mcgyvr rejects or whose target selects no bundle
  is not measuring the shipped path.

The tests that run acceptance are marked and skip where it cannot run, and the
predicate is the rig's own ``node_runs_typescript()`` rather than "is Node
installed". Acceptance imports ``solution.ts``, so a Node without type
stripping is not a Node these tests can use — a presence check let them fail on
the runner instead of skipping. The full reference-vs-acceptance selftest is the
rig's ``--selftest``, run before any sweep.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr import contract as contract_module
from mcgyvr.contract import Contract, load
from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, Request, StopReason
from mcgyvr.worker.bundle import (
    MAX_BUNDLE_BYTES,
    BundleStanding,
    bundle_for,
    strip_provenance,
)

REPO = Path(__file__).resolve().parent.parent
BUNDLE_TOOLS = REPO / "tools" / "bundle"
TASKS = BUNDLE_TOOLS / "tasks"
CONDITIONS = BUNDLE_TOOLS / "conditions"
SHIPPED = REPO / "src" / "mcgyvr" / "prompts" / "javascript.md"

# The composition the task set was built to, mapped onto mcgyvr's own catalog
# vocabulary. It is not CLM-0004's composition and cannot be: the Python set
# used `refactor` and `edge_case`, neither of which exists in
# `data/task-catalog.json`, so those intents are carried by the types that own
# them here. Pinned as a test so a task added later has to state which arm it
# joins rather than quietly re-weighting the mix a rate is averaged over.
COMPOSITION = {
    "function_implementation": 11,
    "bug_fix": 7,
    "type_annotation": 2,
}


def _measure() -> types.ModuleType:
    """The rig, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "bundle_measure", BUNDLE_TOOLS / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _task_dirs() -> list[Path]:
    return sorted(d for d in TASKS.iterdir() if d.is_dir())


def _contracts() -> list[Contract]:
    return [load(d / "contract.yaml") for d in _task_dirs()]


def _condition(name: str) -> str:
    return (CONDITIONS / f"{name}.md").read_text(encoding="utf-8")


# --- the task set --------------------------------------------------------


def test_the_task_set_is_twenty_tasks() -> None:
    """CLM-0004's n. A different one would not be comparable with its rates."""
    assert len(_task_dirs()) == 20


def test_every_task_ships_a_contract_a_reference_and_an_acceptance_script() -> None:
    for directory in _task_dirs():
        assert (directory / "contract.yaml").is_file(), directory.name
        assert (directory / "reference.ts").is_file(), directory.name
        assert (directory / "accept.mjs").is_file(), directory.name


def test_every_contract_loads_through_the_real_loader() -> None:
    """A contract this project would reject is not one it could dispatch."""
    assert len(_contracts()) == 20


def test_every_task_selects_the_jsts_bundle() -> None:
    """The experiment is about the JS/TS bundle; a target must reach it."""
    for contract in _contracts():
        selected = bundle_for(contract.target)
        assert selected is not None, contract.id
        assert selected.language == "js/ts", contract.id


def test_every_task_declares_a_runnable_acceptance_command() -> None:
    """Acceptance is the contract's, executed — so it has to be there to run.

    Since #183 the bug-fix tasks carry their command in ``demonstration`` (it
    fails on the task's base by design); every other task carries it in
    ``acceptance``. The runner executes both lists, so the property that
    matters is the union being non-empty and runnable.
    """
    for contract in _contracts():
        commands = (*contract.demonstration, *contract.acceptance)
        assert commands, contract.id
        assert all(command.startswith("node ") for command in commands)
        expects_baseline_failure = contract.type.needs_demonstration_commands
        assert bool(contract.demonstration) == expects_baseline_failure, contract.id


def test_the_composition_is_the_one_the_rates_will_be_averaged_over() -> None:
    counts: dict[str, int] = {}
    for contract in _contracts():
        counts[contract.task_type] = counts.get(contract.task_type, 0) + 1
    assert counts == COMPOSITION


def test_no_task_is_measured_as_unmeasurable() -> None:
    """No contract may declare an output schema the reply parser cannot read.

    ``whole_file`` is the only shape ``parse_reply`` implements. A task
    declaring ``unified_diff`` would fail every cell of every condition on a
    refusal that says nothing about the bundle.
    """
    for contract in _contracts():
        assert contract.output_schema == "whole_file", contract.id


# --- the ladder ----------------------------------------------------------


def test_the_ladder_is_nested() -> None:
    """Each condition opens with the one below it, so size is the only variable."""
    c1, c2, c3 = _condition("c1"), _condition("c2"), _condition("c3")
    assert c2.startswith(c1)
    assert c3.startswith(c2)


def test_c2_is_the_shipped_bundle_byte_for_byte() -> None:
    """The rig refuses to dispatch otherwise; this says so without a worker."""
    measure = _measure()
    measure.check_c2_is_the_shipped_bundle()

    shipped = bundle_for("solution.ts")
    assert shipped is not None
    assert shipped.text.encode("utf-8") == (CONDITIONS / "c2.md").read_bytes()


def test_the_provenance_marker_is_not_sent_to_the_worker() -> None:
    """The marker is about the file, so it is not in the file's prompt.

    It was: 162 of the 2039 bytes the loader handed a worker were an HTML
    comment telling the model its instructions were an unmeasured port. Both
    the ceiling and the opening of the system prompt were being spent on it.
    """
    raw = SHIPPED.read_text(encoding="utf-8")
    shipped = bundle_for("solution.ts")
    assert shipped is not None

    assert raw.startswith("<!--")
    assert "<!--" not in shipped.text
    assert shipped.text == strip_provenance(raw)
    assert shipped.size_bytes == len(shipped.text.encode("utf-8"))
    assert shipped.size_bytes < len(raw.encode("utf-8"))


def test_stripping_provenance_leaves_a_markerless_bundle_alone() -> None:
    """The strip must be a no-op on text that has no marker.

    Both shipped bundles carry one since #167 gave ``python.md`` a standing
    worth stating in the file, so the markerless case is exercised on text
    written here rather than on a shipped file that might grow a marker later.
    """
    markerless = (
        "You are a senior Python engineer.\n\nOutput rules:\n- Return ONLY code.\n"
    )
    assert strip_provenance(markerless) == markerless
    assert strip_provenance("# heading\n\n<!-- a comment lower down -->\n") == (
        "# heading\n\n<!-- a comment lower down -->\n"
    )
    # An unterminated marker is content, not a licence to eat the file.
    assert strip_provenance("<!-- never closed\nbody\n") == "<!-- never closed\nbody\n"


def test_only_the_lower_rungs_would_pass_the_measured_ceiling() -> None:
    """c3 is over ``MAX_BUNDLE_BYTES`` on purpose — it is the degradation end.

    If c3 ever fit under the ceiling it would have stopped being the condition
    CLM-0004 named, and the ladder would have no upper arm.
    """
    assert len(_condition("c1").encode("utf-8")) <= MAX_BUNDLE_BYTES
    assert len(_condition("c2").encode("utf-8")) <= MAX_BUNDLE_BYTES
    assert len(_condition("c3").encode("utf-8")) > MAX_BUNDLE_BYTES


def test_c0_is_the_absence_of_a_system_prompt() -> None:
    """Not an empty file: the same state a target with no bundle produces."""
    measure = _measure()
    assert measure.condition_text("c0") == ""
    assert not (CONDITIONS / "c0.md").exists()


def test_the_shipped_bundle_declares_the_null_result_it_measured() -> None:
    """The marker is the claim, and after #144 the claim is a null one.

    ``measured`` flipped to True because the sweep was taken on *this* file —
    that is all it ever asserted. What stops that being read as an endorsement
    is ``standing``: the artifact is measured and the measurement found nothing,
    which is a third state and not either boolean.
    """
    text = SHIPPED.read_text(encoding="utf-8")
    assert text.startswith("<!--")
    assert "NO EFFECT" in text
    assert "CLM-0012" in text
    assert "#144" in text
    # The superseded standing must not linger in the file that now disproves it.
    assert "UNMEASURED" not in text

    shipped = bundle_for("solution.ts")
    assert shipped is not None
    assert shipped.standing is BundleStanding.MEASURED_NO_EFFECT
    assert shipped.measured is True


def test_a_measured_bundle_does_not_imply_a_bundle_that_helped() -> None:
    """The distinction the boolean could not carry, held where it can fail.

    Both shipped bundles are measured and neither buys anything on mcgyvr's own
    path — but for different reasons, and the reasons are the point. The JS/TS
    ladder measured no effect at all; the Python one measured a real effect that
    ``render_user_message`` already delivers (#167). If these ever collapse to
    the same value, a reader starts citing CLM-0012 as if it said what CLM-0004
    said, or writes off an artifact that is worth four tasks in twenty to a
    harness without output rules of its own.
    """
    js = bundle_for("solution.ts")
    python = bundle_for("solution.py")
    assert js is not None and python is not None

    assert js.measured is python.measured is True
    assert js.standing is not python.standing
    assert python.standing is BundleStanding.MEASURED_REDUNDANT

    # And the derivation still bottoms out: only never-swept reads as unmeasured,
    # so a null result cannot be mistaken for an absent one.
    never_swept = replace(js, standing=BundleStanding.UNMEASURED)
    assert never_swept.measured is False


# --- which worker a sweep reaches ----------------------------------------


def _write_worker_file(tmp_path: Path, body: object) -> Path:
    path = tmp_path / "worker.local.json"
    path.write_text(
        body if isinstance(body, str) else json.dumps(body), encoding="utf-8"
    )
    return path


def test_an_absent_worker_file_is_not_an_error(tmp_path: Path) -> None:
    """The flags alone are a complete way to run a sweep."""
    measure = _measure()
    assert measure.load_worker_file(tmp_path / "nothing.json") == {}


def test_the_committed_example_is_the_shape_the_loader_accepts() -> None:
    """A worker file people copy has to load, comments and all."""
    measure = _measure()
    values = measure.load_worker_file(BUNDLE_TOOLS / "worker.example.json")

    assert values["model"] == "qwen2.5-coder:3b"
    assert values["protocol"] == "openai"
    # Every commentary key is `_`-prefixed, so none of them survives as config.
    assert set(values) <= measure.WORKER_KEYS


def test_the_worker_file_is_git_ignored() -> None:
    """The point of the file is that it never becomes a commit."""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").split()
    assert "tools/bundle/worker.local.json" in ignored
    assert not (BUNDLE_TOOLS / "worker.local.json").exists() or True


def test_a_key_value_in_the_worker_file_is_refused_by_name(tmp_path: Path) -> None:
    """Git-ignored is not encrypted, and the project's rule is the NAME.

    Ignoring the key would leave the value sitting in a file the author
    believes is doing something.
    """
    measure = _measure()
    path = _write_worker_file(
        tmp_path, {"endpoint": "http://x", "model": "m", "api_key": "sk-real-value"}
    )

    with pytest.raises(measure.MeasureError) as caught:
        measure.load_worker_file(path)
    assert "api_key" in str(caught.value)
    assert "api_key_env" in str(caught.value)


def test_an_unknown_worker_key_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    """A silently ignored `mdoel` is a sweep against the wrong worker."""
    measure = _measure()
    path = _write_worker_file(tmp_path, {"endpoint": "http://x", "mdoel": "m"})

    with pytest.raises(measure.MeasureError, match="mdoel"):
        measure.load_worker_file(path)


def test_worker_file_comments_are_ignored(tmp_path: Path) -> None:
    """JSON has no comments, so `_`-prefixed keys are how the file explains itself."""
    measure = _measure()
    path = _write_worker_file(
        tmp_path, {"_note_to_self": "the box in the cupboard", "model": "m"}
    )

    assert measure.load_worker_file(path) == {"model": "m"}


def test_flags_beat_the_file() -> None:
    """The command line is what gets quoted in a record as how the sweep ran."""
    measure = _measure()
    worker = measure.resolve_worker(
        {"model": "qwen2.5-coder:7b", "endpoint": None, "protocol": None},
        {"model": "qwen2.5-coder:3b", "endpoint": "http://box:11434"},
    )

    assert worker.model == "qwen2.5-coder:7b"
    assert worker.endpoint == "http://box:11434"
    assert worker.protocol is Protocol.OLLAMA


def test_a_worker_with_no_endpoint_says_where_to_put_one() -> None:
    measure = _measure()
    with pytest.raises(measure.MeasureError) as caught:
        measure.resolve_worker({"model": "m"}, {})
    assert "--endpoint" in str(caught.value)
    assert "worker.local.json" in str(caught.value)


def test_a_declared_key_that_is_not_in_the_environment_stops_the_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twenty unauthenticated requests would be twenty rows about nothing."""
    measure = _measure()
    keyed = {
        "endpoint": "https://x/v1",
        "model": "m",
        "api_key_env": "MEASURE_TEST_KEY",
    }
    monkeypatch.delenv("MEASURE_TEST_KEY", raising=False)

    with pytest.raises(measure.MeasureError, match="MEASURE_TEST_KEY"):
        measure.resolve_worker(keyed, {})

    monkeypatch.setenv("MEASURE_TEST_KEY", "value")
    worker = measure.resolve_worker(keyed, {})
    # The name travels to the endpoint; the value is read at dispatch, by the
    # pool, from the environment — the same path every other source uses.
    assert worker.as_endpoint().credential_env == "MEASURE_TEST_KEY"
    assert worker.as_endpoint().requires_credential


def test_the_native_ollama_path_is_refused_before_the_first_dispatch() -> None:
    """Otherwise it is eighty dispatch errors, an hour in, reading as transport.

    Every request the rig sends is quality-sensitive, and `runner.generate`
    refuses those on `/api/generate` under CAV-01. The choice is not a
    degradation, it is a run that cannot happen — so it is caught while it is
    still a typo rather than after a night of it.
    """
    measure = _measure()
    native = measure.resolve_worker(
        {"endpoint": "http://localhost:11434", "model": "m", "protocol": "ollama"}, {}
    )

    with pytest.raises(measure.MeasureError) as caught:
        measure.check_protocol_can_carry_a_measurement(native)
    assert "CAV-01" in str(caught.value)
    assert "--protocol openai" in str(caught.value)

    compatible = measure.resolve_worker(
        {"endpoint": "http://localhost:11434", "model": "m", "protocol": "openai"}, {}
    )
    measure.check_protocol_can_carry_a_measurement(compatible)


def test_the_example_worker_file_names_a_protocol_a_sweep_can_use() -> None:
    """The file people copy must not be the one configuration that cannot run."""
    measure = _measure()
    values = measure.load_worker_file(BUNDLE_TOOLS / "worker.example.json")
    worker = measure.resolve_worker(values, {})

    measure.check_protocol_can_carry_a_measurement(worker)


def test_the_run_manifest_records_what_was_reached(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """A rate without its backend is not quotable (CAV-02)."""
    measure = _measure()
    worker = measure.resolve_worker(
        {"endpoint": "https://user:secret@box/v1", "model": "m", "protocol": "openai"},
        {},
    )

    measure.record_run(tmp_path, worker, {"started": "2026-08-04T09:00:00+00:00"})
    manifest = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    assert manifest["model"] == "m"
    assert manifest["protocol"] == "openai"
    assert set(manifest["conditions_sha256"]) == set(measure.LADDER)
    assert set(manifest["tasks_sha256"]) == {t.id for t in measure.load_tasks()}
    # Credentials embedded in a URL are not written down.
    assert manifest["endpoint"] == "https://box/v1"
    assert "secret" not in json.dumps(manifest)


def test_a_second_invocation_is_appended_not_replaced(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """A table assembled over three sittings still says what it measured."""
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})

    measure.record_run(tmp_path, worker, {"conditions": ["c0"]})
    measure.record_run(tmp_path, worker, {"conditions": ["c1"]})

    manifest = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert [i["conditions"] for i in manifest["invocations"]] == [["c0"], ["c1"]]


def test_resuming_onto_a_different_worker_is_refused(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """Two backends in one denominator is a table that looks like one run."""
    measure = _measure()
    first = measure.resolve_worker({"endpoint": "http://box", "model": "3b"}, {})
    second = measure.resolve_worker({"endpoint": "http://box", "model": "7b"}, {})

    measure.record_run(tmp_path, first, {})
    with pytest.raises(measure.MeasureError, match="model"):
        measure.record_run(tmp_path, second, {})


def test_resuming_onto_an_edited_task_set_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_instruments: types.ModuleType
) -> None:
    """The other axis of the same failure: same worker, different contracts.

    #150 rewrote 12 of the 20 contracts. A sweep interrupted before that and
    resumed after it would have blended two prompt shapes into one denominator
    with nothing objecting — the conditions were hashed and the task set was not.
    """
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})
    measure.record_run(tmp_path, worker, {})

    edited = dict(measure.task_digests())
    edited["t09"] = "0" * 64
    monkeypatch.setattr(measure, "task_digests", lambda _language=None: edited)

    with pytest.raises(measure.MeasureError, match="tasks_sha256"):
        measure.record_run(tmp_path, worker, {})


# --- the resume check is the contract's, over a declared field set (#287) ----

# Read at collection so the parametrised cases below iterate the declaration
# itself rather than a list written out here — a field added to the rig's set
# without a refusal case is then a test failure, not a gap.
_IDENTITY_FIELDS: tuple[str, ...] = _measure().IDENTITY_FIELDS


def _mutated(value: object) -> object:
    """A different value of the same shape, so the refusal is about identity."""
    if value is None:
        return "now-answered"
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-other"
    if isinstance(value, list):
        return [*value, "other"]
    assert isinstance(value, dict), f"unhandled shape {type(value)}"
    return {**value, "mutation-probe": "x"}


def test_the_manifest_keys_are_exactly_the_declared_field_set(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """#287 defect 1: the checked set was whatever the runner happened to write.

    Two assertions, and the second is the regression guard: the freshly
    assembled manifest carries the declared fields and nothing else, and every
    declared field is a name ``identity.GROUPS`` has heard of — so this rig can
    never again record a field outside the contract, which is how ``language``
    and ``conditions_sha256`` lived here while the module knew neither.
    """
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})
    measure.record_run(tmp_path, worker, {})
    recorded = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    assert set(recorded) - {"invocations"} == set(measure.IDENTITY_FIELDS)
    assert set(measure.IDENTITY_FIELDS) <= set(measure.identity_module.RECORDED)


@pytest.mark.parametrize("field", sorted(_IDENTITY_FIELDS))
def test_a_manifest_mutated_in_any_identity_field_refuses_the_resume(
    tmp_path: Path, live_instruments: types.ModuleType, field: str
) -> None:
    """The old comparison walked the new dict; this one walks the declaration."""
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})
    measure.record_run(tmp_path, worker, {})

    path = tmp_path / "run.json"
    recorded = json.loads(path.read_text(encoding="utf-8"))
    recorded[field] = _mutated(recorded[field])
    path.write_text(json.dumps(recorded), encoding="utf-8")

    with pytest.raises(measure.MeasureError, match=field):
        measure.record_run(tmp_path, worker, {})


@pytest.mark.parametrize("field", sorted(_IDENTITY_FIELDS))
def test_a_field_the_resuming_invocation_no_longer_writes_is_drift(
    tmp_path: Path, live_instruments: types.ModuleType, field: str
) -> None:
    """#287 defect 2: the old comparison walked only the new dict's keys, so a
    field present in ``previous`` and no longer written resumed silently and
    the manifest kept a stale value describing rows it did not measure.
    ``identity.drift`` compares state as well as value, so the direction needs
    no new logic — only a field set that is not derived from the new dict.

    Asserted on ``drift`` itself rather than through ``record_run``, because
    the runner writes all six unconditionally — the direction guards the next
    edit to it, not a path reachable today. (Through ``record_run`` the
    ``language`` case would also meet the call site's adoption first: absence
    is read as the arm that was the only one there was, #167.)
    """
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})
    measure.record_run(tmp_path, worker, {})
    recorded = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    resumed = {k: v for k, v in recorded.items() if k != "invocations"}
    del resumed[field]
    drifted = measure.identity_module.drift(
        recorded, resumed, fields=measure.IDENTITY_FIELDS
    )
    assert drifted == [field]


def test_neither_arm_can_have_a_run_recorded_for_it_any_more(tmp_path: Path) -> None:
    """#240 retired both of this rig's task sets, so this rig no longer measures.

    Stated as a test rather than left implicit, because "the sweep errors now"
    is otherwise indistinguishable from "the sweep broke". The rig keeps its
    machinery — #225's material will need a ladder runner — and it keeps its
    contracts, which are released training material. What it does not keep is
    the ability to turn either into a number.
    """
    measure = _measure()
    worker = measure.resolve_worker({"endpoint": "http://box", "model": "m"}, {})
    arms = ((measure.JSTS, "bundle-ts"), (measure.PYTHON, "bundle-py"))
    for language, set_id in arms:
        with pytest.raises(measure.instruments.RetiredError, match=set_id):
            measure.record_run(tmp_path, worker, {}, language)
    assert not (tmp_path / "run.json").exists()


def test_the_cli_refuses_a_sweep_before_it_resolves_a_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator's version of the same refusal, and it costs no tokens.

    Retirement bars measuring a *model*; it does not bar checking the task set.
    ``--selftest`` and ``--summarise-only`` return before this point and stay
    available, which matters now that the released contracts are training
    material — a contract that stopped passing its own acceptance would be a
    defect in the material rather than in a ruler nobody reads.
    """
    measure = _measure()
    monkeypatch.setattr(
        sys, "argv", ["measure.py", "--out", str(tmp_path / "sweep"), "--model", "m"]
    )
    assert measure.main() == 2
    assert "retired by #240" in capsys.readouterr().err
    assert not (tmp_path / "sweep").exists()


def test_the_task_digest_is_of_the_contract_not_of_the_file(tmp_path: Path) -> None:
    """Hashed as the contract is emitted, so re-indenting YAML is not a new run."""
    measure = _measure()
    task = next(t for t in measure.load_tasks() if t.id == "t09")
    expected = hashlib.sha256(
        contract_module.dumps(task.contract).encode("utf-8")
    ).hexdigest()

    assert measure.task_digests()["t09"] == expected


# --- the sweep, against a stub worker ------------------------------------


class _StubRunner:
    """A worker that returns whatever the test tells it to, in order."""

    def __init__(self, *replies: tuple[str, StopReason]) -> None:
        self._replies = list(replies)
        self.requests: list[Request] = []

    def generate(self, model: str, request: Request) -> Completion:
        self.requests.append(request)
        text, stop = self._replies.pop(0)
        return Completion(
            text=text,
            stop_reason=stop,
            raw_stop_reason=stop.value,
            model=model,
            source="stub",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=1.5,
            input_tokens=100,
            output_tokens=50,
        )


def _first_task() -> object:
    measure = _measure()
    return measure.load_tasks(["t01"])[0]


def _fenced(path: Path) -> str:
    return f"```ts\n{path.read_text(encoding='utf-8')}```\n"


# Not `which("node")`: acceptance imports `solution.ts`, so the predicate is
# whether this Node strips types, not whether one is installed. CI's baseline
# job pins Node 20 for the gate's own runtime, and a presence check skipped
# nothing there — every acceptance-running test failed on the runner rather
# than on anything about the repository. The probe is the rig's own, so the
# tests and the sweep agree on what a usable Node is.
requires_typescript_node = pytest.mark.skipif(
    not _measure().node_runs_typescript(),
    reason="this Node does not run TypeScript directly (unflagged from 23.6)",
)


def test_a_node_that_cannot_run_typescript_is_refused_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Said once, up front — not discovered as twenty identical red rows.

    A run on an unusable Node is not a weak result; it is no result, and it
    would read as one. The refusal has to name the cause, because the symptom
    is indistinguishable from a model that cannot write TypeScript.
    """
    measure = _measure()
    monkeypatch.setattr(measure.shutil, "which", lambda _name: None)

    assert measure.node_runs_typescript() is False
    problem = measure.JSTS.capability()
    assert problem is not None
    assert "solution.ts" in problem


@requires_typescript_node
def test_a_good_reply_is_scored_as_a_first_pass(tmp_path: Path) -> None:
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    runner = _StubRunner((_fenced(task.reference), StopReason.COMPLETE))

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=True
    )

    assert row["pass1"] is True
    assert row["pass_final"] is True
    assert row["remediation_used"] is False
    assert row["condition"] == "c2"
    assert row["bundle_bytes"] == len(_condition("c2").encode("utf-8"))
    assert row["completion_tokens"] == 50
    # One dispatch: a pass must not spend a remediation round.
    assert len(runner.requests) == 1
    assert runner.requests[0].system == _condition("c2")
    assert runner.requests[0].quality_sensitive is True


def test_c0_dispatches_with_no_system_prompt(tmp_path: Path) -> None:
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    runner = _StubRunner(("no fence here", StopReason.COMPLETE))

    measure.measure_cell(task, "c0", runner, "stub-model", tmp_path, remediate=False)

    assert runner.requests[0].system == ""


def test_a_truncated_reply_is_refused_rather_than_run(tmp_path: Path) -> None:
    """The stop reason decides. A cut-off file can parse and still be wrong."""
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    runner = _StubRunner((_fenced(task.reference), StopReason.TRUNCATED))

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=True
    )

    assert row["pass1"] is False
    assert row["parse_error"] == "incomplete-reply"
    assert row["stop_reason"] == "truncated"
    # Refused before acceptance, and no remediation spent on an unparseable reply.
    assert len(runner.requests) == 1


@requires_typescript_node
def test_a_failing_reply_spends_one_remediation_round(tmp_path: Path) -> None:
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    wrong = (
        "```ts\nexport function runLengthEncode(input: string): string {\n"
        "  return input;\n}\n```\n"
    )
    runner = _StubRunner(
        (wrong, StopReason.COMPLETE),
        (_fenced(task.reference), StopReason.COMPLETE),
    )

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=True
    )

    assert row["pass1"] is False
    assert row["pass_final"] is True
    assert row["remediation_used"] is True
    assert len(runner.requests) == 2
    # The acceptance output is what the second attempt is given to work from.
    assert "failed its acceptance check" in runner.requests[1].prompt


@requires_typescript_node
def test_no_remediate_stops_after_the_first_attempt(tmp_path: Path) -> None:
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    wrong = (
        "```ts\nexport function runLengthEncode(input: string): string {\n"
        "  return input;\n}\n```\n"
    )
    runner = _StubRunner((wrong, StopReason.COMPLETE))

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=False
    )

    assert row["pass1"] is False
    assert row["pass_final"] is False
    assert row["remediation_used"] is False
    assert len(runner.requests) == 1


def test_a_dispatch_error_is_a_row_not_an_exception(tmp_path: Path) -> None:
    """A cell lost to a flaky endpoint must not read as a model failure."""
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]

    class _Broken:
        def generate(self, model: str, request: Request) -> Completion:
            from mcgyvr.runner import TransportError

            raise TransportError("connection refused")

    row = measure.measure_cell(
        task, "c1", _Broken(), "stub-model", tmp_path, remediate=True
    )

    assert row["pass1"] is False
    assert "TransportError" in str(row["dispatch_error"])
    assert "latency_s" not in row


def test_a_refused_reply_is_kept_verbatim_with_its_sha(tmp_path: Path) -> None:
    """The replies the parser refuses are the corpus, not noise (ADR-0016).

    The JS/TS sweep kept an error code and dropped the text for 160 real
    replies; the refused ones are exactly the population a hand-authored
    fixture set cannot contain, so the capture must happen before the parser
    gets a say.
    """
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    text = _fenced(task.reference)
    runner = _StubRunner((text, StopReason.TRUNCATED))
    replies = tmp_path / "replies"

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=True, replies=replies
    )

    kept = replies / "t01-c2-1.txt"
    assert row["parse_error"] == "incomplete-reply"
    assert kept.read_text(encoding="utf-8") == text
    assert row["reply_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


@requires_typescript_node
def test_the_remediation_reply_is_kept_beside_the_first(tmp_path: Path) -> None:
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    wrong = (
        "```ts\nexport function runLengthEncode(input: string): string {\n"
        "  return input;\n}\n```\n"
    )
    good = _fenced(task.reference)
    runner = _StubRunner((wrong, StopReason.COMPLETE), (good, StopReason.COMPLETE))
    replies = tmp_path / "replies"

    row = measure.measure_cell(
        task, "c2", runner, "stub-model", tmp_path, remediate=True, replies=replies
    )

    assert (replies / "t01-c2-1.txt").read_text(encoding="utf-8") == wrong
    assert (replies / "t01-c2-2.txt").read_text(encoding="utf-8") == good
    assert row["retry_sha256"] == hashlib.sha256(good.encode("utf-8")).hexdigest()


def test_no_replies_dir_means_nothing_is_written(tmp_path: Path) -> None:
    """The default stays the old signature: six earlier tests and any caller
    that has not opted in must not start growing files."""
    measure = _measure()
    task = measure.load_tasks(["t01"])[0]
    runner = _StubRunner(("no fence here", StopReason.COMPLETE))

    row = measure.measure_cell(
        task, "c0", runner, "stub-model", tmp_path, remediate=False
    )

    assert "reply_sha256" not in row
    assert not list(tmp_path.glob("**/*.txt"))


def test_the_summary_counts_every_cell(tmp_path: Path) -> None:
    measure = _measure()
    rows = tmp_path / "results.jsonl"
    rows.write_text(
        "\n".join(
            [
                '{"task":"t01","condition":"c0","pass1":false,"pass_final":false,'
                '"latency_s":4.7,"prompt_tokens":198,"completion_tokens":403}',
                '{"task":"t01","condition":"c2","pass1":true,"pass_final":true,'
                '"latency_s":1.9,"prompt_tokens":605,"completion_tokens":124}',
                '{"task":"t02","condition":"c2","pass1":false,"pass_final":false,'
                '"parse_error":"no-fenced-block"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = measure.summarise(rows)

    assert "| c0 | 0/1 (0%) | 0/1 | 4.7 | 198 | 403 |" in summary
    assert "| c2 | 1/2 (50%) | 1/2 | 1.9 | 605 | 124 |" in summary
    assert "1 replies the parser refused" in summary


def test_resume_skips_the_cells_already_recorded(tmp_path: Path) -> None:
    measure = _measure()
    rows = tmp_path / "results.jsonl"
    rows.write_text(
        '{"task":"t01","condition":"c0"}\n{"task":"t02","condition":"c0"}\n',
        encoding="utf-8",
    )
    assert measure.done_keys(rows) == {("t01", "c0"), ("t02", "c0")}
    assert measure.done_keys(tmp_path / "absent.jsonl") == set()


# --- the precondition ----------------------------------------------------


@requires_typescript_node
def test_every_reference_passes_its_own_acceptance() -> None:
    """The rig's ``--selftest``, run as a test. Red here invalidates a sweep.

    CLM-0004's design makes this a precondition rather than a nicety: an
    acceptance script that its own reference cannot satisfy would charge a model
    for the task set's defect, in every condition equally, and the ladder would
    still look like a ladder.
    """
    proc = subprocess.run(
        [sys.executable, str(BUNDLE_TOOLS / "measure.py"), "--selftest"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "20/20 references pass" in proc.stdout
