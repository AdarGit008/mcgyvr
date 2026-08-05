"""Detection runs on a stranger's machine, which is the one we cannot see.

The properties that matter are therefore about behaviour under absence and
under failure, not about what this particular machine reports. Nothing here
touches the network or a real subprocess: every probe is stubbed, so the
suite asserts on the code's handling rather than on the runner's hardware.
"""

from __future__ import annotations

import json
import re
import urllib.error
from typing import Any

import pytest

from mcgyvr import detect as detect_module
from mcgyvr.detect import (
    DEFAULT_PROBE_TARGETS,
    PORT_CONVENTIONS,
    ProbeTarget,
    detect,
    detect_docker,
    detect_gpus,
    probe,
    probe_all,
    targets_for,
)

NVIDIA_SMI = "NVIDIA GeForce RTX 3060, 12288\n"
NVIDIA_SMI_TWO = "NVIDIA GeForce RTX 3060, 12288\nNVIDIA GeForce GTX 1660 SUPER, 6144\n"

OLLAMA_TAGS = {"models": [{"name": "qwen2.5-coder:7b"}, {"name": "qwen2.5-coder:3b"}]}
OPENAI_MODELS = {"data": [{"id": "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ"}]}


def stub_run(monkeypatch: pytest.MonkeyPatch, table: dict[str, str | None]) -> None:
    """Replace command execution with a lookup keyed on the binary name."""
    monkeypatch.setattr(
        detect_module, "_run", lambda cmd: table.get(cmd[0]), raising=True
    )


def stub_http(monkeypatch: pytest.MonkeyPatch, table: dict[str, Any]) -> None:
    """Replace the HTTP probe with a lookup keyed on the full URL."""
    monkeypatch.setattr(
        detect_module, "_get_json", lambda url, timeout: table.get(url), raising=True
    )


# --- absence is an outcome, not an error ---------------------------------


def test_a_bare_machine_detects_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No GPU, no Docker, no backend. This is a supported install."""
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {})
    found = detect()
    assert found.has_gpu is False
    assert found.largest_vram_gb is None
    assert found.backends == ()
    assert found.docker is False


def test_absence_is_explained_rather_than_left_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent zero reads as 'absent' when it may mean 'unknown'."""
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {})
    notes = " ".join(detect().notes)
    assert "nvidia-smi" in notes, "an undetected GPU must say what was tried"
    assert "AMD" in notes, "and must name the machines it cannot speak for"
    assert "No local backend answered" in notes
    assert "temp directory" in notes, "a missing Docker must state what it costs"


def test_no_gpu_still_reports_fallback_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {})
    found = detect()
    assert found.cpu_count is None or found.cpu_count > 0


# --- every fact carries how it was found ---------------------------------


def test_every_reported_fact_has_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_run(
        monkeypatch,
        {"nvidia-smi": NVIDIA_SMI, "docker": "27.1.1\n"},
    )
    stub_http(monkeypatch, {"http://localhost:11434/api/tags": OLLAMA_TAGS})

    found = detect()
    assert found.provenance["gpu:NVIDIA GeForce RTX 3060"].startswith("nvidia-smi")
    assert "11434" in found.provenance["backend:ollama"]
    assert found.provenance["docker"] == "docker info reported server 27.1.1"
    assert found.provenance["cpu_count"] == "os.cpu_count()"
    if found.ram_gb is not None:
        assert found.provenance["ram_gb"]


def test_a_fact_that_is_absent_carries_no_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance describes what was found, so it must not claim a non-fact."""
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {})
    found = detect()
    assert not any(k.startswith("gpu:") for k in found.provenance)
    assert not any(k.startswith("backend:") for k in found.provenance)
    # docker is a real false, not an absent value, so it keeps its provenance
    assert "docker" in found.provenance


# --- GPU ------------------------------------------------------------------


def test_nvidia_smi_output_becomes_gpus(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_run(monkeypatch, {"nvidia-smi": NVIDIA_SMI})
    gpus, notes = detect_gpus()
    assert notes == ()
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 3060"
    assert gpus[0].vram_gb == 12.0


def test_largest_vram_is_not_a_sum(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model runs on one card: two 6 GB cards are not one 12 GB decision."""
    stub_run(monkeypatch, {"nvidia-smi": NVIDIA_SMI_TWO})
    stub_http(monkeypatch, {})
    found = detect()
    assert len(found.gpus) == 2
    assert found.largest_vram_gb == 12.0


def test_garbage_from_nvidia_smi_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {"nvidia-smi": "this is not, csv\nnor, is-this\n"})
    gpus, notes = detect_gpus()
    assert gpus == ()
    assert notes and "reported no device" in notes[0]


# --- backends -------------------------------------------------------------


def test_ollama_listing_is_read_in_its_own_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_http(monkeypatch, {"http://localhost:11434/api/tags": OLLAMA_TAGS})
    found = probe(ProbeTarget("ollama", "http://localhost:11434", "ollama"))
    assert found is not None
    assert found.models == ("qwen2.5-coder:7b", "qwen2.5-coder:3b")
    assert found.has_model("qwen2.5-coder:7b")
    assert not found.has_model("qwen2.5-coder:14b")


def test_openai_listing_is_read_in_its_own_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_http(monkeypatch, {"http://localhost:8000/v1/models": OPENAI_MODELS})
    found = probe(ProbeTarget("vllm", "http://localhost:8000", "openai"))
    assert found is not None
    assert found.models == ("Qwen/Qwen2.5-Coder-14B-Instruct-AWQ",)


def test_an_endpoint_that_does_not_answer_is_simply_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_http(monkeypatch, {})
    assert probe(ProbeTarget("vllm", "http://localhost:8000", "openai")) is None


def test_a_malformed_listing_is_a_backend_with_no_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It answered, so it exists; it just told us nothing we can bind."""
    stub_http(monkeypatch, {"http://localhost:8000/v1/models": {"data": "nonsense"}})
    found = probe(ProbeTarget("vllm", "http://localhost:8000", "openai"))
    assert found is not None and found.models == ()


def test_probes_do_not_stop_at_the_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_http(monkeypatch, {"http://localhost:1234/v1/models": OPENAI_MODELS})
    found = probe_all(DEFAULT_PROBE_TARGETS)
    assert [b.name for b in found] == ["lmstudio"]


def test_every_endpoint_is_probed_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wall clock must be one timeout, not one per endpoint."""
    seen: list[str] = []

    def slow(url: str, timeout: float) -> Any:
        seen.append(url)
        return None

    monkeypatch.setattr(detect_module, "_get_json", slow, raising=True)
    probe_all(DEFAULT_PROBE_TARGETS)
    assert len(seen) == len(DEFAULT_PROBE_TARGETS), "every endpoint must be tried"


def test_a_hanging_endpoint_cannot_hang_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """urlopen's timeout is the only thing standing between us and a hang."""
    captured: list[float] = []

    def record(url: str, timeout: float) -> Any:
        captured.append(timeout)
        return None

    monkeypatch.setattr(detect_module, "_get_json", record, raising=True)
    probe_all(DEFAULT_PROBE_TARGETS)
    assert captured and all(t > 0 for t in captured), "no probe may be unbounded"


def test_models_present_spans_every_reachable_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {})
    stub_http(
        monkeypatch,
        {
            "http://localhost:11434/api/tags": OLLAMA_TAGS,
            "http://localhost:8000/v1/models": OPENAI_MODELS,
        },
    )
    found = detect()
    assert found.models_present() == {
        "qwen2.5-coder:7b",
        "qwen2.5-coder:3b",
        "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ",
    }
    assert found.backend("ollama") is not None
    assert found.backend("tgi") is None


# --- docker ---------------------------------------------------------------


def test_docker_absent_from_path_is_false_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcgyvr.detect.shutil.which", lambda _: None)
    present, how = detect_docker()
    assert present is False
    assert "not on PATH" in how


def test_docker_installed_but_dead_is_false_with_a_different_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stopped daemon is not the same failure as an uninstalled Docker."""
    monkeypatch.setattr("mcgyvr.detect.shutil.which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(detect_module, "_run", lambda cmd: None, raising=True)
    present, how = detect_docker()
    assert present is False
    assert "daemon did not answer" in how


# --- the real HTTP path ---------------------------------------------------


def test_every_transport_failure_reads_as_nothing_listening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused, timed out, or not-JSON all mean the same thing to the caller."""

    def raiser(boom: BaseException) -> Any:
        def raise_it(*_args: Any, **_kwargs: Any) -> Any:
            raise boom

        return raise_it

    for failure in (
        urllib.error.URLError("refused"),
        TimeoutError("timed out"),
        json.JSONDecodeError("nope", "", 0),
    ):
        monkeypatch.setattr("mcgyvr.detect.urllib.request.urlopen", raiser(failure))
        assert detect_module._get_json("http://localhost:1/x", 0.01) is None


# --- the host is an input, not a literal (#161) ---------------------------


def test_the_default_sweep_is_localhost_and_unchanged() -> None:
    """A single-machine install must take exactly the path it always took."""
    assert targets_for() == DEFAULT_PROBE_TARGETS
    assert all(t.host == "localhost" for t in DEFAULT_PROBE_TARGETS)
    assert all("localhost" in t.base_url for t in DEFAULT_PROBE_TARGETS)
    assert [t.name for t in DEFAULT_PROBE_TARGETS] == [
        name for name, *_ in PORT_CONVENTIONS
    ], "bare names, as before — nothing is qualified on a one-host sweep"


def test_a_named_host_is_swept_on_every_port_convention() -> None:
    targets = targets_for(["srv1"])
    assert len(targets) == len(PORT_CONVENTIONS)
    assert {t.host for t in targets} == {"srv1"}
    assert "http://srv1:11434" in {t.base_url for t in targets}
    assert "http://srv1:8000" in {t.base_url for t in targets}


def test_a_single_named_host_still_gets_bare_names() -> None:
    """One machine is unambiguous, whichever machine it is."""
    assert [t.name for t in targets_for(["srv1"])] == [
        name for name, *_ in PORT_CONVENTIONS
    ]


def test_two_hosts_qualify_names_so_sources_cannot_collide() -> None:
    """Both rigs run ollama on 11434. Unqualified, one would overwrite the other.

    The config maps sources by name, so a collision here is not a cosmetic
    problem: it is one rig silently disappearing from the ladder.
    """
    targets = targets_for(["srv1", "srv2"])
    names = [t.name for t in targets]
    assert len(names) == len(set(names)), "every candidate source is distinctly named"
    assert "srv1_ollama" in names
    assert "srv2_ollama" in names


def test_qualifying_a_name_never_changes_what_the_backend_is() -> None:
    """`requires_backend` in the table matches the kind, not the config name.

    A model measured on ollama is measured on ollama whether the source is
    called `ollama` or `srv2_ollama`. Conflating the two would withhold every
    backend-pinned model the moment a second host was named.
    """
    for target in targets_for(["srv1", "srv2"]):
        assert target.kind in {name for name, *_ in PORT_CONVENTIONS}
        assert target.name.endswith(target.kind)


def test_an_address_survives_becoming_a_config_key() -> None:
    """A tailnet address is a name someone edits by hand in YAML."""
    names = [t.name for t in targets_for(["100.69.72.51", "srv1"])]
    assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", n) for n in names), names


def test_naming_one_host_twice_probes_it_once() -> None:
    assert len(targets_for(["srv1", "srv1"])) == len(PORT_CONVENTIONS)
    assert [t.name for t in targets_for(["srv1", "srv1"])] == [
        name for name, *_ in PORT_CONVENTIONS
    ], "a duplicate must not be read as two hosts and trigger qualification"


def test_a_remote_backend_is_not_reported_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {"http://srv2:11434/api/tags": OLLAMA_TAGS})
    found = detect(targets_for(["srv2"]))
    assert found.backends
    assert found.has_remote_backend
    assert found.hosts_answering == ("srv2",)
    assert all(not b.is_local for b in found.backends)


def test_a_tunnelled_rig_named_localhost_is_treated_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locality is the name the user gave, not what it resolves to.

    An SSH tunnel makes a remote rig answer on localhost, and everything else
    here is already treating it as local. Claiming otherwise would be a
    distinction nothing acts on.
    """
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {"http://localhost:11434/api/tags": OLLAMA_TAGS})
    found = detect(targets_for(["localhost"]))
    assert not found.has_remote_backend


def test_nothing_answering_anywhere_names_the_flag_that_widens_the_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {})
    found = detect(targets_for(["srv1", "srv2"]))
    joined = " ".join(found.notes)
    assert "--host" in joined
    assert "http://srv1:11434" in joined, "and says exactly what was tried"


# --- asked one way, dispatched another (#164) ----------------------------


def test_ollama_is_asked_natively_and_bound_compatibly() -> None:
    """The two protocols are used for the thing each is better at.

    `/api/tags` is the only listing that includes models pulled but not
    loaded, which is the inventory a proposal needs. `/api/generate` is the
    path CAV-01 measured at 32.3% against a true 84.1%.
    """
    ollama = next(t for t in targets_for() if t.kind == "ollama")
    assert ollama.api == "ollama", "detection still asks natively"
    assert ollama.binds_as == "openai", "dispatch does not"


def test_every_other_backend_is_bound_as_it_is_asked() -> None:
    """Only Ollama has two doors. A split everywhere would be noise."""
    for target in targets_for():
        if target.kind == "ollama":
            continue
        assert target.binds_as == target.api


def test_a_probed_ollama_reports_both_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {"http://localhost:11434/api/tags": OLLAMA_TAGS})
    found = detect()
    backend = found.backend("ollama")
    assert backend is not None
    assert backend.models, "the native listing is what enumerates pulled models"
    assert backend.bound_on_another_protocol
    assert backend.binds_as == "openai"


def test_a_backend_bound_as_it_answered_is_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag exists to explain a surprise; firing always would explain nothing."""
    stub_run(monkeypatch, {})
    stub_http(monkeypatch, {"http://localhost:8000/v1/models": OPENAI_MODELS})
    found = detect()
    backend = found.backend("vllm")
    assert backend is not None
    assert not backend.bound_on_another_protocol
