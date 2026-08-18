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
    ) -> dict[str, Any]:
        self.claimed.append(model)
        return {
            "backend": self.NAME,
            "model": model,
            "verified": True,
            "checks": {"weights": {"weights_sha256": self.digest}},
        }

    def describe(self, host: str, base: str, model: str) -> dict[str, Any]:
        return {"backend": self.NAME, "capture": {"model_sha256": f"{self.NAME}-sha"}}


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
        runner.contract, "ramp", lambda *a, **k: {"knee": 4, "levels": []}
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


def test_a_knee_that_misses_its_expectation_is_flagged(
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
    assert measured["knee"] == 4
    assert measured["expected"] == 2
    assert measured["matches_expected"] is False


# --- the shared pieces ------------------------------------------------------


def test_a_width_is_reported_only_when_both_statistics_agree(contract: Any) -> None:
    """The correction: a throughput plateau alone is not a batch width.

    Real measurements, 2026-08-18. The vLLM server was launched with
    `--max-num-seqs 8` and both statistics land on 8. The two ollama servers
    were configured one slot apart — `-np 2` and `-np 1` — and the throughput
    plateau returns **6 for both**, so on its own it could not distinguish the
    two configurations it was meant to measure. Requiring the latency plateau to
    agree turns that into `None`, which is the honest reading: ollama shows no
    latency plateau at any width because it is not batching in the way that
    produces one.
    """

    def rows(triples: list[tuple[int, float, float]]) -> list[dict[str, Any]]:
        return [
            {"n": n, "tokens_per_s": t, "latency_mean_s": lat} for n, t, lat in triples
        ]

    vllm = rows(
        [
            (1, 42.6, 3.004),
            (2, 27.6, 9.277),
            (3, 40.8, 9.377),
            (4, 54.4, 9.398),
            (6, 80.5, 9.525),
            (8, 106.5, 9.596),
            (12, 80.9, 12.739),
            (16, 106.8, 14.418),
            (24, 107.3, 19.133),
        ]
    )
    assert contract.knee(vllm) == 8, "the configured --max-num-seqs"

    ollama_two = rows(
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
    ollama_one = rows(
        [
            (2, 108.1, 1.877),
            (3, 113.1, 2.398),
            (4, 116.5, 2.918),
            (6, 120.2, 3.938),
            (8, 122.9, 4.892),
            (12, 124.3, 6.949),
            (16, 125.1, 8.976),
            (24, 125.5, 13.161),
        ]
    )
    assert contract.knee(ollama_two) is None
    assert contract.knee(ollama_one) is None

    # The reason the old rule was unsafe: identical answer, different servers.
    assert (
        contract.readings(ollama_two)["throughput_plateau_n"]
        == contract.readings(ollama_one)["throughput_plateau_n"]
        == 6
    )


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
    # The backend's OWN contract, not the fixture's: an earlier test clears the
    # shared module slot to prove each backend loads alone, so a later fresh
    # load builds a different `NotCleanError` class object and an identity check
    # against the fixture's copy would miss it.
    with pytest.raises(backend.contract.NotCleanError, match="not a usable environ"):
        backend._start("h", "m", {"env": {"A; touch /tmp/x; B": "1"}})


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
    for module in (contract, ollama.contract, vllm.contract):
        monkeypatch.setattr(module, "ssh", lambda h, c, timeout=None: leak)
    monkeypatch.setattr(vllm, "launcher", lambda host: "pip")
    monkeypatch.setattr(
        vllm.contract, "get_json", lambda url, timeout=None: {"vllm_config": leak}
    )

    written = json.dumps(
        {
            "snapshot": contract.snapshot("h"),
            "ollama_readings": ollama.readings("h"),
            "ollama_server": ollama._server("h"),
            "vllm_readings": vllm.readings("h"),
            "vllm_launch": vllm._start("h", "m", {"env": {"HF_TOKEN": token}}),
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
