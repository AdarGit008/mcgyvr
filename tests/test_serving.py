"""The serving survey: backends that do not know each other, and one orchestrator.

The properties here are structural rather than numerical. What can go wrong in
this tree is not a wrong figure — it is a backend reaching across at another, an
orchestrator clearing away the server it was about to measure, or a family
verdict that reads as complete while a member is missing. Each of those happened
in the single-module predecessor, and each is a test below.
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
SERVING = REPO / "tools" / "bench" / "serving"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner() -> Any:
    return _by_path("serving_run", SERVING / "run.py")


@pytest.fixture(scope="module")
def contract(runner: Any) -> Any:
    return runner.contract


BACKENDS = sorted(p.stem for p in (SERVING / "backends").glob("*.py"))

#: What every backend must expose for the orchestrator to drive it.
INTERFACE = (
    "NAME",
    "PORT",
    "probe",
    "inventory",
    "release",
    "claim",
    "describe",
    "readings",
)


def test_there_is_more_than_one_backend_to_keep_apart() -> None:
    """The isolation tests below are vacuous with a single backend."""
    assert len(BACKENDS) >= 2, BACKENDS


@pytest.mark.parametrize("name", BACKENDS)
def test_every_backend_implements_the_whole_interface(contract: Any, name: str) -> None:
    backend = contract.load_backend(name)
    missing = [item for item in INTERFACE if not hasattr(backend, item)]
    assert not missing, f"{name} is missing {missing}"


@pytest.mark.parametrize("name", BACKENDS)
def test_a_backend_never_names_another_backend(name: str) -> None:
    """The rule the whole structure rests on, enforced rather than trusted.

    A backend knows how to stop being on the card and how to get onto it. Who
    else wants the card is the orchestrator's decision — and the bug this
    prevents was real: an unconditional cleanup stopped one engine immediately
    before measuring it, then recorded it as unreachable.

    Checked against the OTHER backends' names, so a third engine is covered the
    day its file lands, with no edit here.
    """
    source = (SERVING / "backends" / f"{name}.py").read_text(encoding="utf-8").lower()
    for other in BACKENDS:
        if other == name:
            continue
        assert other not in source, (
            f"backends/{name}.py names {other!r}. Cross-engine decisions belong "
            "to run.py: a backend implements release() and claim() and knows "
            "nothing about who else wants the card."
        )


@pytest.mark.parametrize("name", BACKENDS)
def test_a_backend_loads_without_a_sibling_priming_the_cache(name: str) -> None:
    """Each must stand alone.

    One did not: it referenced `importlib` it had never imported, and passed
    only because a sibling loaded first had already filled the shared contract
    slot, so the early return skipped the broken line.
    """
    for slot in [f"serving_backend_{b}" for b in BACKENDS] + ["serving_contract"]:
        sys.modules.pop(slot, None)
    module = _by_path(f"solo_{name}", SERVING / "backends" / f"{name}.py")
    assert name == module.NAME
    assert module.contract is not None


def test_all_backends_share_one_contract(contract: Any) -> None:
    """Two copies would mean two ramps and two definitions of "clean"."""
    loaded = [contract.load_backend(name) for name in BACKENDS]
    assert len({id(backend.contract) for backend in loaded}) == 1


# --- the orchestrator -------------------------------------------------------


class _Backend:
    """A backend that records what was asked of it and touches nothing."""

    def __init__(self, name: str, port: int, models: list[str]) -> None:
        self.NAME = name
        self.PORT = port
        self._models = models
        self.released = 0
        self.claimed: list[str] = []

    def probe(self, host: str) -> str:
        return f"http://{host}:{self.PORT}"

    def inventory(self, host: str, base: str) -> list[str]:
        return self._models

    def readings(self, host: str) -> dict[str, Any]:
        return {}

    def release(self, host: str) -> dict[str, Any]:
        self.released += 1
        return {"backend": self.NAME, "released": True}

    digest: str | None = None

    def claim(
        self,
        host: str,
        base: str,
        model: str,
        serve: Any = None,
        expect: Any = None,
        coresident_with: Any = None,
    ) -> dict[str, Any]:
        # Accepted because the real backends do: a co-residency entry names its
        # neighbour here, and a stub that refused the argument made the survey
        # report `launch_failed` for a claim that never had a chance to run.
        self.coresident_with = coresident_with
        self.claimed.append(model)
        return {
            "backend": self.NAME,
            "model": model,
            "verified": True,
            "checks": {"weights": {"weights_sha256": self.digest}},
        }

    def describe(
        self, host: str, base: str, model: str, serve: Any = None
    ) -> dict[str, Any]:
        # `serve` is accepted because D1 made the launched width part of what a
        # backend can be asked to describe: one engine states it on no endpoint,
        # so there the only available value is the dispatched one.
        return {
            "backend": self.NAME,
            "capture": {"model_sha256": f"{self.NAME}-sha"},
            "declared_slots": {"value": None, "provenance": "dispatched"},
        }


def _stub(
    runner: Any, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> dict[str, Any]:
    table = {
        "alpha": _Backend("alpha", 11434, ["m"]),
        "beta": _Backend("beta", 8000, ["m"]),
    }
    table.update(kwargs)
    monkeypatch.setattr(runner.contract, "load_backend", lambda name: table[name])
    monkeypatch.setattr(runner.contract, "snapshot", lambda host: {"host": host})
    monkeypatch.setattr(
        runner.contract,
        "ramp",
        lambda *a, **k: {
            "saturation": {
                "n": 4,
                "refused": None,
                "ramp_tokens": 475,
                "plateau_fraction": 0.92,
            },
            "levels": [],
        },
    )
    return table


def test_the_engine_under_test_is_never_the_one_released(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug this whole structure exists to prevent.

    Measuring one engine must make every OTHER engine yield the card, and must
    never stop the engine about to be measured. The predecessor stopped vLLM
    unconditionally and then ramped a server that was no longer running.
    """
    table = _stub(runner, monkeypatch)
    runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [{"label": "a", "backend": "alpha", "id": "m"}],
        }
    )
    assert table["alpha"].released == 0, "the engine under test was told to yield"
    assert table["beta"].released == 1, "the other engine was not asked to yield"
    assert table["alpha"].claimed == ["m"]


def test_discovery_happens_before_anything_is_cleared(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A survey that clears first can only measure whichever engine it reaches
    first — which is why both engines are probed before the first release."""
    order: list[str] = []
    table = _stub(runner, monkeypatch)

    def trace(backend: Any, verb: str, original: Any) -> Any:
        def wrapped(host: str) -> Any:
            order.append(f"{verb}:{backend.NAME}")
            return original(host)

        return wrapped

    for backend in table.values():
        backend.probe = trace(backend, "probe", backend.probe)
        backend.release = trace(backend, "release", backend.release)
    runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [{"label": "a", "backend": "alpha", "id": "m"}],
        }
    )
    first_release = next(
        i for i, step in enumerate(order) if step.startswith("release")
    )
    probes = [i for i, step in enumerate(order) if step.startswith("probe")]
    assert probes and max(probes) < first_release, order


def test_a_refused_claim_is_recorded_and_never_measured(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal must leave evidence, not a row of nulls that reads like data."""
    table = _stub(runner, monkeypatch)

    def refuse(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise runner.contract.NotCleanError("card would not clear")

    monkeypatch.setattr(table["alpha"], "claim", refuse)
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "a", "backend": "alpha", "id": "m", "family": "f"},
                {"label": "b", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    row = result["hosts"]["h"]["measured"]["a"]
    assert row["verified"] is False
    assert "card would not clear" in row["refused"]
    assert result["refusals"][0]["label"] == "a"
    assert "concurrency" not in row


def test_a_family_verdict_states_its_denominator(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Identical across the ones that turned up" is not a finding.

    A family with a refused member has a hole, and the verdict has to carry it
    or a partial comparison reads as a complete one.
    """
    table = _stub(runner, monkeypatch)

    def refuse(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise runner.contract.NotCleanError("nope")

    monkeypatch.setattr(table["beta"], "claim", refuse)
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "a", "backend": "alpha", "id": "m", "family": "f"},
                {"label": "b", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    family = result["families"]["f"]
    assert family["denominator"] == "1 of 2"
    assert family["refused"] == [{"host": "h", "label": "b"}]


def test_a_declared_family_the_digests_refute_is_recorded_as_refuted(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The config claims; the measurement is allowed to disagree in writing."""
    table = _stub(runner, monkeypatch)
    table["alpha"].digest = "aaa"
    table["beta"].digest = "bbb"
    monkeypatch.setattr(
        table["alpha"],
        "describe",
        lambda *a, **k: {"capture": {"quantization": "Q4_K_M"}},
    )
    monkeypatch.setattr(
        table["beta"],
        "describe",
        lambda *a, **k: {"capture": {"quantization": "auto_awq"}},
    )
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "a", "backend": "alpha", "id": "m", "family": "f"},
                {"label": "b", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    # Both stubs report the SAME KIND of digest with different values, so this
    # is the strong refutation — the numbers are directly comparable and they
    # disagree — rather than the weaker cross-kind one.
    family = result["families"]["f"]
    assert family["verdict"].startswith("REFUTED: same checkpoint-tensor digest")
    assert family["digests_comparable"] is True
    assert family["denominator"] == "2 of 2"


def test_two_serve_configs_of_one_model_are_two_rows(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`label` is the key, so a batch-width change is a separate instrument."""
    _stub(runner, monkeypatch)
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "s8", "backend": "beta", "id": "m", "serve": {"n": 8}},
                {"label": "s16", "backend": "beta", "id": "m", "serve": {"n": 16}},
            ],
        }
    )
    assert sorted(result["hosts"]["h"]["measured"]) == ["s16", "s8"]


def test_a_saturation_point_that_misses_its_expectation_is_flagged(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`expect` is the positive control: a miss is recorded, not smoothed over."""
    _stub(runner, monkeypatch)
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {"concurrency": True},
            "models": [
                {
                    "label": "a",
                    "backend": "alpha",
                    "id": "m",
                    "concurrency": {"measure": True, "expect": 2},
                }
            ],
        }
    )
    measured = result["hosts"]["h"]["measured"]["a"]["concurrency"]
    assert measured["saturation"]["n"] == 4
    assert measured["expected"] == 2
    assert measured["matches_expected"] is False


def test_the_survey_ramp_names_the_host_its_levels_are_read_on(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#327: the per-level card and load are read over ssh to the rig, and
    ``contract.ramp`` only knows which rig if the survey tells it. A ramp
    called without ``host`` writes every level's state as null with the
    command it never ran -- a silent loss on the one runner a config reaches.
    """
    _stub(runner, monkeypatch)
    calls: list[dict[str, Any]] = []

    def ramp(
        base: str, model: str, levels: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        calls.append({"base": base, "levels": levels, **kwargs})
        return {"saturation": {"n": 4, "refused": None}, "levels": []}

    monkeypatch.setattr(runner.contract, "ramp", ramp)
    runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "collect": {"concurrency": True},
            "models": [
                {
                    "label": "a",
                    "backend": "alpha",
                    "id": "m",
                    "concurrency": {"measure": True, "levels": [1, 2]},
                }
            ],
        }
    )
    assert calls and calls[0].get("host") == "h", (
        f"run.py called contract.ramp with {calls}; without host= the level "
        "reader has no rig to ask"
    )
    assert calls[0]["levels"] == (1, 2)


# --- the shared pieces ------------------------------------------------------


def test_the_width_is_recovered_where_the_server_batches(contract: Any) -> None:
    """Two configured values on one engine, and a decline on the other.

    Real measurements. The vLLM servers were launched `--max-num-seqs 8` and
    `--max-num-seqs 16` and the throughput plateau returns exactly those — two
    DIFFERENT values on the same engine, which is what makes this a measurement
    of the flag rather than a number that happened to match once.

    Two earlier rules were wrong in opposite directions and both are pinned
    here. Reading the plateau alone reported 6 for a 2-slot ollama host.
    Requiring the latency plateau to agree fixed that and then threw away the
    correct 16, because latency does not stay flat until queueing starts: at
    n=12 of 16 slots it had already risen 25% with every request still fitting.
    """

    def rows(triples: list[tuple[int, float, float]]) -> list[dict[str, Any]]:
        # A level is clean when nothing errored AND every reply that arrived
        # was countable — `counted == ok`. Partial counting is a drop, because
        # summing only the counted tokens over the wall of ALL of them reports a
        # fraction of the true throughput as if it were the whole thing.
        return [
            {
                "n": n,
                "tokens_per_s": t,
                "latency_mean_s": lat,
                "errors": 0,
                "ok": n,
                "counted": n,
            }
            for n, t, lat in triples
        ]

    vllm8 = rows(
        [
            (1, 42.6, 3.002),
            (2, 27.5, 9.291),
            (3, 40.7, 9.405),
            (4, 54.3, 9.403),
            (6, 80.7, 9.502),
            (8, 106.3, 9.615),
            (12, 81.3, 12.695),
            (16, 106.9, 14.396),
            (24, 107.2, 19.154),
        ]
    )
    vllm16 = rows(
        [
            (1, 42.6, 3.005),
            (2, 27.4, 9.326),
            (3, 40.9, 9.369),
            (4, 54.3, 9.405),
            (6, 80.8, 9.482),
            (8, 106.3, 9.62),
            (12, 127.7, 12.01),
            (16, 167.7, 12.196),
            (24, 140.2, 15.584),
        ]
    )
    ollama = rows(
        [
            (1, 98.9, 1.293),
            (2, 147.6, 1.729),
            (3, 140.9, 2.070),
            (4, 160.1, 2.473),
            (6, 165.0, 3.211),
            (8, 166.4, 3.992),
            (12, 168.8, 5.511),
            (16, 168.3, 7.097),
            (24, 168.4, 10.287),
        ]
    )

    assert contract.saturation(vllm8)["n"] == 8
    assert contract.saturation(vllm16)["n"] == 16

    # D1: ollama's saturation point is REPORTED, not suppressed. The old rule
    # returned None here because a 1.71x rise fell under BATCHING_SPEEDUP=2.0 —
    # which was suppressing a real reading in order to stop it being mistaken
    # for a slot count. The split makes the suppression unnecessary: this is
    # where ollama's throughput stops rising, and it is NOT its slot count.
    # **D2 moves this reading, and that is the point.** At the former inline
    # 0.95 this curve read 6; at PLATEAU_FRACTION = 0.92 it reads 4, because
    # the curve is still creeping upward by a percent or two per level and 0.95
    # placed the saturation point later than the hardware reached it. Neither
    # number was ever this engine's slot count — it was configured 2 — which is
    # exactly why D1 stopped calling it one.
    assert contract.saturation(ollama)["n"] == 4
    assert contract.saturation(ollama)["refused"] is None
    assert contract.readings(ollama)["throughput_plateau_n"] == 4

    # Every value carries the conditions that define it — a saturation point at
    # one token budget is not comparable with one at another.
    assert contract.saturation(vllm16)["ramp_tokens"] == contract.RAMP_TOKENS
    assert contract.saturation(vllm16)["plateau_fraction"] == contract.PLATEAU_FRACTION

    # `batches` is retired: it claimed to say which of two different quantities
    # to believe.
    assert "batches" not in contract.readings(vllm16)

    # WHY the agreement rule was wrong: on a 16-slot server the two plateaus
    # differ by design, because a bigger batch is slower per request.
    assert contract.readings(vllm16)["latency_plateau_n"] == 8


def test_the_curve_reads_the_same_in_any_order_it_was_run(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#327. ``ramp()`` took ``rows[0]`` as the n=1 baseline and the plateau
    scans returned the first row in list order, so one synthetic curve that
    saturates at 4 read ``saturation_n`` 4 offered ascending and 24 offered
    descending. The readers now see the rows sorted by ``n`` once, repeats
    kept in the order they ran; the order offered is a condition on the row,
    not a term in the reading.
    """
    throughput = {1: 100.0, 2: 200.0, 3: 300.0, 4: 400.0}

    def level(_base: str, _model: str, n: int, reader: Any = None) -> dict[str, Any]:
        return {
            "n": n,
            "wall_s": 1.0,
            "ok": n,
            "counted": n,
            "errors": 0,
            "error_kinds": [],
            "completion_tokens_total": 475 * n,
            "tokens_per_s": throughput.get(n, 400.0),
            "latency_mean_s": 1.0 if n <= 4 else n / 4,
            "latency_max_s": 1.0,
            "card": {},
            "ambient": {},
        }

    monkeypatch.setattr(contract, "_level", level, raising=True)
    read = ("saturation", "readings", "speedup_vs_n1", "repeat_spread")

    def run(**kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = contract.ramp("x", "m", reader=lambda: None, **kwargs)
        return result

    ascending = run()
    assert ascending["saturation"]["n"] == 4, "the synthetic curve saturates at 4"
    assert ascending["levels_run"] == list(contract.RAMP_LEVELS)
    for kwargs in ({"order": "descending"}, {"order": "shuffled", "seed": 7}):
        other = run(**kwargs)
        for key in read:
            assert other[key] == ascending[key], (
                f"{key} reads {other[key]!r} offered {kwargs}, "
                f"{ascending[key]!r} offered ascending: the order the levels "
                "ran in reached the reading"
            )
        assert [row["n"] for row in other["levels"]] == sorted(contract.RAMP_LEVELS)
        assert other["levels_run"] != ascending["levels_run"]
    assert run(order="descending")["levels_run"] == sorted(
        contract.RAMP_LEVELS, reverse=True
    )
    once, twice = run(order="shuffled", seed=7), run(order="shuffled", seed=7)
    assert once["levels_run"] == twice["levels_run"], "seed=7 is one sequence"
    assert once["level_seed"] == 7 and once["level_order"] == "shuffled"


def test_a_base_url_ending_in_v1_is_not_doubled(contract: Any) -> None:
    assert contract.url("https://h/v1", "/v1/models") == "https://h/v1/models"
    assert contract.url("http://h:11434", "/api/tags") == "http://h:11434/api/tags"


def test_the_shipped_config_is_valid_and_keys_are_unique() -> None:
    """Labels are the key; two entries sharing one would overwrite each other."""
    config = json.loads(
        (SERVING / "configs" / "srv-full.json").read_text(encoding="utf-8")
    )
    labels = [entry["label"] for entry in config["models"]]
    assert len(labels) == len(set(labels)), labels
    for entry in config["models"]:
        assert entry["backend"] in BACKENDS, entry


# --- the weights pin --------------------------------------------------------


def test_a_cross_backend_family_is_not_decided_on_incomparable_digests(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One backend states a manifest digest; another hashes checkpoint tensors.

    They describe the same weights with different numbers, so comparing them
    would refute every family that is in fact the same model. A cross-backend
    family is decided on what IS comparable — the tokenizer and the quantization
    each engine reports — and the result says so.
    """
    table = _stub(runner, monkeypatch)
    # Two DIFFERENT KINDS of digest: one backend reports a manifest digest in
    # its attempt trail, the other a checkpoint-tensor digest in its checks.
    monkeypatch.setattr(
        table["alpha"],
        "claim",
        lambda *a, **k: {
            "verified": True,
            "attempts": [{"model_sha256": "manifest-digest"}],
        },
    )
    table["beta"].digest = "tensor-digest"
    monkeypatch.setattr(
        table["alpha"],
        "describe",
        lambda *a, **k: {"capture": {"quantization": "Q4_K_M"}},
    )
    monkeypatch.setattr(
        table["beta"],
        "describe",
        lambda *a, **k: {"capture": {"quantization": "auto_awq"}},
    )
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "a", "backend": "alpha", "id": "m", "family": "f"},
                {"label": "b", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    family = result["families"]["f"]
    assert family["digests_comparable"] is False
    assert family["verdict"].startswith("REFUTED as identical")
    assert "Q4_K_M" in family["verdict"] and "auto_awq" in family["verdict"]


def test_two_entries_on_one_backend_are_decided_on_their_digests(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Within a backend the digests ARE the same kind of thing."""
    table = _stub(runner, monkeypatch)
    table["beta"].digest = "same"
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "s8", "backend": "beta", "id": "m", "family": "f"},
                {"label": "s16", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    family = result["families"]["f"]
    assert family["digests_comparable"] is True
    assert family["verdict"].startswith("identical checkpoint-tensor digest")


def test_the_shipped_config_pins_each_backend_with_its_own_field() -> None:
    """A pin names the digest the backend actually computes.

    ``model_sha256`` is a manifest digest and ``weights_sha256`` is a hash over
    checkpoint tensors; pinning the wrong one for a backend is refused at claim
    time rather than silently skipped, so the config must not carry it.
    """
    config = json.loads(
        (SERVING / "configs" / "srv-full.json").read_text(encoding="utf-8")
    )
    fields = {"ollama": "model_sha256", "vllm": "weights_sha256"}
    for entry in config["models"]:
        expect = entry.get("expect") or {}
        wrong = set(fields.values()) - {fields[entry["backend"]]}
        assert not (wrong & set(expect)), (
            f"{entry['label']} pins {sorted(wrong & set(expect))}, which is not "
            f"{entry['backend']}'s field"
        )


# --- what an adversarial pass found -----------------------------------------


def test_one_model_failing_does_not_destroy_the_survey(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A survey is hours of rig time; an ssh dying in the last model must not
    discard every model before it.

    Unguarded, one RuntimeError from `describe` propagated out of `run` and
    nothing at all was written — the failure mode this whole instrument spent a
    day learning to avoid, reintroduced at the orchestration layer.
    """
    table = _stub(runner, monkeypatch)
    monkeypatch.setattr(
        table["beta"],
        "describe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ssh died")),
    )
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "ok", "backend": "alpha", "id": "m"},
                {"label": "bad", "backend": "beta", "id": "m"},
            ],
        }
    )
    assert "description" in result["hosts"]["h"]["measured"]["ok"]
    bad = result["hosts"]["h"]["measured"]["bad"]
    assert bad["verified"] is True, "the claim succeeded; only the description failed"
    assert "ssh died" in bad["incomplete"]
    assert result["refusals"][-1]["stage"].startswith("describe/ramp")


def test_a_model_id_with_a_quote_cannot_reach_the_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serving config is interpolated into a shell on the serving host.

    A model id containing an apostrophe closes the quote — breaking the command
    at best and running the remainder as shell at worst. Checked by building the
    command and handing it to a real shell, because reasoning about quoting is
    how quoting bugs survive review: a first attempt at this test reported a
    false positive by looking for the wrong escape sequence.
    """
    import contextlib
    import subprocess

    backend: Any = _by_path("quote_ollama", SERVING / "backends" / "ollama.py")
    sent: list[str] = []

    def record(host: str, command: str, timeout: float | None = None) -> str:
        sent.append(command)
        return "200"

    monkeypatch.setattr(backend.contract, "ssh", record)
    monkeypatch.setattr(backend.contract, "drop_page_cache", lambda host: {})
    monkeypatch.setattr(backend, "release", lambda host: {"released": True})
    monkeypatch.setattr(backend, "_resident", lambda host: [])
    monkeypatch.setattr(backend, "_server", lambda host: {"instances": []})
    monkeypatch.setattr(backend, "_digest", lambda base, model: None)
    marker = "/tmp/mcgyvr-quote-probe"
    # The claim will fail its verification — irrelevant. What is under test is
    # the command it BUILT before failing.
    with contextlib.suppress(Exception):
        backend.claim("h", "http://x", f"evil'; touch {marker}; echo '")

    command = next(c for c in sent if "api/generate" in c)
    probe = command.replace("curl", "true").replace("-o /dev/null", "")
    subprocess.run(["bash", "-c", probe], capture_output=True)
    assert not Path(marker).exists(), (
        "a model id reached the shell as a command: " + command[:200]
    )


def test_an_unusable_environment_variable_name_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Values were quoted and keys were not, so an `env` key was a command.

    A variable name is a narrow shape, so it is validated rather than escaped:
    quoting would produce a name no shell would export, hiding the typo instead
    of naming it.
    """
    backend: Any = _by_path("envcheck_vllm", SERVING / "backends" / "vllm.py")
    monkeypatch.setattr(
        backend.contract, "ssh", lambda host, command, timeout=None: "launched"
    )
    monkeypatch.setattr(backend, "release", lambda host: {})
    # #354: the card is stubbed like everything else here, so the pre-launch fit
    # check has no reading to work with and would refuse first. It is exercised
    # in tests/test_serving_memory_declaration.py; this test is about env names.
    monkeypatch.setattr(backend, "free_mib", lambda host: 12287)
    # The backend's OWN contract, not the fixture's: an earlier test clears the
    # shared module slot to prove each backend loads alone, so a later fresh
    # load builds a different `NotCleanError` class object and an identity check
    # against the fixture's copy would miss it.
    with pytest.raises(backend.contract.NotCleanError, match="not a usable environ"):
        backend._start(
            "h",
            "m",
            # ADR-0039: `serve` must declare its KV cache or `_start` refuses
            # before it reaches the env names this test is about.
            {
                "kv_cache_memory_bytes": 1879048192,
                # #354: an entry that declares bytes also declares the
                # weights they are weighed against, or the fit check refuses
                # before it reaches the env names.
                "weights_bytes": 1181116006,
                "env": {"A; touch /tmp/x; B": "1"},
            },
        )


@pytest.mark.parametrize("name", BACKENDS)
def test_a_pin_naming_the_wrong_field_is_refused_not_ignored(
    contract: Any, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """A config that believes it is pinned and is not.

    Each backend computes a different KIND of digest, so a pin has to name the
    one that backend produces. Naming another backend's field was silently
    accepted: the success path returned before the check, because the real pin
    was absent and absent means "nothing to verify". A pin that passes when
    misspelled is worse than no pin, and this was only found by running it
    against a live server rather than a stub.

    Parametrised over the discovered roster, so a third backend inherits the
    property the day its file lands.
    """
    backend: Any = _by_path(f"pin_{name}", SERVING / "backends" / f"{name}.py")
    monkeypatch.setattr(backend.contract, "ssh", lambda *a, **k: None)
    with pytest.raises(backend.contract.NotCleanError, match="not this backend's pin"):
        backend.claim("h", "http://x", "m", {}, {"definitely_not_a_real_field": "x"})


def test_no_host_reading_reaches_disk_unredacted(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Host readings are the most credential-dense material this tool touches.

    A systemd `Environment=` line, a `docker inspect` env block, a process
    command line and an exported launch command are where a key actually lives —
    far more so than the single endpoint URL the per-run capture already guarded
    with a whole scrubbing subsystem. All of it was being written verbatim to a
    tracked path; the careful redaction was on the small surface and none of it
    on the large one.

    Every reading path at once, because a targeted fix missed one: the parsed
    per-instance detail was redacted while the raw listing it was parsed FROM
    was not, and only a planted secret across the whole surface found it.

    Fixtures are assembled at runtime, never written as literals.
    """
    ollama: Any = _by_path("leak_ollama", SERVING / "backends" / "ollama.py")
    vllm: Any = _by_path("leak_vllm", SERVING / "backends" / "vllm.py")
    token = "ghp_" + "z" * 36
    key = "AKIA" + "Q" * 16
    leak = (
        f'Environment="OLLAMA_KEY={token}" HOME=/home/someone '
        f"api=https://user:pw@host/x {key} --port 9 llama-server"
    )

    # Each backend's OWN contract reference: an earlier test clears the shared
    # module slot, so a later fresh load holds a different module object and
    # patching only the fixture's copy would leave the real fetchers live.
    def _ssh(h: str, c: str, timeout: float | None = None) -> str:
        # The readiness loop is answered so `_start` reaches its RETURN and the
        # launch record can be inspected. Everything else leaks on purpose.
        return "ready" if "/health" in c else leak

    for module in (contract, ollama.contract, vllm.contract):
        monkeypatch.setattr(module, "ssh", _ssh)
    monkeypatch.setattr(vllm, "launcher", lambda host: "pip")
    # #354: `_ssh` leaks on purpose and answers nothing numeric, so the card
    # reading the fit check needs is absent and it would refuse before `_start`
    # returns the launch record this test inspects.
    monkeypatch.setattr(vllm, "free_mib", lambda host: 12287)
    monkeypatch.setattr(
        vllm.contract, "get_json", lambda url, timeout=None: {"vllm_config": leak}
    )

    written = json.dumps(
        {
            "snapshot": contract.snapshot("h"),
            "ollama_readings": ollama.readings("h"),
            "ollama_server": ollama._server("h"),
            "vllm_readings": vllm.readings("h"),
            "vllm_launch": vllm._start(
                "h",
                "m",
                # ADR-0039: declared so `_start` reaches the launch record this
                # test reads; the value is irrelevant to redaction.
                {
                    "kv_cache_memory_bytes": 1879048192,
                    "weights_bytes": 1181116006,  # #354
                    "env": {"HF_TOKEN": token},
                },
            ),
            # The three vLLM host-derived returns the first version of this
            # test did not reach: the digest carries a home-directory snapshot
            # path, and both config readers parse `/server_info`'s repr, which
            # carries `model='/path/…'` and `download_dir`.
            "vllm_weights": vllm.weights_sha256("h", "m"),
            "vllm_serving_config": vllm.serving_config("http://h:8000"),
            "vllm_running_config": vllm._running_config("http://h:8000"),
        }
    )
    for name, secret in (
        ("github token", token),
        ("aws key", key),
        ("url password", "user:pw@"),
        ("home directory", "/home/someone"),
    ):
        assert secret not in written, f"{name} reached the record unredacted"
    # Redacted, not deleted: the reading still tells a reader what was there.
    assert "host/x" in written


def test_an_unreadable_card_is_not_reported_as_an_idle_one(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`(value or 0) <= threshold` collapsed "could not read" into "empty".

    The most dangerous direction for this reading: an unreachable host would
    have been recorded as ready to measure.
    """
    monkeypatch.setattr(contract, "ssh", lambda h, c, timeout=None: None)
    assert contract.snapshot("h")["gpu_idle"] is None

    monkeypatch.setattr(contract, "ssh", lambda h, c, timeout=None: "1 MiB")
    assert contract.snapshot("h")["gpu_idle"] is True


def test_one_missing_digest_is_undecided_not_a_refutation(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing measurement is not evidence of disagreement.

    The guard fired only when EVERY member was null, so one member whose digest
    could not be computed made the set two-valued and was reported as positive
    evidence that the weights differ.
    """
    table = _stub(runner, monkeypatch)
    table["alpha"].digest = "aaa"
    table["beta"].digest = None
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha", "beta"],
            "collect": {},
            "models": [
                {"label": "a", "backend": "alpha", "id": "m", "family": "f"},
                {"label": "b", "backend": "beta", "id": "m", "family": "f"},
            ],
        }
    )
    verdict = result["families"]["f"]["verdict"]
    assert verdict.startswith("UNDECIDED")
    assert "'b'" in verdict, "the member that produced nothing is named"


# --- the serving-config fingerprint -----------------------------------------


@pytest.fixture(scope="module")
def fingerprint() -> Any:
    return _by_path("serving_fingerprint", SERVING / "fingerprint.py")


# The four nested blocks from a live vLLM config, verbatim. A naive comma split
# produced 55 keys where 33 exist and gave the wrong value for every one of
# these — they are here because they are exactly what the depth-0 reader is for.
LIVE_REPR = (
    "model='Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ', dtype=torch.float16, "
    "max_seq_len=8192, quantization=auto_awq, enforce_eager=True, "
    "structured_outputs_config=StructuredOutputsConfig(backend='auto', "
    "disable_any_whitespace=False, reasoning_parser=''), "
    "observability_config=ObservabilityConfig(kv_cache_metrics=False, "
    "cudagraph_metrics=False), seed=0, enable_prefix_caching=True"
)


def test_nested_config_survives_the_parse(fingerprint: Any) -> None:
    """Splitting on every comma flattened nested constructors into phantoms."""
    parsed = fingerprint.parse_repr("Config(" + LIVE_REPR + ")")
    parsed.pop("_type", None)
    assert len(parsed) == 9, sorted(parsed)
    structured = parsed["structured_outputs_config"]
    assert structured["backend"] == "auto"
    assert structured["disable_any_whitespace"] is False
    assert parsed["max_seq_len"] == 8192 and parsed["seed"] == 0
    assert parsed["enable_prefix_caching"] is True

    naive = {t.split("=")[0].strip() for t in LIVE_REPR.split(",") if "=" in t}
    assert len(naive) > len(parsed), "the naive split invents keys"


def test_the_two_digests_move_independently(fingerprint: Any) -> None:
    """One digest would re-baseline a round when somebody enabled a counter.

    The semantic half is the one a guard could key on, so a change to metrics
    must leave it untouched — and a change to structured-output enforcement must
    move it, because that changes what a reply is allowed to be (ADR-0009).
    """
    base = fingerprint.parse_repr("Config(" + LIVE_REPR + ")")
    base.pop("_type", None)
    first = fingerprint.fingerprint(base)

    metrics = dict(base)
    metrics["observability_config"] = {"kv_cache_metrics": True}
    changed = fingerprint.fingerprint(metrics)
    assert changed["serving_semantic_sha256"] == first["serving_semantic_sha256"]
    assert changed["serving_operational_sha256"] != first["serving_operational_sha256"]

    output = dict(base)
    output["structured_outputs_config"] = {"backend": "xgrammar"}
    moved = fingerprint.fingerprint(output)
    assert moved["serving_semantic_sha256"] != first["serving_semantic_sha256"]
    assert moved["serving_operational_sha256"] == first["serving_operational_sha256"]


def test_an_unknown_key_refuses_rather_than_defaulting(fingerprint: Any) -> None:
    """A new engine field must not fall silently to either side.

    Defaulting to "operational" would drop a setting that changes output out of
    the semantic pin while the pin went on looking green — the exact failure
    this module exists to prevent, reintroduced by a convenience.
    """
    with pytest.raises(fingerprint.UnclassifiedError, match="brand_new_flag"):
        fingerprint.fingerprint({"dtype": "float16", "brand_new_flag": True})


def test_no_key_is_both_semantic_and_operational(fingerprint: Any) -> None:
    """A key in both sets would be pinned twice and mean neither thing."""
    assert not (fingerprint.SEMANTIC & fingerprint.OPERATIONAL)


def test_the_sampler_defaults_are_semantic(fingerprint: Any) -> None:
    """49 of them sit under every request this project dispatches.

    They were captured verbatim and read by nothing, which made the engine that
    exposes MORE configuration the less-instrumented of the two.
    """
    for name in (
        "temperature",
        "top_k",
        "top_p",
        "repeat_penalty",
        "samplers",
        "mirostat",
        "dry_multiplier",
        "seed",
        "n_ctx",
        "total_slots",
    ):
        assert name in fingerprint.SEMANTIC, name


# --- pinning a run to the host readings --------------------------------------


@pytest.fixture(scope="module")
def pin_module() -> Any:
    return _by_path("serving_pin", SERVING / "pin.py")


def _side(token: str | None, digest: str | None) -> dict[str, Any]:
    return {
        "instance": {"token": token} if token else {},
        "fingerprint": {"serving_semantic_sha256": digest} if digest else {},
    }


def test_all_three_claims_holding_is_what_pins_a_run(pin_module: Any) -> None:
    result = pin_module.pin(
        _side("boot:start:1", "aaa"), _side("boot:start:1", "aaa"), {"held": True}
    )
    assert result["pinned"] is True
    assert result["claims"] == {
        "same_machine": True,
        "same_process": True,
        "same_config": True,
    }


def test_a_restart_mid_run_breaks_the_pin(pin_module: Any) -> None:
    """A different start time is a different process, whatever the pid says."""
    result = pin_module.pin(
        _side("boot:100:7", "aaa"), _side("boot:900:7", "aaa"), {"held": True}
    )
    assert result["claims"]["same_process"] is False
    assert result["pinned"] is False


def test_a_config_change_without_a_restart_breaks_the_pin(pin_module: Any) -> None:
    """The claim the other two cannot make, and it is not hypothetical.

    Ollama re-derives serving parameters per model: measured on one host with
    one OLLAMA_NUM_PARALLEL, `qwen2.5-coder:*` was served `-c 8192 -np 2` and
    `nemotron-3-nano:4b` `-c 4096 -np 1`. Same machine, same pid, different
    served window — so `same_machine` and `same_process` both hold while the
    thing being described has changed underneath them.
    """
    result = pin_module.pin(
        _side("boot:100:7", "aaa"), _side("boot:100:7", "bbb"), {"held": True}
    )
    assert result["claims"]["same_process"] is True
    assert result["claims"]["same_config"] is False
    assert result["pinned"] is False


def test_a_claim_that_could_not_be_checked_is_not_a_claim_that_held(
    pin_module: Any,
) -> None:
    """`None` is a third state: "we did not look" is not "we looked and it was
    fine", and a run with no close capture has not been pinned by anything."""
    result = pin_module.pin(
        _side("boot:100:7", "aaa"), _side(None, None), {"held": True}
    )
    assert result["claims"]["same_process"] is None
    assert result["claims"]["same_config"] is None
    assert result["pinned"] is False


def test_an_endpoint_pointing_elsewhere_breaks_the_pin(
    pin_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host readings must describe the machine that served the run.

    A proxy, a tunnel or a load balancer in front of several servers all give a
    host whose readings look perfectly healthy and describe the wrong box.
    """
    monkeypatch.setattr(
        pin_module.socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("203.0.113.9", 0))],
    )
    monkeypatch.setattr(
        pin_module.contract, "ssh", lambda h, c, timeout=None: "10.0.0.4 172.17.0.1"
    )
    machine = pin_module.same_machine("h", "http://elsewhere:8000")
    assert machine["held"] is False
    assert "NOT among" in machine["why"]
    assert pin_module.pin(_side("t", "a"), _side("t", "a"), machine)["pinned"] is False


def test_a_reused_pid_after_a_reboot_is_not_the_same_process(pin_module: Any) -> None:
    """Why the token carries boot time and not only the pid."""
    result = pin_module.pin(
        _side("1000:50:7", "aaa"), _side("2000:50:7", "aaa"), {"held": True}
    )
    assert result["claims"]["same_process"] is False


# --- the two paths the adversarial review found untested --------------------


def _ollama_rig(
    monkeypatch: pytest.MonkeyPatch,
    *,
    card_before: int,
    card_after: int,
    resident: list[dict[str, Any]],
    children: str | list[str] = "4242 /usr/local/lib/ollama/llama-server --model "
    "/blobs/sha256-aaa --port 4242 -c 4096 -np 2",
) -> Any:
    """A fake ollama host: one card reading, one `/api/ps`, one child listing.

    ``children`` may be a per-attempt sequence (#326): attempt *n* sees the
    *n*-th listing, so a load that fails once and succeeds once is expressible.

    Loaded by path and patched on its OWN contract reference, because an earlier
    test clears the shared module slot and a fresh load holds a different module
    object.
    """
    ollama: Any = _by_path("gated_ollama", SERVING / "backends" / "ollama.py")

    reads: list[int] = []
    listings = iter(children) if isinstance(children, list) else None

    def _ssh(host: str, command: str, timeout: float | None = None) -> str | None:
        if "memory.used" in command:
            # The card is read twice per attempt and the two readings are
            # different facts: once by `release`, BEFORE the load, and once by
            # `claim` after it. A stub returning one value for both cannot
            # express "idle beforehand, holding the model afterwards" — which is
            # the only state in which a clean claim succeeds.
            # Two reads per ATTEMPT, and `claim` retries the whole cycle, so
            # the pattern is before/after/before/after — not first/rest.
            reads.append(1)
            return f"{card_before if len(reads) % 2 else card_after} MiB"
        if "api/ps" in command and "curl -s -m 15" in command:
            return json.dumps({"models": resident})
        # `pgrep -af '[l]lama-server'` — the bracket keeps pgrep from matching
        # its own command line, and it also means the literal "llama-server"
        # does not appear in the string. Matching on it silently returned no
        # children, so these tests raised on `no_server_child` and would have
        # passed with the gate under test deleted.
        if "pgrep -af" in command:
            return next(listings) if listings is not None else str(children)
        if "http_code" in command:
            return "200"
        if "pgrep -c" in command:
            return "0"
        if "modelfile" in command:
            return "/blobs/sha256-aaa"
        return ""

    monkeypatch.setattr(ollama.contract, "ssh", _ssh)
    monkeypatch.setattr(
        ollama.contract,
        "get_json",
        lambda url, timeout=None: {"models": [{"name": "m", "digest": "d"}]},
    )
    return ollama


def test_a_dirty_card_refuses_the_load_that_lands_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D4 withdrew a gate on the promise that this check replaced it.

    `MIN_VRAM_FRACTION` was removed because a placement fraction means different
    things per architecture — and the stated replacement was that `claim`
    already refuses a card that was not idle before the load. It did not: the
    field was READ and then left out of the verdict, so the promise was only
    ever true of the prose. Without it nothing catches contamination for the two
    MoE entries, which are precisely the entries D4 exists to make measurable.

    A foreign allocation before the load, the model placed at 8% — the case this
    module's own docstring describes as serving happily at a twentieth of speed.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=4916,
        card_after=4996,
        resident=[{"name": "m", "size": 1000, "size_vram": 80}],
    )
    with pytest.raises(ollama.contract.NotCleanError) as raised:
        ollama.claim("h", "http://h:11434", "m")
    # EXACTLY this reason: a refusal for some other cause would carry
    # `card_not_idle_before_load` too, since the reason list is built from every
    # failing condition. Equality is what makes this a test of the gate.
    assert raised.value.reasons == ["card_not_idle_before_load"]


def test_a_refusal_carries_its_reasons_as_data_not_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D8's third defect was a reason recoverable only by regex over a sentence.

    Building reason codes and then interpolating them into the message would
    reproduce it exactly: the codes exist and a consumer still has to parse them
    back out of a string.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[{"name": "m", "size": 1000, "size_vram": 1000}],
        children="",
    )
    with pytest.raises(ollama.contract.RefusedError) as raised:
        ollama.claim("h", "http://h:11434", "m")
    assert raised.value.reasons == ["no_server_child"]


def test_a_load_that_fails_once_and_succeeds_once_records_both_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dogfood for `LOAD_ATTEMPTS = 2` (#326): does a second attempt ever
    rescue a first, and what did each cost. Before this no test named the
    constant and no sink kept more than the last attempt."""
    good = (
        "4242 /usr/local/lib/ollama/llama-server --model /blobs/sha256-aaa "
        "--port 4242 -c 4096 -np 2"
    )
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[{"name": "m", "size": 1000, "size_vram": 1000}],
        children=["", good],
    )
    assert ollama.LOAD_ATTEMPTS == 2
    claimed = ollama.claim("h", "http://h:11434", "m")
    trail = claimed["attempts"]
    assert [a["ok"] for a in trail] == [False, True]
    assert [a["attempt"] for a in trail] == [1, 2]
    for attempt in trail:
        assert isinstance(attempt["seconds"], float) and attempt["seconds"] >= 0
        assert attempt["started_at"] <= attempt["ended_at"]

    calibrate: Any = _by_path("serving_calibrate_dogfood", SERVING / "calibrate.py")
    row = calibrate._load_row("h", "m", 0, 3.0, True, None, claimed)
    assert row["attempts"] == 2
    assert row["attempt_outcomes"] == [False, True]
    assert row["rescued_by_retry"] is True
    assert row["attempt"] == 2 and row["attempt_seconds"] == trail[-1]["seconds"]
    # A first-try success is not a rescue.
    first = calibrate._load_row("h", "m", 0, 3.0, True, None, {"attempts": trail[-1:]})
    assert first["attempts"] == 1 and first["rescued_by_retry"] is False


def test_a_refused_claim_carries_its_attempt_trail_as_data(
    runner: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`RefusedError.attempts` is the whole trail, and both sinks keep it."""
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[{"name": "m", "size": 1000, "size_vram": 1000}],
        children="",
    )
    with pytest.raises(ollama.contract.RefusedError) as raised:
        ollama.claim("h", "http://h:11434", "m")
    trail = raised.value.attempts
    assert len(trail) == ollama.LOAD_ATTEMPTS
    assert [a["ok"] for a in trail] == [False, False]
    assert all("seconds" in a for a in trail)

    # The load row: the trail, counted and judged.
    calibrate: Any = _by_path("serving_calibrate_refusal", SERVING / "calibrate.py")
    row = calibrate._load_row(
        "h", "m", 0, 5.0, False, "RefusedError: x", {"attempts": list(trail)}
    )
    assert row["attempts"] == 2 and row["attempt_outcomes"] == [False, False]
    assert row["rescued_by_retry"] is False and row["attempt"] == 2

    # The survey's refusal block, through the real `run`.
    class Refusing:
        NAME, PORT = "alpha", 11434

        def probe(self, host: str) -> str:
            return "http://h:11434"

        def inventory(self, host: str, base: str) -> list[str]:
            return ["m"]

        def readings(self, host: str) -> dict[str, Any]:
            return {}

        def release(self, host: str) -> dict[str, Any]:
            return {"released": True}

        def claim(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise raised.value

    monkeypatch.setattr(runner.contract, "load_backend", lambda name: Refusing())
    monkeypatch.setattr(runner.contract, "snapshot", lambda host: {})
    journal = tmp_path / "j.jsonl"
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "models": [{"label": "x", "backend": "alpha", "id": "m"}],
        },
        journal=journal,
    )
    measured = result["hosts"]["h"]["measured"]["x"]
    assert measured["outcome"] == "launch_failed"
    assert measured["refusal"]["reasons"] == ["no_server_child"]
    assert measured["refusal"]["attempts"] == trail
    recorded = json.loads(journal.read_text().splitlines()[0])
    assert recorded["refusal"]["attempts"] == trail


def test_a_placement_key_the_backend_does_not_read_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`expect` has had this guard from the start; `placement` had none.

    D4 replaced a constant with a per-entry declaration, so an ignored typo in
    that declaration is an entry believing it set a floor it does not have — on
    the one field whose whole purpose is to BE the declaration.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[{"name": "m", "size": 1000, "size_vram": 1000}],
    )
    with pytest.raises(ollama.contract.NotCleanError, match="placement declaration"):
        ollama.claim("h", "http://h:11434", "m", placement={"min_vram_fracton": 0.8})


def test_co_residency_is_arranged_rather_than_merely_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D7 item 4 measures INTENDED co-residency.

    Accepting a neighbour is not arranging one, and before this the gate was
    `resident_names == [model]`, so the step was refused by construction. A
    neighbour that does not become resident refuses the entry: a row that asked
    to measure sharing and silently measured solo is the wrong answer, not a
    lenient one.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[{"name": "m", "size": 1000, "size_vram": 1000}],
    )
    with pytest.raises(ollama.contract.RefusedError) as raised:
        ollama.claim("h", "http://h:11434", "m", coresident_with=["neighbour"])
    assert raised.value.reasons == ["coresidency_not_arranged"]


def test_the_placement_of_every_resident_is_recorded_not_only_the_model_under_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#335 box 5 — "it loaded" and "it fits" are different facts.

    `_placement` ran for the model under test alone, so a co-residency cell
    recorded that its neighbour was *listed* and never where the neighbour
    *landed*. The campaign header's first `void_if` — "any cell records a
    verdict without the placement of EVERY resident on it" — was therefore
    unevaluable on every cell in the tree, including the sixty of the plan it
    was written for.

    The fraction here is srv1's, measured 2026-08-22: ollama answered
    `load_http=200` with 93% of the model on the CPU, and the spilled model
    still returned correct code. Nothing in the record said so.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[
            {"name": "neighbour", "size": 1000, "size_vram": 68},
            {"name": "m", "size": 1000, "size_vram": 1000},
        ],
    )
    claimed = ollama.claim("h", "http://h:11434", "m", coresident_with=["neighbour"])
    attempt = claimed["attempts"][-1]
    # The existing verdict, unchanged and still true: the neighbour is there.
    assert attempt["coresidency_arranged"] is True
    placed = {row["name"]: row for row in attempt["resident_placements"]}
    assert set(placed) == {"m", "neighbour"}, (
        "a placement for the model under test alone is the gap, not the fix"
    )
    assert placed["m"]["fraction"] == 1.0
    assert placed["neighbour"]["fraction"] == 0.068
    # Recorded, never gated. A spilled neighbour is the frontier this campaign
    # exists to map; a claim that refused it would refuse its own question.
    assert attempt["ok"] is True


def test_a_resident_whose_row_carries_no_usable_size_is_named_without_a_fraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing fraction says "unknown", and must not say "on the card".

    `_placed` returns `size`/`size_vram` and no `fraction` when either is not a
    positive integer — the same shape `_placement` has always had for the model
    under test. Asserted here because the whole-card view is the one a reader
    scans for a number, and a `0.0` invented for an unreadable row would be a
    measurement nobody took.
    """
    ollama = _ollama_rig(
        monkeypatch,
        card_before=10,
        card_after=1200,
        resident=[
            {"name": "neighbour", "size": None, "size_vram": 900},
            {"name": "m", "size": 1000, "size_vram": 1000},
        ],
    )
    claimed = ollama.claim("h", "http://h:11434", "m", coresident_with=["neighbour"])
    attempt = claimed["attempts"][-1]
    placed = {row["name"]: row for row in attempt["resident_placements"]}
    assert "fraction" not in placed["neighbour"]
    assert placed["neighbour"]["size_vram"] == 900


# --- #345: the same question, asked of the engine that cannot spill ---------

#: What `ps -eo pid=,ppid=,args= | grep -E '[V]LLM::EngineCore|[v]llm serve|…'`
#: printed on srv1, 2026-08-22, with vLLM installed by pip. Verbatim, because a
#: fixture captures what the parser reads (ADR-0016) — including the launcher's
#: own `bash -c` line, which the grep matches too.
_SRV1_TREE = (
    "1133927       1 bash -c export VLLM_SERVER_DEV_MODE=1 "
    "FLASHINFER_DISABLE_VERSION_CHECK=1; export PATH=$HOME/.local/bin:$PATH; "
    "cd /tmp && nohup vllm serve Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ "
    "--max-model-len 8192 --kv-cache-memory-bytes 1879048192 --max-num-seqs 8 "
    "--port 8000 --enforce-eager > /tmp/vllm-345.log 2>&1 < /dev/null & disown; "
    "echo launched\n"
    "1133928 1133927 /usr/bin/python3 /home/adaramir/.local/bin/vllm serve "
    "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ --max-model-len 8192 "
    "--kv-cache-memory-bytes 1879048192 --max-num-seqs 8 --port 8000 "
    "--enforce-eager\n"
    "1133972 1133928 VLLM::EngineCore\n"
)

#: The same read on srv2 the same day, where this engine runs in a container:
#: no launcher line, the binary at a different path, and the leading spaces `ps`
#: pads a narrower pid column with.
_SRV2_TREE = (
    " 364343  364313 /usr/bin/python3 /usr/local/bin/vllm serve "
    "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ --max-model-len 8192 "
    "--kv-cache-memory-bytes 1879048192 --max-num-seqs 8 --port 8000 "
    "--enforce-eager\n"
    " 364842  364343 VLLM::EngineCore\n"
)

#: srv1's card with the vLLM entry and `qwen2.5-coder:1.5b` both on it, and
#: srv2's with the vLLM entry alone. The sentinel is what the probe appends.
_SRV1_APPS = "1133972, 3126 MiB\n1134308, 1196 MiB\n__compute_apps_end__\n"
_SRV2_APPS = "364842, 3174 MiB\n__compute_apps_end__\n"

_AWQ = "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"


def _vllm_card(
    monkeypatch: pytest.MonkeyPatch,
    *,
    apps: str | None,
    tree: str,
    served: list[str],
    name: str = "placement_vllm",
) -> Any:
    """The vLLM backend with one card and one process list under it."""
    vllm: Any = _by_path(name, SERVING / "backends" / "vllm.py")

    def _ssh(host: str, command: str, timeout: float | None = None) -> str | None:
        if "--query-compute-apps" in command:
            return apps
        if command.startswith("ps -eo"):
            return tree
        return None

    monkeypatch.setattr(vllm.contract, "ssh", _ssh)
    monkeypatch.setattr(
        vllm.contract,
        "get_json",
        lambda url, timeout=None: {"data": [{"id": model} for model in served]},
    )
    return vllm


def test_a_vllm_placement_reports_the_card_it_holds_and_refuses_the_fraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0040 rules 1 and 2, on both rigs' real readings.

    ollama reports `size_vram / size` because llama.cpp spills — 6.8% of a model
    on the card, `load_http=200` beside it. vLLM cannot: `requested = ceil(total
    * util)` behind a hard `free >= requested` precondition means it takes the
    whole allocation or refuses to start, so there is no denominator and the
    fraction is **refused with its reason**, never reported as the `1.0` that is
    true by the engine's contract and would read as an ollama fraction of 1.0.

    The MiB are the driver's own, measured 2026-08-22 on the declared serve
    block of `srv-full.json`'s `q15-vllm-s8`: 3,126 on srv1, 3,174 on srv2.
    """
    for tree, apps, mib, rig in (
        (_SRV1_TREE, _SRV1_APPS, 3126, "srv1"),
        (_SRV2_TREE, _SRV2_APPS, 3174, "srv2"),
    ):
        vllm = _vllm_card(monkeypatch, apps=apps, tree=tree, served=[_AWQ])
        rows = vllm.placements(rig)
        mine = [row for row in rows if row["name"] == _AWQ]
        assert len(mine) == 1, f"{rig} serves one model and holds one allocation"
        assert mine[0]["card_mib"] == mib
        # Present and null, not absent: an absent key would say this reading
        # predates the contract, and this engine will never answer it.
        assert "fraction" in mine[0] and mine[0]["fraction"] is None
        assert mine[0]["fraction_refused"], "ADR-0027 D2: a null carries its reason"
        assert not [row for row in rows if row["fraction"] == 1.0], (
            "1.0 is true by this engine's contract and is the one value a "
            "reader would compare against an ollama 0.068 (ADR-0038 D4)"
        )


def test_the_pid_that_holds_the_card_names_no_model_so_the_owner_is_the_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured fact the whole reading turns on.

    vLLM renames its GPU worker with `setproctitle`, so the process the driver
    attributes the memory to has a command line of exactly `VLLM::EngineCore` —
    no model, no flags, nothing to join on. A reading assembled from that pid's
    own line returns `None` on every rig and looks exactly like an empty card.
    The model is on the immediate parent, in both deployment shapes: pip on
    srv1, container on srv2, differing only in the path to the binary.
    """
    vllm = _vllm_card(monkeypatch, apps=_SRV1_APPS, tree=_SRV1_TREE, served=[_AWQ])
    assert vllm._served_name(vllm.ENGINE_CORE) is None

    for tree, pid in ((_SRV1_TREE, 1133972), (_SRV2_TREE, 364842)):
        parsed = vllm._process_tree(tree)
        assert parsed[pid]["args"] == vllm.ENGINE_CORE
        assert vllm._owner(pid, parsed) == _AWQ

    # And it is a join, not a guess: with the parent gone — it exited, or the
    # narrowed `ps` read never matched it — the answer is None.
    orphaned = {pid: row for pid, row in vllm._process_tree(_SRV2_TREE).items()}
    del orphaned[364343]
    assert vllm._owner(364842, orphaned) is None


def test_a_card_holder_this_engine_cannot_name_is_a_row_and_not_a_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0040 rule 3, against the co-residency reading that motivated it.

    srv1 held both engines on 2026-08-22: 3,126 MiB attributed to vLLM's worker
    and 1,196 MiB to a `llama-server` whose parent is `ollama serve`. Dropping
    the second row would make a shared card look solo, which is the same silence
    #335 found on the other engine. Naming it would be this module claiming
    about a model another engine serves, which it must never do — so it is a
    row with `name: null` and the reason beside it.
    """
    vllm = _vllm_card(monkeypatch, apps=_SRV1_APPS, tree=_SRV1_TREE, served=[_AWQ])
    rows = vllm.placements("srv1")
    stranger = [row for row in rows if row["pid"] == 1134308]
    assert len(stranger) == 1, "the other engine's allocation is on this card"
    assert stranger[0]["name"] is None and stranger[0]["card_mib"] == 1196
    assert stranger[0]["unnamed"], "null, with the reason it is null"


def test_a_served_model_the_driver_attributed_nothing_to_is_recorded_as_unplaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0040 rule 4 — the other direction of the same silence.

    The server answers `/v1/models` and the driver attributes no memory to it:
    a worker still starting, or one whose process the narrowed read did not
    match. Absent is not zero. Dropping the model would say it is not being
    served; `card_mib: 0` would say it is on the card holding nothing.
    """
    vllm = _vllm_card(
        monkeypatch,
        apps="1134308, 1196 MiB\n__compute_apps_end__\n",
        tree="",
        served=[_AWQ],
    )
    rows = vllm.placements("srv1")
    mine = [row for row in rows if row["name"] == _AWQ]
    assert len(mine) == 1 and mine[0]["card_mib"] is None
    assert mine[0]["pid"] is None and mine[0]["unplaced"]


def test_an_unread_card_is_refused_and_never_an_empty_placement_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty card and a card nobody read are different answers.

    `contract.ssh` returns `None` for empty stdout, so a host that did not
    answer and a card holding nothing arrive identical — the same collapse
    `snapshot` refuses for `gpu_idle` one reading over. The probe appends a
    sentinel so the parser can tell them apart, and an unread card refuses
    rather than reporting `[]`.
    """
    vllm = _vllm_card(monkeypatch, apps=None, tree="", served=[])
    with pytest.raises(vllm.contract.NotCleanError, match="could not be read"):
        vllm.placements("srv1")

    assert vllm.contract.compute_apps(None) is None
    assert vllm.contract.compute_apps("1133972, 3126 MiB\n") is None, (
        "no sentinel is a read that did not complete, whatever it printed"
    )
    # And the sentinel is CONJOINED to the reading, not appended after it: a
    # missing `nvidia-smi` writes to stderr and prints nothing, so under `;`
    # the sentinel would arrive alone and the card would read as empty — the
    # collapse the sentinel exists to prevent, reintroduced by the separator.
    assert " && echo " in vllm.contract.COMPUTE_APPS_PROBE

    idle = _vllm_card(
        monkeypatch,
        apps="__compute_apps_end__\n",
        tree="",
        served=[],
        name="idle_vllm",
    )
    assert idle.placements("srv1") == []


def test_a_vllm_claim_records_where_everything_on_the_card_sits_and_gates_on_none_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0040 rule 5, on the claim side, where #335 put the ollama half.

    `allocation_present` is a threshold over the card's TOTAL, so it says yes to
    a card whose memory belongs to somebody else. What the claim could not say
    was *whose*. It says so now — and still returns `ok`, with another engine's
    1,196 MiB sitting beside it, because a shared card is the frontier this
    campaign maps and a claim that refused one would refuse its own question.
    """
    vllm = _vllm_card(
        monkeypatch,
        apps=_SRV1_APPS,
        tree=_SRV1_TREE,
        served=[_AWQ],
        name="claim_vllm",
    )
    inner = vllm.contract.ssh

    def _ssh(host: str, command: str, timeout: float | None = None) -> str | None:
        if "--query-gpu=memory.used" in command:
            return "4326 MiB"
        fell_through: str | None = inner(host, command, timeout)
        return fell_through

    monkeypatch.setattr(vllm.contract, "ssh", _ssh)
    monkeypatch.setattr(vllm, "_running_config", lambda base: {"model": _AWQ})
    monkeypatch.setattr(vllm, "_matches", lambda running, serve: True)
    monkeypatch.setattr(vllm, "weights_sha256", lambda host, model: {})

    claimed = vllm.claim("srv1", "http://srv1:8000", _AWQ)
    placed = claimed["checks"]["resident_placements"]
    assert {row["pid"] for row in placed} == {1133972, 1134308}
    assert claimed["checks"]["resident_placements_refused"] is None
    assert claimed["checks"]["ok"] is True, "recorded, never gated"


def test_the_compute_apps_reading_is_declared_once_and_has_a_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reading stops being minted-and-unwired, and cannot go back.

    §3 of the run contract names three idle readings this tree computes and
    never reads, and warns against adding a fourth. `gpu_compute_apps` was one
    of them: a string that appeared once, inside `snapshot`, consumed by
    nothing. It is now declared once and read twice — `snapshot` records the
    line, `vllm.placements` computes from it — and a second inline copy is how
    the two would come to mean different things.
    """
    launcher = _launcher()
    contract_source = (SERVING / "contract.py").read_text(encoding="utf-8")
    vllm_source = (SERVING / "backends" / "vllm.py").read_text(encoding="utf-8")
    written = {
        where: [
            line
            for line in launcher.code_lines(source)
            if "--query-compute-apps" in line
        ]
        for where, source in (("contract", contract_source), ("vllm", vllm_source))
    }
    assert len(written["contract"]) == 1, f"declared once, found {written['contract']}"
    assert written["vllm"] == [], "a consumer reads the declaration, never re-types it"
    assert "COMPUTE_APPS_COMMAND = (" in contract_source
    assert "COMPUTE_APPS_PROBE" in vllm_source, "and it has a consumer"

    # And behaviourally, not only textually: the line `snapshot` records is the
    # same string the placement reading runs, because it is the same object.
    contract_module: Any = _by_path("wiring_contract", SERVING / "contract.py")
    monkeypatch.setattr(contract_module, "ssh", lambda h, c, timeout=None: None)
    monkeypatch.setattr(contract_module, "scrub", lambda value: value)
    recorded = contract_module.snapshot("h")["readings"]["gpu_compute_apps"]
    assert recorded["command"] == contract_module.COMPUTE_APPS_COMMAND
    assert contract_module.COMPUTE_APPS_PROBE.startswith(recorded["command"])


# --- the verify-then-launch step --------------------------------------------


def _launcher() -> Any:
    return _by_path("serving_launch", SERVING / "launch.py")


def test_the_launcher_passes_on_the_tree_it_is_launching() -> None:
    """The markers describe THIS tree, so they must hold against it.

    A marker list that has drifted from the code is worse than none: it refuses
    every launch until someone deletes the check, which is how the check stops
    existing.
    """
    launcher = _launcher()
    assert launcher.check("test") == []


def test_a_dry_run_is_reported_to_but_not_refused_by_a_live_driver(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E14 protects a rig from a second CLAIMANT, and a dry run claims nothing.

    Found by this file failing for a reason unrelated to what it asserts: a
    campaign was running on this client, so `--dry-run` — which prints the
    driver text and returns — was refused by a guard about throughput
    contention, and the check about shell constructs reported on the state of
    the machine instead. That is the shape this lane keeps meeting: a check
    that fails because of WHEN it ran rather than what it asserts.

    The fact is still printed on a dry run, because suppressing it would trade
    one silent failure for another. Only the refusal is scoped.
    """
    launcher = _launcher()
    monkeypatch.setattr(
        launcher, "already_running", lambda: ["705744 python run.py --config x"]
    )

    assert (
        launcher.main(
            ["--campaign", "--dry-run", "--log", str(tmp_path / "unused.log")]
        )
        == 0
    )
    dry = capsys.readouterr().out
    assert "705744" in dry, "the operator must still be told a driver is up"
    assert "REFUSED" not in dry

    # And the refusal is intact on the path it protects: a real launch.
    assert launcher.main(["--campaign", "--log", str(tmp_path / "unused.log")]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_an_interrupted_driver_lets_go_of_the_rigs(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A killed driver left srv2 holding 11,078 MiB until it was cleared by hand.

    The property is not that a handler exists — it is that the handler can RUN.
    `sh` defers a trap while a FOREGROUND child is running, so the obvious
    spelling releases the rigs only once the interrupted phase has finished on
    its own: measured at 300 seconds against a 300-second phase, which over
    eleven hours is no handler at all. The phases must therefore be backgrounded
    behind an interruptible `wait`, and the handler must kill the phase's own
    children before releasing, or the release races a live claimant.

    Pinned against the driver text the launcher actually emits, because every
    one of these is a shell construct that a later edit could drop while the
    campaign still launched perfectly.
    """
    launcher = _launcher()
    assert (
        launcher.main(
            ["--campaign", "--dry-run", "--log", str(tmp_path / "unused.log")]
        )
        == 0
    )
    driver = capsys.readouterr().out

    assert "wait $CHILD" in driver, "a foreground phase defers the trap"
    assert "} &" in driver, "the phases must not be the foreground child"
    assert "pkill -P $CHILD" in driver, "the phase's children outlive it"
    assert "--release" in driver, "the handler has to release something"
    # Once for the signal, once for the ordinary end: a campaign that refuses in
    # its last phase would otherwise exit still holding a card.
    assert driver.count("cleanup") >= 3

    # **The stop sentinel, and the ORDER it is written in.** `pkill -P $CHILD`
    # and `kill $CHILD` are two commands, and between them the subshell's `wait`
    # returns and it forks the NEXT phase — which is then reparented to init and
    # never signalled, so `cleanup` releases the rigs while an orphaned survey
    # re-claims them. Measured on stand-ins at 4-17 of every 20 SIGTERM trials
    # before the guard and 0 of 20 after.
    #
    # Pinned as an order, not as a presence: a `touch` that happened after the
    # kills would satisfy a substring test and close nothing.
    trap = next(line for line in driver.splitlines() if line.startswith("trap "))
    assert trap.index("touch") < trap.index("pkill"), (
        "the sentinel must be written BEFORE anything is signalled"
    )
    assert trap.index("touch") < trap.index("cleanup"), (
        "a phase must not be able to start during the release"
    )
    # Every phase after the first is gated on it. The first is deliberately not:
    # nothing can have set the sentinel before the driver starts, and the `rm`
    # on the way in is what makes an interrupted run's leftover harmless.
    assert driver.count("[ -f ") == len(launcher.CAMPAIGN) - 1, (
        "every phase but the first is gated on the sentinel"
    )
    assert "rm -f " in driver, "a stale sentinel must not silence a fresh campaign"


def test_the_launcher_refuses_the_exact_failure_it_exists_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """1.5 h of rig time went to a patch that silently never reached the file.

    The unchanged harness ran and produced a full set of plausible readings. So
    the interesting property is not that the launcher passes — it is that it
    REFUSES when a decision is missing, and names which one.
    """
    launcher = _launcher()
    real = launcher.REPO

    def _staged(path: str) -> str:
        # `real` is the launcher's own Path, whose read_text mypy cannot narrow
        # through the SimpleNamespace below — annotated rather than cast so the
        # str-ness is asserted here, where the substitution happens.
        text: str = (real / path).read_text(encoding="utf-8")
        return text.replace("RAMP_TOKENS = 475", "RAMP_TOKENS = 128")

    class _Repo:
        def __truediv__(self, path: str) -> Any:
            return types.SimpleNamespace(read_text=lambda encoding=None: _staged(path))

    monkeypatch.setattr(launcher, "REPO", _Repo())
    problems = launcher.check("reverted")
    assert any("RAMP_TOKENS = 475" in p and "D3" in p for p in problems)


def test_a_docstring_naming_a_withdrawn_constant_is_not_a_hit() -> None:
    """The absence check reads code, not prose, and this is why.

    The first version was a plain substring test and refused a correct tree,
    because the docstring explaining what D1 replaced `BATCHING_SPEEDUP = 2.0`
    with contains the string. A record of what a constant used to be is the
    opposite of the defect the list hunts for — and a check that cannot tell a
    definition from a mention of one pushes every author toward deleting the
    explanation.
    """
    launcher = _launcher()
    source = (SERVING / "contract.py").read_text(encoding="utf-8")
    assert "BATCHING_SPEEDUP = 2.0" in source, "the explanation should still be there"
    code = launcher.code_lines(source)
    assert not [line for line in code if "BATCHING_SPEEDUP = 2.0" in line]


def test_the_launched_width_is_read_off_the_host_not_off_our_own_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E5, revised: no endpoint carries it, but the host does.

    Concluding "there is no observed source" from the HTTP surface alone stopped
    one step early. The flag is in the server's own argv on the pip rig and in
    the container's `Config.Cmd` on the docker rig — both verified on the rigs.
    That matters because `claim` has a path that does NOT restart a server
    already serving the wanted configuration, so on that path a server someone
    else started at a different width would otherwise be described using our
    variable, with nothing looking wrong.

    Fixtures are the two real shapes, read off srv1 and srv2 on 2026-08-19.
    """
    vllm: Any = _by_path("width_vllm", SERVING / "backends" / "vllm.py")
    pip_argv = (
        "adaramir 774452 /usr/bin/python3 /home/adaramir/.local/bin/vllm serve "
        "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ --max-model-len 8192 "
        "--gpu-memory-utilization 0.85 --max-num-seqs 16 --port 8000 --enforce-eager"
    )
    container_cmd = (
        '["Qwen/Qwen2.5-Coder-7B-Instruct-AWQ","--max-model-len","16384",'
        '"--gpu-memory-utilization","0.90","--max-num-seqs","16",'
        '"--enable-prefix-caching","--enable-sleep-mode"]'
    )
    for shape in (pip_argv, container_cmd):
        monkeypatch.setattr(vllm.contract, "ssh", lambda h, c, timeout=None, r=shape: r)
        assert vllm.launched_width("h")["value"] == 16

    monkeypatch.setattr(vllm.contract, "ssh", lambda h, c, timeout=None: pip_argv)
    agreed = vllm.declared_slots({"max_num_seqs": 16}, "h")
    assert agreed["value"] == 16 and agreed["provenance"] == "observed"

    # The case the whole revision is for: the server is not ours. Neither number
    # is reported, because picking one would be picking which of two
    # contradictory facts about the running server to believe.
    clash = vllm.declared_slots({"max_num_seqs": 8}, "h")
    assert clash["provenance"] == "contradicted" and clash["value"] is None

    monkeypatch.setattr(vllm.contract, "ssh", lambda h, c, timeout=None: "")
    fallback = vllm.declared_slots({"max_num_seqs": 8}, "h")
    assert fallback["value"] == 8 and fallback["provenance"] == "dispatched"


def test_the_serial_guard_matches_a_driver_not_a_mention_of_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E14 is enforced, and its first version refused a correct launch.

    The rigs are measured one at a time because the ramp times requests with
    THIS machine's clock, so a second driver would put its own contention inside
    the throughput curve. The guard was `pgrep -af serving/(run|calibrate).py`,
    which matched the shell that was *editing* the file — its argv contained the
    script's name. A guard that fires on anything merely mentioning the driver
    is a guard that gets switched off.
    """
    launcher = _launcher()
    real_driver = "4242 /repo/.venv/bin/python tools/bench/serving/run.py --config x"
    mere_mention = "4243 /bin/bash -c echo tools/bench/serving/run.py"
    editor = "4244 /usr/bin/vim tools/bench/serving/calibrate.py"

    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(
            stdout="\n".join([real_driver, mere_mention, editor])
        ),
    )
    running = launcher.already_running()
    assert len(running) == 1, running
    assert running[0].startswith("4242")


def test_the_campaign_phases_are_declared_rather_than_typed(
    tmp_path: Path,
) -> None:
    """E15 in code: an order that lives in one person's shell is not reviewable.

    Also pins the two properties the order exists for — sleep first, because it
    is twenty minutes that exercises the whole vLLM path the eleven hours behind
    it depend on; and every D7 item this campaign is responsible for appearing
    exactly once.
    """
    launcher = _launcher()
    names = [name for name, _ in launcher.CAMPAIGN]
    assert names[0].startswith("sleep"), names
    commands = " ".join(command for _, command in launcher.CAMPAIGN)
    for item in ("--phase sleep", "--config", "--phase ramp", "--tokens 475"):
        assert item in commands, item
    # Every phase resumes, or a crash costs the elapsed time rather than nothing.
    assert commands.count("--resume") == len(launcher.CAMPAIGN)
    # Every phase writes into the committed evidence directory (D8: the output
    # is durable and lands somewhere a reader can find it).
    assert commands.count(launcher.EVIDENCE) == len(launcher.CAMPAIGN)


def test_a_crashed_survey_resumes_instead_of_restarting(
    runner: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """D8 made the output durable; nothing read it back.

    Seventeen cells over six hours, one fsynced journal line each — and a
    restart re-measured all of them anyway, because the journal was written and
    never consulted. Durable output nothing resumes from is a record, not a
    checkpoint.

    Simulated by journalling one cell, then re-running with that journal: the
    already-measured entry must not reach the backend a second time.
    """
    table = _stub(runner, monkeypatch)
    config = {
        "hosts": ["h"],
        "backends": ["alpha", "beta"],
        "models": [
            {"label": "one", "backend": "alpha", "id": "m"},
            {"label": "two", "backend": "alpha", "id": "m"},
        ],
    }
    journal = tmp_path / "journal.jsonl"
    runner.run(config, journal=journal)
    assert len(table["alpha"].claimed) == 2
    # Two cells and, since #325, the survey's own phase row.
    assert len(journal.read_text(encoding="utf-8").strip().splitlines()) == 3

    prior = runner.completed(journal)
    assert set(prior) == {"h\x00one", "h\x00two"}

    table["alpha"].claimed.clear()
    result = runner.run(config, journal=tmp_path / "second.jsonl", resume=prior)
    # Nothing was claimed again, and the rows are still in the result.
    assert table["alpha"].claimed == []
    assert sorted(result["hosts"]["h"]["measured"]) == ["one", "two"]


def test_every_survey_journal_row_carries_the_stamp_its_document_carries(
    runner: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#325: one run, one stamp, on every journal row and on `result["run"]`.

    Driven through `main` so `config_sha256` is over the bytes the file held
    -- including a `_`-key that the survey ignores and the digest must not.
    """
    import hashlib

    _stub(runner, monkeypatch)
    config = tmp_path / "survey.json"
    config.write_bytes(
        json.dumps(
            {
                "hosts": ["h"],
                "backends": ["alpha", "beta"],
                "models": [
                    {"label": "one", "backend": "alpha", "id": "m", "_why": "x"},
                    {"label": "two", "backend": "beta", "id": "m"},
                ],
            }
        ).encode("utf-8")
    )
    out = tmp_path / "survey.out.json"
    assert runner.main(["--config", str(config), "--out", str(out)]) == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (tmp_path / "survey.out.json.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(rows) == 3, "two cells and the phase row"
    fields = (
        "commit",
        "tree_dirty",
        "harness_sha256",
        "config_sha256",
        "run_started_at",
    )
    stamp = {k: document["run"][k] for k in fields}
    assert stamp["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert stamp["harness_sha256"] and stamp["run_started_at"]
    for row in rows:
        assert {k: row[k] for k in fields} == stamp
        assert row["started_at"] <= row["ended_at"]
    phase = rows[-1]
    assert phase["metric"] == "phase" and phase["started_at"] == stamp["run_started_at"]
    assert document["run"]["seconds"] == phase["seconds"]


def test_resume_keeps_a_refusal_but_retry_failed_drops_it(tmp_path: Path) -> None:
    """A refusal is an answer, not a gap.

    Re-running it buys the same refusal for the same rig time. `--retry-failed`
    is how a caller says the conditions have changed and it wants another look.
    """
    runner: Any = _by_path("resume_run", SERVING / "run.py")
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"host": "h", "label": "ok-one", "outcome": "ok"})
        + "\n"
        + json.dumps({"host": "h", "label": "bad-one", "outcome": "refused"})
        + "\n"
        # A crash mid-append looks exactly like this, and costs one entry.
        + '{"host": "h", "label": "trunc',
        encoding="utf-8",
    )
    assert set(runner.completed(journal)) == {"h\x00ok-one", "h\x00bad-one"}
    assert set(runner.completed(journal, retry_failed=True)) == {"h\x00ok-one"}


def test_a_torn_line_costs_one_sample_not_two(tmp_path: Path) -> None:
    """A crash mid-append leaves a line without its newline.

    The next append is then concatenated onto it, the PAIR fails to parse, and
    two records are lost — including one written after the crash, by the run
    that was supposed to be recovering. The comment claiming this "re-does
    exactly that one sample" was true of the torn row and false of the row
    after it.
    """
    runner: Any = _by_path("torn_run", SERVING / "run.py")
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"host": "h", "label": "first", "outcome": "ok"})
        + "\n"
        # torn: no trailing newline, which is what a kill mid-write leaves
        + '{"host": "h", "label": "tor',
        encoding="utf-8",
    )
    append = runner._journal(journal)
    append({"host": "h", "label": "after", "outcome": "ok"})

    recovered = runner.completed(journal)
    assert "h\x00first" in recovered, "the record before the tear must survive"
    assert "h\x00after" in recovered, "the record AFTER the tear must survive"
    assert "h\x00tor" not in recovered


def test_retry_failed_does_not_resurrect_a_superseded_measurement(
    tmp_path: Path,
) -> None:
    """A cell measured `ok`, then re-measured `refused`, is refused.

    Filtering during the scan let the older `ok` line survive the newer one, so
    the cell was counted done and the document reported `ok` for a cell whose
    most recent answer was a refusal — the opposite of what the flag is for.
    """
    runner: Any = _by_path("supersede_run", SERVING / "run.py")
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"host": "srv2", "label": "gpt-oss-20b", "outcome": "ok"})
        + "\n"
        + json.dumps({"host": "srv2", "label": "gpt-oss-20b", "outcome": "refused"})
        + "\n",
        encoding="utf-8",
    )
    assert runner.completed(journal)["srv2\x00gpt-oss-20b"]["outcome"] == "refused"
    assert runner.completed(journal, retry_failed=True) == {}


def test_calibrate_retry_failed_does_not_resurrect_a_superseded_sample(
    tmp_path: Path,
) -> None:
    """`run.py`'s DE-D defect, in the module that never got the fix.

    A sample measured once, then re-measured into a failure, is a failure. The
    filter ran DURING the scan here, so the older good line survived the newer
    bad one and `--retry-failed` counted the cell done — skipping the retry it
    was asked for. The twin in `run.py` is pinned by
    `test_retry_failed_does_not_resurrect_a_superseded_measurement`.
    """
    cal: Any = _by_path("supersede_cal", SERVING / "calibrate.py")
    out = tmp_path / "c.jsonl"
    sample = {"phase": "ramp", "host": "srv2", "engine": "vllm", "model": "m"}

    # DE-D's own case, restated with a REFUSAL as the superseding row. A refusal
    # is an answer about this rig at these settings, so a plain resume counts
    # the cell done and only `--retry-failed` re-does it -- which is the
    # ordering property this test was written for.
    out.write_text(
        json.dumps({**sample, "saturation_n": 8})
        + "\n"
        + json.dumps({**sample, "saturation_refused": "the curve never rose"})
        + "\n",
        encoding="utf-8",
    )
    assert len(cal.completed(out)) == 1
    assert cal.completed(out, retry_failed=True) == set()

    # **Changed 2026-08-20 (A6).** This assertion used to read `== 1` with an
    # `error` row superseding the success, which pinned the defect rather than
    # the property: an exception is not an answer, nothing was learned, and the
    # cell is still owed. Counting it done made a cell lost to a transient error
    # unrecoverable by the `--resume` the campaign driver runs. DE-D's ordering
    # is unchanged and is asserted above; what changed is which failures a plain
    # resume forgives.
    out.write_text(
        json.dumps({**sample, "saturation_n": 8})
        + "\n"
        + json.dumps({**sample, "error": "ssh died"})
        + "\n",
        encoding="utf-8",
    )
    assert cal.completed(out) == set()
    assert cal.completed(out, retry_failed=True) == set()


def test_a_journal_reads_one_byte_to_heal_its_tail(tmp_path: Path) -> None:
    """Not the whole file, which is O(n^2) bytes across n appends.

    Both journals fsync per row and an hours-long ramp is the design case named
    in their own docstrings, so the append path is where a long campaign spends
    its I/O. The healing itself still has to work: a torn tail must not have the
    next record concatenated onto it, or the pair fails to parse and two entries
    are lost rather than one.
    """
    for module, path in (("heal_run", "run.py"), ("heal_cal", "calibrate.py")):
        mod: Any = _by_path(module, SERVING / path)
        torn = tmp_path / f"{module}.jsonl"
        torn.write_text('{"host": "srv1", "cut": tr', encoding="utf-8")
        assert mod._ends_mid_line(torn) is True
        torn.write_text('{"host": "srv1"}\n', encoding="utf-8")
        assert mod._ends_mid_line(torn) is False
        torn.write_text("", encoding="utf-8")
        assert mod._ends_mid_line(torn) is False


def test_a_lapsed_coresidency_is_counted_not_only_recorded(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal list is what a consumer counts; this path left it empty.

    Four refusal paths set a row-level refusal and three of them also appended
    to `result["refusals"]`. The one that did not was the post-ramp co-residency
    lapse — so the entry whose entire purpose is co-residency was the entry
    whose failure the top-level summary reported as no failure at all.
    """
    table = _stub(runner, monkeypatch)
    # Resident when the claim looks, gone by the time the ramp ends: BL-6, an
    # ollama neighbour pinned with `keep_alive: -1` that the server evicts.
    monkeypatch.setattr(table["alpha"], "residents", lambda host: [], raising=False)
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "collect": {},
            "models": [
                {
                    "label": "a",
                    "backend": "alpha",
                    "id": "m",
                    "family": "f",
                    "coresident_with": ["neighbour"],
                }
            ],
        }
    )
    row = result["hosts"]["h"]["measured"]["a"]
    assert row["outcome"] == "ramp_failed"
    assert row["refusal"]["stage"] == "post-ramp"
    counted = [r for r in result["refusals"] if r.get("stage") == "post-ramp"]
    assert counted, "the lapse set row['refusal'] and was never counted"
    assert "coresidency lapsed" in counted[0]["why"]
    assert counted[0]["label"] == "a"


def test_the_post_ramp_coresidency_verdict_says_where_each_neighbour_sat(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#335 box 5, on the AFTER side — `held` is a verdict on a name list.

    The lapse check above catches a neighbour that LEFT. It cannot catch one
    that stayed and spilled: an evicted neighbour disappears from the name
    list, and a spilled one is still listed, under its own name, with its full
    `size` beside a `size_vram` nobody read. So `coresidency_after.held` reads
    `true` for a neighbour sitting 93% on the CPU — the same silent nothing at
    the other end of the measurement.

    Recorded and not gated, for the reason the claim-side record is: this
    campaign is a map of where things land, and a run that refused a spill
    would refuse its own result.
    """
    table = _stub(runner, monkeypatch)
    monkeypatch.setattr(
        table["alpha"], "residents", lambda host: ["m", "neighbour"], raising=False
    )
    monkeypatch.setattr(
        table["alpha"],
        "placements",
        lambda host: [
            {"name": "m", "size": 1000, "size_vram": 1000, "fraction": 1.0},
            {"name": "neighbour", "size": 1000, "size_vram": 68, "fraction": 0.068},
        ],
        raising=False,
    )
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "collect": {},
            "models": [
                {
                    "label": "a",
                    "backend": "alpha",
                    "id": "m",
                    "family": "f",
                    "coresident_with": ["neighbour"],
                }
            ],
        }
    )
    after = result["hosts"]["h"]["measured"]["a"]["coresidency_after"]
    assert after["held"] is True and after["missing"] == []
    where = {row["name"]: row["fraction"] for row in after["placements"]}
    assert where == {"m": 1.0, "neighbour": 0.068}, (
        "the verdict is recorded beside where each resident actually sat, or "
        "it is a claim about names"
    )


def test_a_backend_that_cannot_report_placement_writes_null_and_not_a_number(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent is not zero and it is not one.

    Placement is a fact only an engine that reports it can state — `vllm.py`
    has no `residents` at all today, let alone this. The field is present on
    every row so a reader never has to ask whether it was looked for, and it is
    `null` where it was not, because a default here would be a measurement
    nobody took.
    """
    table = _stub(runner, monkeypatch)
    monkeypatch.setattr(
        table["alpha"], "residents", lambda host: ["m", "neighbour"], raising=False
    )
    assert not hasattr(table["alpha"], "placements")
    result = runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "collect": {},
            "models": [
                {
                    "label": "a",
                    "backend": "alpha",
                    "id": "m",
                    "family": "f",
                    "coresident_with": ["neighbour"],
                }
            ],
        }
    )
    after = result["hosts"]["h"]["measured"]["a"]["coresidency_after"]
    assert after["held"] is True
    assert after["placements"] is None


def test_a_resumed_survey_still_reports_its_refusals(
    runner: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deliverable must not claim a run refused nothing when it refused.

    The resume skip returned before any refusal was appended, and the survey is
    resumed by design — so `d7-survey.json` would have carried `refusals: []`
    for a run that refused. D8 decided a campaign be countable rather than read.
    """
    table = _stub(runner, monkeypatch)

    def _explode(*a: Any, **k: Any) -> None:
        raise runner.contract.NotCleanError("no")

    monkeypatch.setattr(table["alpha"], "claim", _explode)
    config = {
        "hosts": ["h"],
        "backends": ["alpha", "beta"],
        "models": [{"label": "a", "backend": "alpha", "id": "m"}],
    }
    journal = tmp_path / "j.jsonl"
    first = runner.run(config, journal=journal)
    assert len(first["refusals"]) == 1

    resumed = runner.run(config, resume=runner.completed(journal))
    assert resumed["hosts"]["h"]["measured"]["a"]["outcome"] == "launch_failed"
    assert len(resumed["refusals"]) == 1, resumed["refusals"]
    assert resumed["refusals"][0]["resumed"] is True


def test_an_entry_key_the_survey_reads_nowhere_is_refused(
    runner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`expect` and `placement` were whitelisted; the entry itself was not.

    Mistype `coresident_with` and the co-residency entry measures SOLO under a
    label that says otherwise, with `coresidency_arranged: null` rather than a
    refusal — the same silent nothing E6 was written against, one level up.
    """
    _stub(runner, monkeypatch)
    with pytest.raises(runner.contract.NotCleanError, match="reads nowhere"):
        runner.run(
            {
                "hosts": ["h"],
                "backends": ["alpha", "beta"],
                "models": [
                    {
                        "label": "a",
                        "backend": "alpha",
                        "id": "m",
                        "coresident_wth": ["other"],
                    }
                ],
            }
        )


# --- #352: the post-state container clause, narrowed and then recorded -------
#
# The run contract's second post-state clause read "no container of ours", and
# the reading beneath it was `docker ps`, which lists RUNNING containers only.
# Phase 0 ended with every post-state reading clean and srv2 holding
# `mcgyvr-vllm  Exited (1)`: the clause asserted a property wider than the one
# it tested. The clause is narrowed to "running" — owner's ruling, 2026-08-23,
# `docs/run-contract-2026-08-22.md` §4 — and the stopped container is recorded
# instead of required absent, because it is where a failed launch's reason
# lives. The checks below hold both halves against the commands the module
# actually sends, not against its source text.

#: srv2's leftover, in the shape `docker ps -a` printed it on 2026-08-23.
_STOPPED_CONTAINER = "mcgyvr-vllm Exited (1) 4 hours ago"

#: The last line of a vLLM launch that died allocating KV cache — the #354
#: refusal reason that had to be recovered by re-running a cell, because the
#: next cell's `docker rm -f` destroyed the container holding it.
_OOM_TAIL = (
    "ERROR [core.py:770] EngineCore failed to start.\n"
    "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 256.00 MiB\n"
)


def _vllm_stopped_box(
    monkeypatch: pytest.MonkeyPatch, name: str = "stopped_vllm"
) -> tuple[Any, Any, list[str]]:
    """The backend on a host whose only container of ours has exited.

    The fake host is the discriminator, and that is deliberate: it answers the
    `-a` reading with the exited container and every running-only reading with
    nothing, which is what docker does. A fixture that answered both the same
    way would let a check pass on a string rather than on a behaviour.
    """
    vllm: Any = _by_path(name, SERVING / "backends" / "vllm.py")
    sent: list[str] = []

    def _ssh(host: str, command: str, timeout: float | None = None) -> str | None:
        sent.append(command)
        if "docker ps" in command:
            if " -a " in command:
                return _STOPPED_CONTAINER
            return "0" if "wc -l" in command else ""
        if command.startswith("docker inspect"):
            return '["--max-num-seqs", "8"] ["VLLM_SERVER_DEV_MODE=1"]'
        if "pgrep" in command:
            return "0"
        if "nvidia-smi" in command:
            return "1"
        return ""

    monkeypatch.setattr(vllm.contract, "ssh", _ssh)
    return vllm, _ssh, sent


def test_a_stopped_container_of_ours_is_in_the_record_and_out_of_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#352's two halves, on one host, in one check because they are one ruling.

    The record must see it: a container named `mcgyvr-vllm` sitting `Exited (1)`
    on the box is ours, and an operator told `own_containers_remaining: 0` who
    then finds it has been answered truthfully and not asked-truthfully.

    The gate must not act on it: `released` is the orchestrator's only exclusion
    gate, and what it decides is whether anything of ours still holds the card.
    A stopped container holds none of it. Widening the gate instead would have
    made the contract's cheapest guarantee turn on a state that costs nothing.
    """
    vllm, _, _sent = _vllm_stopped_box(monkeypatch)

    record = vllm.readings("h")["containers"]["stdout"]
    assert "mcgyvr-vllm" in record and "Exited" in record, (
        "the record cannot see a container of ours that exited — the exact "
        "state phase 0 left on srv2 and reported as clean"
    )

    released = vllm.release("h")
    assert released["own_containers_remaining"] == 0
    assert released["released"] is True, (
        "a stopped container held the gate shut: the clause was narrowed to "
        "running, not the gate widened to match the clause"
    )


def test_canary_the_running_only_reading_calls_the_same_host_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shown to reject — the check above passes because of `-a` and nothing else.

    Asserting that `readings` contains the string `-a` would confirm the
    thermometer was installed (`tests/test_sink_conformance.py:11-18`). This
    puts the pre-fix question to the same host and shows the answer differs:
    without `-a` the exited container reads as absent, which is the defect
    itself rather than a difference in phrasing.
    """
    vllm, ssh, sent = _vllm_stopped_box(monkeypatch, name="canary_stopped_vllm")
    vllm.readings("h")
    listings = [c for c in sent if c.startswith("docker ps") and "--format" in c]
    assert len(listings) == 1, sent
    assert " -a " in listings[0]
    assert ssh("h", listings[0].replace("docker ps -a ", "docker ps ")) == "", (
        "this host answers the running-only reading the same way, so the check "
        "above would still pass with the fix reverted"
    )


def test_the_width_read_off_a_container_ignores_the_one_that_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`-a` belongs in the record and in exactly one place in this module.

    `launched_width` reads `--max-num-seqs` off a container's own argv, and
    `docker ps -a` lists the newest first — so a sweep that added `-a` here too
    would answer with the width of the run that FAILED, which is the one number
    this reading exists to get right. It answers `None` with its source instead,
    which is ADR-0027 D2's shape: a reading that was not taken says so.
    """
    vllm, _, sent = _vllm_stopped_box(monkeypatch, name="width_stopped_vllm")
    width = vllm.launched_width("h")
    assert width == {"value": None, "source": None}, width
    container_reads = [c for c in sent if c.startswith("docker ps")]
    assert container_reads and not any(" -a " in c for c in container_reads), (
        "the width reading took `-a` and would answer off the exited container"
    )


def _vllm_launch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    binary: str,
    image: str,
    log: str | None,
    ready: str = "timeout code=000 mib=0",
    name: str = "launch_vllm",
) -> tuple[Any, list[str]]:
    """The backend on a host where a launch never becomes ready."""
    vllm: Any = _by_path(name, SERVING / "backends" / "vllm.py")
    sent: list[str] = []

    def _ssh(host: str, command: str, timeout: float | None = None) -> str | None:
        sent.append(command)
        if "command -v vllm" in command:
            return binary
        if "docker images -q" in command:
            return image
        if command.startswith("docker logs") or command.startswith("tail -n"):
            return log
        # Before the bare `nvidia-smi` branch: the readiness loop calls
        # nvidia-smi inside itself, so a fixture ordered the other way answers
        # the loop with a card reading and never returns `ready` at all.
        if command.startswith("for i in $(seq"):
            return ready
        if "memory.total" in command:
            return "6144, 1024"
        if "nvidia-smi" in command:
            return "1024"
        if "pgrep" in command:
            return "0"
        if "docker ps" in command:
            return "0" if "wc -l" in command else ""
        return "launched"

    monkeypatch.setattr(vllm.contract, "ssh", _ssh)
    return vllm, sent


@pytest.mark.parametrize(
    ("binary", "image", "how", "read"),
    [
        ("/usr/local/bin/vllm", "", "pip", "tail -n 40 /tmp/vllm-serving.log"),
        ("", "sha256:c0ffee", "docker", "docker logs --tail 40 mcgyvr-vllm"),
    ],
)
def test_a_launch_that_never_became_ready_carries_the_log_the_next_cell_destroys(
    monkeypatch: pytest.MonkeyPatch, binary: str, image: str, how: str, read: str
) -> None:
    """#352's third box, and the one that cost rig time.

    The refusal used to tell the reader to go and look at `docker logs
    mcgyvr-vllm` or `/tmp/vllm-serving.log`. Both are gone by the time anybody
    does: the next cell opens with `docker rm -f mcgyvr-vllm` on the container
    rig, and the pip launch redirects `> /tmp/vllm-serving.log`, which truncates
    the previous cell's rather than appending to it. The 2026-08-23 campaign ran
    a cell byte-identically a second time to recover a reason this call keeps.

    Both launchers, because the pip rig loses it the same way and that had not
    been noticed — the instruction named two places and neither survived.
    """
    vllm, sent = _vllm_launch(
        monkeypatch,
        binary=binary,
        image=image,
        log=_OOM_TAIL,
        name=f"launch_{how}_vllm",
    )
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm._start(
            "h",
            "m",
            # A fraction rather than bytes, so #354's pre-check has nothing
            # to weigh and this stays a test about the launch failing.
            {"max_model_len": 2048, "max_num_seqs": 8, "gpu_memory_utilization": 0.5},
        )

    message = str(raised.value)
    assert "torch.OutOfMemoryError" in message, (
        "the refusal names where to look instead of carrying what was there"
    )
    assert repr(how) in message, "the refusal does not say which launcher ran"
    assert any(c.startswith(read) for c in sent), f"{read!r} was never read: {sent}"


def test_the_engine_log_is_read_only_where_it_is_about_to_be_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A launch that came up pays no ssh for a log nobody will read.

    The reading is on the failure path because that is the only path where
    something is about to be destroyed. Put at the end of every launch it would
    be one more round trip per cell against a file that will still be there.
    """
    vllm, sent = _vllm_launch(
        monkeypatch,
        binary="/usr/local/bin/vllm",
        image="",
        log=_OOM_TAIL,
        ready="ready",
        name="ready_launch_vllm",
    )
    started = vllm._start(
        "h",
        "m",
        # A fraction rather than bytes, so #354's pre-check has nothing
        # to weigh and this stays a test about the launch failing.
        {"max_model_len": 2048, "max_num_seqs": 8, "gpu_memory_utilization": 0.5},
    )
    assert started["restarted"] is True
    assert not [c for c in sent if c.startswith(("docker logs", "tail -n"))], sent


def test_a_log_the_host_would_not_give_up_is_a_reason_and_not_a_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0027 D2 on the failure path: the refusal survives the reading failing.

    `contract.ssh` answers `None` for a host it could not reach, and a host that
    will not answer is exactly where a launch fails. A reading that could not be
    taken must not replace the refusal that was already true — the launch failed
    either way, and that is what is reported.
    """
    vllm, _ = _vllm_launch(
        monkeypatch,
        binary="/usr/local/bin/vllm",
        image="",
        log=None,
        name="mute_launch_vllm",
    )
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm._start(
            "h",
            "m",
            # A fraction rather than bytes, so #354's pre-check has nothing
            # to weigh and this stays a test about the launch failing.
            {"max_model_len": 2048, "max_num_seqs": 8, "gpu_memory_utilization": 0.5},
        )
    message = str(raised.value)
    assert "did not reach health" in message, "the refusal lost its own reason"
    assert "the engine's own log was not read" in message, (
        "an unread log is a silence in the record rather than a stated gap"
    )


def test_the_engine_log_goes_through_the_same_scrubber_as_every_other_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This text reaches the run record through the exception message.

    A vLLM traceback quotes the argv and the paths beneath it, which is where
    the home directory naming a user and a published token shape both sit. The
    guarantee claimed is the one every host reading here carries and not a
    stronger one: an arbitrary `KEY=value` an operator invented is redacted by
    nothing in this tree, and this check does not pretend otherwise.
    """
    vllm, _ = _vllm_launch(
        monkeypatch,
        binary="/usr/local/bin/vllm",
        image="",
        log=(
            "loading /home/adaramir/.cache/huggingface/blob\n"
            "--api-key sk-abcdefghijklmnopqrstuvwx\n"
        ),
        name="scrub_launch_vllm",
    )
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm._start(
            "h",
            "m",
            # A fraction rather than bytes, so #354's pre-check has nothing
            # to weigh and this stays a test about the launch failing.
            {"max_model_len": 2048, "max_num_seqs": 8, "gpu_memory_utilization": 0.5},
        )
    message = str(raised.value)
    assert "sk-abcdefghijklmnopqrstuvwx" not in message
    assert "/home/adaramir" not in message
    assert "redacted" in message, "the tail reached the record without a scrub"
