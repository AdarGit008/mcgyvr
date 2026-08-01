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
from mcgyvr.initialize import InitError, build, initialize, render

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
    assert "worker_api_claude-opus-5" in message, "named by the convention"


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
    assert [t.name for t in config.ladder.tiers] == ["worker_api_claude-opus-5"]
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
        assert tier.name.startswith("worker_local_")
    assert "worker_local_qwen2.5-coder-7b" in [t.name for t in config.ladder.tiers]


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
    assert "# token_env:" in text


def test_values_that_need_quoting_get_it(tmp_path: Path, table) -> None:  # type: ignore[no-untyped-def]
    """A model id carries a colon; a URL carries a colon and slashes."""
    path = tmp_path / "mcgyvr.yaml"
    initialize(path, detection=KEYLESS_RIG, table=table)
    text = path.read_text(encoding="utf-8")
    assert '"http://localhost:11434"' in text
    assert '"qwen2.5-coder:7b"' in text
