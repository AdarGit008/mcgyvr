"""`mcgyvr init` is the first thing a stranger runs.

The v1 release criterion is written around it: clean machine, no key, no
Docker, and the result must be a config that supports a real local task. So
the central test here is exactly that machine — and the generated file is
fed back through the real loader, because "it looks right" is not the claim
being made.

Every machine is invented (:mod:`tests.machine_shapes`) and detection is run
on it offline, so these run identically on a machine with no GPU and on one
with four.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import load as load_config
from mcgyvr.detect import Detection
from mcgyvr.initialize import (
    InitError,
    _sources_for,
    build,
    initialize,
    parse_api_unit,
    render,
)
from mcgyvr.propose import binding_name, propose
from tests.machine_shapes import Shape, detection, shape, shapes, with_server

KINDS = tuple(kind for kind, _, _ in detect.PORT_CONVENTIONS)

#: A machine with nothing: no card tool, no server.
BARE = detection(shape("bare"))


def _serving(label: str, *models: str) -> Detection:
    """The invented machine of ``label`` with one more server listing ``models``."""
    machine = shape(label)
    taken = {server.kind for server in machine.servers}
    kind = next(kind for kind in KINDS if kind not in taken)
    return detection(with_server(machine, kind=kind, models=models))


#: A machine with a card and a server that lists a model, and no docker.
KEYLESS_RIG = _serving("one-card", "example-model:small")


def _far() -> tuple[Shape, Shape]:
    """Two machines over the network, both running the same server program.

    Each server lists models of its own, so every listing is bound.
    """
    far = [m for m in shapes() if not m.local and m.servers][:2]
    assert len(far) == 2, "two machines over the network"
    first, second = (
        dataclasses.replace(
            machine,
            servers=tuple(
                dataclasses.replace(s, models=(f"example-model-{i}-{j}",))
                for j, s in enumerate(machine.servers)
            ),
        )
        for i, machine in enumerate(far)
    )
    kind = second.servers[0].kind
    if kind not in {s.kind for s in first.servers}:
        first = with_server(first, kind=kind, models=("example-model-far",))
    return first, second


def _remote_only() -> Detection:
    first, second = _far()
    return detection(first, reached=(second,))


# --- the v1 release criterion --------------------------------------------


def test_clean_machine_no_key_no_docker_gets_a_working_local_config(
    tmp_path: Path,
) -> None:
    path = tmp_path / "setup"
    result = initialize(path, detection=KEYLESS_RIG)
    assert result.created and result.written

    config = load_config(path)
    assert config.is_local_only, "no key must be needed to run"
    assert config.ladder.names, "a real local task needs at least one rung"
    assert config.data["sandbox"]["mode"] == "tempdir", "no Docker → the weaker mode"


@pytest.mark.parametrize("label", ["one-card", "busy-card", "bare-local-server"])
def test_the_generated_file_loads_without_edits(tmp_path: Path, label: str) -> None:
    """The whole point: init's output is the loader's input, unmodified."""
    initialize(tmp_path / "setup", detection=_serving(label, "example-model-small"))
    config = load_config(tmp_path / "setup")
    assert config.get("profile") == "live"
    assert "version" not in config.data


def test_a_machine_with_no_backend_refuses_rather_than_writing(tmp_path: Path) -> None:
    """No GPU, no backend, nothing to dispatch to.

    A file that dispatches nowhere is not a head start — it is a
    misconfiguration that surfaces later and further from its cause. So init
    writes nothing and says what to fix.
    """
    path = tmp_path / "setup"
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE)

    assert not path.exists(), "nothing may be left behind on a refusal"
    message = str(exc.value)
    assert "Refusing to write a config that cannot load" in message
    assert "No local backend answered" in message
    assert "no GPU this build can see" in message


def test_the_refusal_says_how_to_fix_it_both_ways(tmp_path: Path) -> None:
    """A loud failure that does not say what to do is just a loud failure."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=BARE)
    message = str(exc.value)
    assert "start a local backend" in message
    assert "--api model=claude-opus-5" in message, "a worked `--api` invocation"
    assert "api_key_env=ANTHROPIC_API_KEY" in message, "the key named, never held"


def test_the_invocation_the_refusal_advertises_actually_works(tmp_path: Path) -> None:
    """We tell the user to run it, so it had better write a loadable setup.

    The refusal names a command rather than a YAML block to paste, so what has
    to be true is that the command works: the line is lifted out
    of the message and run, rather than a copy of it being maintained here.
    """
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "refused", detection=BARE)

    advertised = next(
        line.strip()
        for line in str(exc.value).splitlines()
        if line.strip().startswith("mcgyvr init --api ")
    )
    path = tmp_path / "setup"
    result = initialize(
        path,
        detection=BARE,
        api_units=(parse_api_unit(advertised.split("--api ", 1)[1]),),
    )

    assert result.created and result.written
    config = load_config(path)
    assert list(config.ladder.names) == ["api_claude-opus-5"]
    assert not config.is_local_only


def test_a_reachable_backend_with_nothing_bindable_also_refuses(
    tmp_path: Path,
) -> None:
    """A server is up but lists no model: nothing to bind, still unwritable."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=_serving("bare"))
    message = " ".join(str(exc.value).split())
    assert f"Reachable model servers: {KINDS[0]}" in message
    assert "none of them lists a model" in message
    assert "load a model into a server named above" in message


def test_a_refusal_never_touches_an_existing_config(tmp_path: Path) -> None:
    """Someone's working config must survive a re-run on a broken machine."""
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    before = (
        (path / "fleet.yaml").read_text(encoding="utf-8"),
        (path / "policy.yaml").read_text(encoding="utf-8"),
    )

    with pytest.raises(InitError):
        initialize(path, detection=BARE, force=True)
    assert (
        (path / "fleet.yaml").read_text(encoding="utf-8"),
        (path / "policy.yaml").read_text(encoding="utf-8"),
    ) == before


# --- naming convention ----------------------------------------------------


def test_tiers_are_named_by_locality_and_model(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    config = load_config(path)
    for name in config.ladder.names:
        assert name.startswith("local_")
    assert list(config.ladder.names) == [binding_name("example-model:small")]


# --- idempotence and not clobbering hand edits ---------------------------


def test_rerunning_reports_a_delta_and_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    fleet = path / "fleet.yaml"
    edited = fleet.read_text(encoding="utf-8").replace("width: 1", "width: 4")
    fleet.write_text(edited, encoding="utf-8")

    again = initialize(path, detection=KEYLESS_RIG)
    assert not again.written, "a hand edit must never be overwritten silently"
    assert fleet.read_text(encoding="utf-8") == edited
    assert any("width" in str(d) for d in again.deltas)


def test_an_unchanged_config_reports_no_delta(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    again = initialize(path, detection=KEYLESS_RIG)
    assert not again.written
    assert again.deltas == (), "the same machine must propose the same config"


def test_force_overwrites_and_says_what_changed(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    fleet = path / "fleet.yaml"
    fleet.write_text(
        fleet.read_text(encoding="utf-8").replace("width: 1", "width: 4"),
        encoding="utf-8",
    )
    forced = initialize(path, detection=KEYLESS_RIG, force=True)
    assert forced.written and not forced.created
    assert any("width" in str(d) for d in forced.deltas)
    units = load_config(path).units.values()
    assert next(u for u in units if u.rig == KINDS[0]).width == 1


def test_rendering_is_deterministic() -> None:
    """BUILD-09: a second run on an unchanged machine is a no-op."""
    proposal = propose(sources=_sources_for(KEYLESS_RIG))
    data = build(KEYLESS_RIG, proposal)
    assert render(data) == render(data)


def test_an_unreadable_config_is_not_silently_replaced(tmp_path: Path) -> None:
    """A corrupt file is still someone's file."""
    path = tmp_path / "setup"
    path.mkdir()
    (path / "fleet.yaml").write_text(
        "this: is: not: valid: yaml:\n  - [\n", encoding="utf-8"
    )
    result = initialize(path, detection=KEYLESS_RIG)
    assert not result.written
    assert (path / "fleet.yaml").read_text(encoding="utf-8").startswith("this:")
    assert result.deltas, "it must say why it declined"
    assert "does not parse" in str(result.deltas[0])


# --- honest about what is missing ----------------------------------------


def test_missing_pieces_are_reported_with_what_they_cost(tmp_path: Path) -> None:
    result = initialize(tmp_path / "c", detection=KEYLESS_RIG)
    limits = " ".join(result.limits)
    assert "No API provider is configured" in limits
    assert "supported install" in limits
    assert "tempdir" in limits and "weaker" in limits


def test_docker_present_does_not_produce_a_docker_warning(tmp_path: Path) -> None:
    # The generator's machines have no docker; this one is given it, and the
    # note detection adds for its absence goes with it.
    found = dataclasses.replace(
        KEYLESS_RIG,
        docker=True,
        notes=tuple(n for n in KEYLESS_RIG.notes if not n.startswith("Sandbox")),
    )
    result = initialize(tmp_path / "c", detection=found)
    assert not any("weaker mode" in limit for limit in result.limits)
    assert load_config(tmp_path / "c").data["sandbox"]["mode"] == "docker"


def test_decisions_explain_each_binding(tmp_path: Path) -> None:
    """Every card and server found is named, and every unit says why it is."""
    result = initialize(tmp_path / "c", detection=KEYLESS_RIG)
    decisions = " ".join(result.decisions)
    for gpu in KEYLESS_RIG.gpus:
        assert f"GPU {gpu.name} with {gpu.size}" in decisions
    for backend in KEYLESS_RIG.backends:
        assert f"{len(backend.models)} model(s) listed" in decisions
        for model in backend.models:
            assert (
                f"{binding_name(model)} -> {model} at {backend.base_url}: bound "
                f"because {backend.name} lists it" in decisions
            )


# --- the file a human has to read ----------------------------------------


def test_the_file_carries_comments_from_the_schema(tmp_path: Path) -> None:
    """Comments are rendered from the schema, so they cannot drift from it."""
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    text = (path / "fleet.yaml").read_text(encoding="utf-8") + (
        path / "policy.yaml"
    ).read_text(encoding="utf-8")
    assert "# Which setup this file is" in text
    assert "# Where this unit answers, including scheme and port." in text
    prose = " ".join(
        line.lstrip().removeprefix("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    )
    collapsed = " ".join(prose.split())
    assert (
        "A unit carries every fact about what it is and can physically do" in collapsed
    )


def test_no_credential_is_ever_written_as_a_value(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    text = (path / "fleet.yaml").read_text(encoding="utf-8") + (
        path / "policy.yaml"
    ).read_text(encoding="utf-8")
    assert "never written in this file" in text
    # The env-name keys ship commented, so nothing binds a secret by accident.
    assert "# api_key_env:" in text


def test_values_that_need_quoting_get_it(tmp_path: Path) -> None:
    """A model id carries a colon; a URL carries a colon and slashes."""
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    text = (path / "fleet.yaml").read_text(encoding="utf-8")
    assert f'"{KEYLESS_RIG.backends[0].base_url}"' in text
    assert '"example-model:small"' in text


# --- a rig on another machine is bindable (#161) --------------------------


def test_a_laptop_with_no_gpu_binds_the_rigs_it_can_reach(tmp_path: Path) -> None:
    """The deployment mcgyvr exists for: no GPU here, two rigs answering.

    No local GPU does not end in a refusal while a reachable rig lists a model.
    """
    found = _remote_only()
    assert not found.gpus
    path = tmp_path / "setup"
    result = initialize(path, detection=found)

    assert result.created and path.exists()
    config = load_config(path)
    assert config.ladder.names, "a reachable rig is a bindable rig"
    assert {u.rig for u in config.units.values()} == {b.name for b in found.backends}
    assert config.is_local_only, "no key is needed to reach your own machines"


def test_two_rigs_running_the_same_backend_both_survive() -> None:
    """Sources are a mapping, so an unqualified name would drop a whole rig."""
    found = _remote_only()
    kinds = [b.kind for b in found.backends]
    assert any(kinds.count(kind) > 1 for kind in kinds), "one program on both"
    data = build(found, propose(sources=_sources_for(found)))
    assert {s["address"] for s in data["units"].values()} == {
        b.base_url for b in found.backends
    }


def test_every_rung_says_which_machine_it_runs_on(tmp_path: Path) -> None:
    """With one machine this was implicit. With two it is the whole question."""
    found = _remote_only()
    result = initialize(tmp_path / "c.yaml", detection=found)
    rung_decisions = [d for d in result.decisions if " -> " in d]
    assert len(rung_decisions) == sum(len(b.models) for b in found.backends)
    for decision in rung_decisions:
        assert any(f" at {b.base_url}: " in decision for b in found.backends)


def test_the_refusal_points_at_the_flag_that_would_have_worked(tmp_path: Path) -> None:
    """A bare laptop's problem may be that nobody told init where the rigs are."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "c.yaml", detection=BARE)
    assert "--host" in str(exc.value)


def test_hosts_are_ignored_when_a_detection_is_supplied(tmp_path: Path) -> None:
    """Two answers to one question. The caller's own detection wins, silently.

    Asserted because the alternative — sweeping the network during a test
    that supplied its own machine — is the kind of thing that passes locally
    and hangs in CI.
    """
    found = _remote_only()
    result = initialize(tmp_path / "c.yaml", detection=found, hosts=("nope.invalid",))
    assert {u.rig for u in load_config(result.path).units.values()} == {
        b.name for b in found.backends
    }


# --- a written config dispatches on the uncaveated path (#164) ------------


def test_a_written_config_binds_ollama_on_the_uncaveated_protocol(
    tmp_path: Path,
) -> None:
    """A unit init writes for a server that is not vLLM names no engine."""
    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    config = load_config(path)
    assert next(iter(config.units.values())).engine is None


def test_no_rung_of_a_written_config_carries_the_quality_caveat(
    tmp_path: Path,
) -> None:
    """The property that matters, asserted where it is actually decided.

    Binding `api: openai` is only the mechanism; the claim is that a config
    init wrote can serve a measurement. That is `Runner.quality_safe`, so the
    assertion goes through the runner rather than through the string.
    """
    from mcgyvr.pool import source_map
    from mcgyvr.runner import runner_for

    path = tmp_path / "setup"
    initialize(path, detection=KEYLESS_RIG)
    pool = source_map(load_config(path))
    assert pool.rungs, "this fixture is only interesting with rungs on it"
    for rung in pool.rungs:
        runner = runner_for(pool.bind(rung.name))
        assert runner.quality_safe, (
            f"{rung.name} dispatches on a path CAV-01 invalidates, so this "
            f"install cannot serve a measurement"
        )


def test_detection_still_reads_the_whole_model_listing(tmp_path: Path) -> None:
    """Each server's decision counts every model it lists, bound or not."""
    found = _serving("one-card", "example-model-small", "example-model-medium")
    result = initialize(tmp_path / "c", detection=found)
    (backend,) = found.backends
    assert any(
        d.startswith(f"Backend '{backend.name}'")
        and d.endswith(f"; {len(backend.models)} model(s) listed.")
        for d in result.decisions
    )
