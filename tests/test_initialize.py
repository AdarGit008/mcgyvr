"""`mcgyvr init` is the first thing a stranger runs.

The v1 release criterion is written around it: clean machine, no key, no
Docker, and the result must be a config that supports a real local task. So
the central test here is exactly that machine — and the generated file is
fed back through the real loader, because "it looks right" is not the claim
being made.

Detection is injected rather than performed, so these run identically on a
machine with no GPU and on one with four.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcgyvr.capability import load as load_table
from mcgyvr.config import load as load_config
from mcgyvr.config import parse as parse_config
from mcgyvr.detect import Backend, Detection, Gpu
from mcgyvr.initialize import InitError, _sources_for, build, initialize, render
from mcgyvr.propose import propose

BARE = Detection(
    gpus=(),
    cpu_count=4,
    ram_gb=16.0,
    backends=(),
    docker=False,
    provenance={"docker": "docker is not on PATH"},
    notes=("GPU: not determined — nvidia-smi is absent or failed.",),
)

SMALL_RIG = Detection(
    gpus=(Gpu("NVIDIA GeForce GTX 1660 SUPER", 6.0, "nvidia-smi"),),
    cpu_count=6,
    ram_gb=32.0,
    backends=(
        Backend(
            "ollama", "http://localhost:11434", "ollama", ("qwen2.5-coder:3b",), "probe"
        ),
        Backend("llama-server", "http://localhost:8080", "openai", (), "probe"),
    ),
    docker=True,
    provenance={"docker": "docker info reported server 27.1.1"},
)

KEYLESS_RIG = Detection(
    gpus=(Gpu("NVIDIA GeForce RTX 3060", 12.0, "nvidia-smi"),),
    cpu_count=8,
    ram_gb=32.0,
    backends=(
        Backend(
            "ollama", "http://localhost:11434", "ollama", ("qwen2.5-coder:7b",), "probe"
        ),
    ),
    docker=False,
    provenance={"docker": "docker is not on PATH"},
    notes=("Sandbox falls back to a temp directory (docker is not on PATH).",),
)


@pytest.fixture
def table():  # type: ignore[no-untyped-def]
    return load_table()


# --- the v1 release criterion --------------------------------------------


def test_clean_machine_no_key_no_docker_gets_a_working_local_config(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    path = tmp_path / "mcgyvr.yaml"
    result = initialize(path, detection=KEYLESS_RIG, table=table)
    assert result.created and result.written

    config = load_config(path)
    assert config.is_local_only, "no key must be needed to run"
    assert config.ladder.tiers, "a real local task needs at least one rung"
    assert config.data["sandbox"]["mode"] == "tempdir", "no Docker → the weaker mode"


def test_the_generated_file_loads_without_edits(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """The whole point: init's output is the loader's input, unmodified."""
    for name, detection in (("small", SMALL_RIG), ("keyless", KEYLESS_RIG)):
        path = tmp_path / f"{name}.yaml"
        initialize(path, detection=detection, table=table)
        config = load_config(path)
        assert config.data["version"] == 1


def test_a_machine_with_no_backend_refuses_rather_than_writing(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """No GPU, no backend, nothing to dispatch to.

    A file that dispatches nowhere is not a head start — it is a
    misconfiguration that surfaces later and further from its cause. So init
    writes nothing and says what to fix.
    """
    path = tmp_path / "mcgyvr.yaml"
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE, table=table)

    assert not path.exists(), "nothing may be left behind on a refusal"
    message = str(exc.value)
    assert "Refusing to write a config that cannot load" in message
    assert "No local backend answered" in message
    assert "no GPU this build can see" in message


def test_the_refusal_says_how_to_fix_it_both_ways(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """A loud failure that does not say what to do is just a loud failure."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=BARE, table=table)
    message = str(exc.value)
    assert "start a local backend" in message
    assert "api_key_env: ANTHROPIC_API_KEY" in message, "a worked API-source example"
    assert "api_claude-opus-5" in message, "named by the convention"


def test_the_worked_example_in_the_refusal_actually_loads(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """We tell the user to paste it, so it had better be a valid config."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=BARE, table=table)

    block = "\n".join(
        line[6:] for line in str(exc.value).splitlines() if line.startswith("      ")
    )
    config = parse_config(textwrap.dedent(block))
    assert [t.name for t in config.ladder.tiers] == ["api_claude-opus-5"]
    assert not config.is_local_only


def test_a_reachable_backend_with_nothing_bindable_also_refuses(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """A backend is up, but no GPU means no rung fits — still unwritable."""
    detection = Detection(
        gpus=(),
        cpu_count=4,
        ram_gb=16.0,
        backends=(Backend("ollama", "http://localhost:11434", "ollama", (), "probe"),),
        docker=False,
        provenance={"docker": "docker is not on PATH"},
    )
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=detection, table=table)
    assert "Reachable backends: ollama" in str(exc.value)


def test_a_refusal_never_touches_an_existing_config(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """Someone's working config must survive a re-run on a broken machine."""
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(InitError):
        initialize(path, detection=BARE, table=table, force=True)
    assert path.read_text(encoding="utf-8") == before


def test_the_small_rig_gets_the_moe_rung_written_into_the_file(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=SMALL_RIG, table=table)
    config = load_config(path)
    models = [t.model for t in config.ladder.tiers]
    assert "qwen3-coder-30b-a3b" in models
    moe = next(t for t in config.ladder.tiers if t.model == "qwen3-coder-30b-a3b")
    assert moe.source == "llama-server", "bound to the backend it was measured on"


# --- naming convention ----------------------------------------------------


def test_tiers_are_named_by_role_locality_and_model(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    config = load_config(path)
    for tier in config.ladder.tiers:
        assert tier.name.startswith("local_")
    assert "local_qwen2.5-coder-7b" in [t.name for t in config.ladder.tiers]


# --- idempotence and not clobbering hand edits ---------------------------


def test_rerunning_reports_a_delta_and_writes_nothing(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    edited = path.read_text(encoding="utf-8").replace(
        "max_parallel: 1", "max_parallel: 4"
    )
    path.write_text(edited, encoding="utf-8")

    again = initialize(path, detection=KEYLESS_RIG, table=table)
    assert not again.written, "a hand edit must never be overwritten silently"
    assert path.read_text(encoding="utf-8") == edited
    assert any("max_parallel" in str(d) for d in again.deltas)


def test_an_unchanged_config_reports_no_delta(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    again = initialize(path, detection=KEYLESS_RIG, table=table)
    assert not again.written
    assert again.deltas == (), "the same machine must propose the same config"


def test_force_overwrites_and_says_what_changed(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    path.write_text(
        path.read_text(encoding="utf-8").replace("max_parallel: 1", "max_parallel: 4"),
        encoding="utf-8",
    )
    forced = initialize(path, detection=KEYLESS_RIG, table=table, force=True)
    assert forced.written and not forced.created
    assert any("max_parallel" in str(d) for d in forced.deltas)
    assert load_config(path).sources["ollama"].max_parallel == 1


def test_rendering_is_deterministic(table) -> None:  # type: ignore[no-untyped-def]
    """BUILD-09: a second run on an unchanged machine is a no-op."""
    from mcgyvr.propose import propose

    proposal = propose(table, vram_gb=12.0, sources=[])
    data = build(KEYLESS_RIG, proposal)
    assert render(data) == render(data)


def test_an_unreadable_config_is_not_silently_replaced(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """A corrupt file is still someone's file."""
    path = tmp_path / "mcgyvr.yaml"
    path.write_text("this: is: not: valid: yaml:\n  - [\n", encoding="utf-8")
    result = initialize(path, detection=KEYLESS_RIG, table=table)
    assert not result.written
    assert path.read_text(encoding="utf-8").startswith("this:")
    assert result.deltas, "it must say why it declined"
    assert "does not parse" in str(result.deltas[0])


# --- honest about what is missing ----------------------------------------


def test_missing_pieces_are_reported_with_what_they_cost(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    result = initialize(tmp_path / "c.yaml", detection=KEYLESS_RIG, table=table)
    limits = " ".join(result.limits)
    assert "No API provider is configured" in limits
    assert "supported install" in limits
    assert "tempdir" in limits and "weaker" in limits


def test_docker_present_does_not_produce_a_docker_warning(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    result = initialize(tmp_path / "c.yaml", detection=SMALL_RIG, table=table)
    assert not any("weaker mode" in limit for limit in result.limits)
    assert load_config(tmp_path / "c.yaml").data["sandbox"]["mode"] == "docker"


def test_decisions_explain_each_binding(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    result = initialize(tmp_path / "c.yaml", detection=KEYLESS_RIG, table=table)
    decisions = " ".join(result.decisions)
    assert "NVIDIA GeForce RTX 3060" in decisions
    assert "HumanEval+" in decisions
    assert "already pulled" in decisions
    assert "needs a" in decisions and "pull" in decisions


# --- the file a human has to read ----------------------------------------


def test_the_file_carries_comments_from_the_schema(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """Comments are rendered from the schema, so they cannot drift from it."""
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    text = path.read_text(encoding="utf-8")
    assert "# Config schema version." in text
    assert "# Where the source answers, including scheme and port." in text
    prose = " ".join(
        line.lstrip().removeprefix("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    )
    collapsed = " ".join(prose.split())
    assert "nothing above the execution seam knows which host" in collapsed


def test_no_credential_is_ever_written_as_a_value(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    text = path.read_text(encoding="utf-8")
    assert "never written in this file" in text
    # The env-name keys ship commented, so nothing binds a secret by accident.
    assert "# api_key_env:" in text


def test_values_that_need_quoting_get_it(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """A model id carries a colon; a URL carries a colon and slashes."""
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    text = path.read_text(encoding="utf-8")
    assert '"http://localhost:11434"' in text
    assert '"qwen2.5-coder:7b"' in text


# --- a rig on another machine is bindable (#161) --------------------------

REMOTE_ONLY = Detection(
    gpus=(),
    cpu_count=8,
    ram_gb=23.5,
    backends=(
        Backend(
            "srv1_ollama",
            "http://srv1:11434",
            "ollama",
            ("qwen2.5-coder:3b", "qwen2.5-coder:1.5b"),
            "probe",
            host="srv1",
            kind="ollama",
        ),
        Backend(
            "srv2_ollama",
            "http://srv2:11434",
            "ollama",
            ("qwen2.5-coder:7b", "qwen2.5-coder:3b"),
            "probe",
            host="srv2",
            kind="ollama",
        ),
    ),
    docker=True,
    provenance={"docker": "docker info reported server 29.1.3"},
    notes=("GPU: not determined — nvidia-smi is absent or failed.",),
)


def test_a_laptop_with_no_gpu_binds_the_rigs_it_can_reach(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """The deployment mcgyvr exists for, and the one init used to refuse.

    Before #161 this took `_nothing_to_bind`: no GPU here meant no rung, even
    with two rigs answering.
    """
    path = tmp_path / "mcgyvr.yaml"
    result = initialize(path, detection=REMOTE_ONLY, table=table)

    assert result.created and path.exists()
    config = load_config(path)
    assert config.ladder.tiers, "a reachable rig is a bindable rig"
    assert set(config.sources) == {"srv1_ollama", "srv2_ollama"}
    assert config.is_local_only, "no key is needed to reach your own machines"


def test_two_rigs_running_the_same_backend_both_survive(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Sources are a mapping, so an unqualified name would drop a whole rig."""
    proposal = propose(
        table,
        vram_gb=REMOTE_ONLY.largest_vram_gb,
        sources=_sources_for(REMOTE_ONLY),
    )
    data = build(REMOTE_ONLY, proposal)
    assert len(data["sources"]) == 2
    assert {s["base_url"] for s in data["sources"].values()} == {
        "http://srv1:11434",
        "http://srv2:11434",
    }


def test_every_rung_says_which_machine_it_runs_on(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """With one machine this was implicit. With two it is the whole question."""
    result = initialize(tmp_path / "c.yaml", detection=REMOTE_ONLY, table=table)
    rung_decisions = [d for d in result.decisions if " -> " in d]
    assert rung_decisions
    for decision in rung_decisions:
        assert " on srv1" in decision or " on srv2" in decision


def test_a_ladder_across_machines_is_flagged_as_possibly_inverted(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Ordering across heterogeneous hardware is #162; silence is not an option."""
    result = initialize(tmp_path / "c.yaml", detection=REMOTE_ONLY, table=table)
    joined = " ".join(result.limits)
    assert "spans 2 machines" in joined
    assert "#162" in joined


def test_the_refusal_points_at_the_flag_that_would_have_worked(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """A bare laptop's problem may be that nobody told init where the rigs are."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=BARE, table=table)
    assert "--host" in str(exc.value)


def test_hosts_are_ignored_when_a_detection_is_supplied(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Two answers to one question. The caller's own detection wins, silently.

    Asserted because the alternative — sweeping the network during a test
    that supplied its own machine — is the kind of thing that passes locally
    and hangs in CI.
    """
    result = initialize(
        tmp_path / "c.yaml", detection=REMOTE_ONLY, table=table, hosts=("nope.invalid",)
    )
    assert set(load_config(result.path).sources) == {"srv1_ollama", "srv2_ollama"}


# --- a written config dispatches on the uncaveated path (#164) ------------


def test_a_written_config_binds_ollama_on_the_uncaveated_protocol(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """`detect` calls it Ollama; the config dispatches to it as OpenAI."""
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    config = load_config(path)
    assert config.sources["ollama"].api == "openai"


def test_no_rung_of_a_written_config_carries_the_quality_caveat(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """The property that matters, asserted where it is actually decided.

    Binding `api: openai` is only the mechanism; the claim is that a config
    init wrote can serve a measurement. That is `Runner.quality_safe`, so the
    assertion goes through the runner rather than through the string.
    """
    from mcgyvr.pool import source_map
    from mcgyvr.runner import runner_for

    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    pool = source_map(load_config(path))
    assert pool.rungs, "this fixture is only interesting with rungs on it"
    for rung in pool.rungs:
        runner = runner_for(pool.bind(rung.name))
        assert runner.quality_safe, (
            f"{rung.name} dispatches on a path CAV-01 invalidates, so this "
            f"install cannot serve a measurement"
        )


def test_the_protocol_switch_is_explained_rather_than_silent(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """A config saying `openai` for a source called `ollama` reads as a bug."""
    result = initialize(tmp_path / "c.yaml", detection=KEYLESS_RIG, table=table)
    joined = " ".join(result.decisions)
    assert "CAV-01" in joined
    assert "32.3%" in joined


def test_detection_still_reads_the_native_model_listing(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Binding compatibly must not cost the inventory that made it possible.

    `/v1/models` on Ollama reports loaded models; `/api/tags` reports pulled
    ones. Proposing against the former would hide every model on disk.
    """
    result = initialize(tmp_path / "c.yaml", detection=KEYLESS_RIG, table=table)
    assert any("already pulled" in d for d in result.decisions)
