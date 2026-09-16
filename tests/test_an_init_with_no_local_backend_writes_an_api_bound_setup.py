"""A machine with a key and no GPU gets a written setup, not a refusal.

Until `--api` existed, `mcgyvr init` on such a machine refused and told the
operator to hand-write the file — and the text that told them printed one
merged document, where a setup on disk is two files. The advice was therefore
both work the product could do itself and a shape the loader does not take.

What is pinned here is the whole of that claim, and each part is a property
the old path did not have:

* the hosted path writes the **same two files** any other init writes, through
  the same renderer and past the same self-parse, so it cannot emit a config
  the loader rejects;
* `mcgyvr pool` reads them back as a usable rung of the `api` family;
* a machine that asked for **nothing** still refuses, because a config that
  dispatches nowhere is not a head start;
* the key's **value** is never written, and is never even read — only the name
  of the environment variable holding it reaches the file.

Detection is injected, so these run identically on a machine with a card and
on one without, and none of them needs a key to exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.capability import load as load_table
from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.initialize import ApiSpecError, InitError, initialize, parse_api_unit
from mcgyvr.pool import source_map
from mcgyvr.route import family_of
from tests.test_initialize import BARE, KEYLESS_RIG

#: The unit a stranger with a key and no card would bind, spelled as they
#: would type it. One string, so no test here restates the flag's grammar.
SPEC = (
    "model=claude-opus-5,"
    "address=https://api.anthropic.com,"
    "api_key_env=ANTHROPIC_API_KEY"
)

#: A value shaped like a real key. It only ever lives in the environment — the
#: point of every assertion below is that it does not reach a file.
SECRET = "sk-ant-api03-notarealkey-000000000000000000"


@pytest.fixture
def table():  # type: ignore[no-untyped-def]
    return load_table()


def _written(path: Path) -> str:
    """Both generated files as one text, for asking what was written."""
    return (path / FLEET_FILENAME).read_text(encoding="utf-8") + (
        path / POLICY_FILENAME
    ).read_text(encoding="utf-8")


# --- the path that used to be a refusal -----------------------------------


def test_a_machine_with_no_backend_and_an_api_unit_writes_a_setup(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """No GPU, no backend, one key: the case init used to refuse outright."""
    path = tmp_path / "setup"
    result = initialize(
        path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),)
    )

    assert result.created and result.written
    config = load_config(path)
    assert list(config.ladder.names) == ["api_claude-opus-5"]
    assert not config.is_local_only, "a hosted rung needs a key by definition"
    assert config.units["api_claude-opus-5"].model == "claude-opus-5"
    assert config.units["api_claude-opus-5"].address == "https://api.anthropic.com"


def test_the_result_is_the_same_two_files_any_other_init_writes(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """The defect in the old advice: it showed one merged document.

    A setup is `fleet.yaml` (what runs where) and `policy.yaml` (how work
    moves over it), and each file refuses a key belonging to the other. So
    the split is asserted on the files themselves, not on a rendered string.
    """
    path = tmp_path / "setup"
    initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),))

    fleet = (path / FLEET_FILENAME).read_text(encoding="utf-8")
    policy = (path / POLICY_FILENAME).read_text(encoding="utf-8")

    assert "units:" in fleet and "api_claude-opus-5:" in fleet
    assert "ladder:" in policy
    assert "ladder:" not in fleet, "the ladder is policy, not fleet"
    assert "units:" not in policy, "units are fleet, not policy"


def test_the_written_setup_survives_the_loader_untouched(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Init's output is the loader's input, unmodified — the whole guarantee."""
    path = tmp_path / "setup"
    initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),))

    config = load_config(path)
    assert config.get("profile") == "live"
    assert config.units["api_claude-opus-5"].requires_credential


def test_a_local_ladder_and_a_hosted_unit_climb_one_ladder(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """`--api` is additive, not a mode.

    A machine with a backend AND a key is the escalation this product exists
    to run, so the hosted unit joins the ladder rather than replacing it — and
    it joins at the dear end, because a ladder is written cheapest-first.
    """
    path = tmp_path / "setup"
    initialize(
        path, detection=KEYLESS_RIG, table=table, api_units=(parse_api_unit(SPEC),)
    )

    names = list(load_config(path).ladder.names)
    assert len(names) > 1, "this fixture is only interesting with a local rung too"
    assert names[-1] == "api_claude-opus-5", "the hosted rung is the dear end"
    assert all(name.startswith("local_") for name in names[:-1])


# --- the refusal that must survive ----------------------------------------


def test_a_machine_that_asked_for_nothing_still_refuses(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """The genuinely-empty case is still a refusal, not an empty config."""
    path = tmp_path / "setup"
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE, table=table)

    assert not path.exists(), "nothing may be left behind on a refusal"
    assert "Refusing to write a config that cannot load" in str(exc.value)


def test_the_refusal_points_at_the_flag_that_would_have_worked(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Advice that is no longer true is worse than no advice."""
    with pytest.raises(InitError) as exc:
        initialize(tmp_path / "setup", detection=BARE, table=table)
    message = str(exc.value)

    assert "--api" in message
    assert "write the file by hand" not in message, "the old, now-false advice"
    # The distinctive line of the old pasteable block, which bound the key in
    # YAML inside one merged document. Its absence is the claim; `units:` on
    # its own is not, because the message quotes the loader's own complaint
    # ("fleet.yaml: units: is empty") and that quote is the honest part.
    assert "api_key_env: ANTHROPIC_API_KEY" not in message, "the merged block"
    assert "api_key_env=ANTHROPIC_API_KEY" in message, "the flag that replaced it"


def test_a_hosted_unit_that_cannot_load_is_not_blamed_on_the_machine(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """Two situations, two remedies.

    A bad `--api` value is the operator's to fix; telling them to start a
    local backend would send them to repair a machine that was never the
    problem. The address here has no scheme, which the loader refuses.
    """
    path = tmp_path / "setup"
    spec = "model=m,address=api.example.com,api_key_env=EXAMPLE_KEY"
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(spec),))

    message = str(exc.value)
    assert not path.exists()
    assert "start a local backend" not in message
    assert "--api" in message and "address" in message


def test_two_hosted_units_of_one_model_are_refused_by_name(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """One model mints one rung name, and a ladder lists a rung once."""
    path = tmp_path / "setup"
    units = (
        parse_api_unit(SPEC),
        parse_api_unit(
            "model=claude-opus-5,address=https://eu.example.com,api_key_env=OTHER_KEY"
        ),
    )
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE, table=table, api_units=units)

    assert not path.exists()
    assert "api_claude-opus-5" in str(exc.value)


# --- the credential rule --------------------------------------------------


def test_no_key_value_is_ever_written_only_its_variable_name(  # type: ignore[no-untyped-def]
    tmp_path: Path, table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule the whole `api_key_env` design exists to keep.

    The variable is exported with a real-shaped secret before init runs, so a
    path that read it and wrote it through would be caught here rather than in
    somebody's git history.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    path = tmp_path / "setup"
    initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),))

    text = _written(path)
    assert SECRET not in text, "a key value reached a config file"
    assert "ANTHROPIC_API_KEY" in text, "the variable's name is what binds it"
    assert load_config(path).units["api_claude-opus-5"].api_key_env == (
        "ANTHROPIC_API_KEY"
    )


def test_init_writes_the_setup_without_the_key_existing_at_all(  # type: ignore[no-untyped-def]
    tmp_path: Path, table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Init names a variable; it never reads one.

    Requiring the key to be exported before the file could be written would
    make init's output depend on a secret, and would mean init had touched
    one. Neither is true, and this is where that is enforced.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "setup"
    result = initialize(
        path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),)
    )

    assert result.created and result.written
    assert "ANTHROPIC_API_KEY" in _written(path)


def test_a_key_pasted_where_its_name_belongs_is_refused(  # type: ignore[no-untyped-def]
    tmp_path: Path, table
) -> None:
    """The mistake the flag's wording exists to prevent, caught if made."""
    path = tmp_path / "setup"
    spec = f"model=claude-opus-5,address=https://api.anthropic.com,api_key_env={SECRET}"
    with pytest.raises(InitError) as exc:
        initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(spec),))

    assert not path.exists(), "nothing may be written when a key was pasted"
    assert SECRET not in str(exc.value), "the refusal must not echo the secret back"


# --- `mcgyvr pool` reads it back ------------------------------------------


def test_pool_reads_the_written_setup_back_as_a_usable_api_rung(  # type: ignore[no-untyped-def]
    tmp_path: Path, table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A written config nothing can read back is not a working config."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    path = tmp_path / "setup"
    initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),))

    config = load_config(path)
    pool = source_map(config)

    assert [rung.name for rung in pool.rungs] == ["api_claude-opus-5"]
    assert pool.skipped == ()
    assert pool.rungs[0].model == "claude-opus-5"
    assert family_of(config, "api_claude-opus-5").name == "api"


def test_a_rung_whose_variable_is_unset_is_skipped_with_the_reason(  # type: ignore[no-untyped-def]
    tmp_path: Path, table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The honest degradation: a named-but-absent key shortens the ladder.

    Asserted beside the usable case because the difference between "this rung
    is missing" and "this rung is missing *because* the variable is unset" is
    the whole value of what `mcgyvr pool` prints.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "setup"
    initialize(path, detection=BARE, table=table, api_units=(parse_api_unit(SPEC),))

    pool = source_map(load_config(path))

    assert pool.rungs == ()
    assert [skip.name for skip in pool.skipped] == ["api_claude-opus-5"]
    assert "ANTHROPIC_API_KEY" in pool.skipped[0].reason


# --- what the flag accepts ------------------------------------------------


def test_a_spec_must_state_all_three_facts(table) -> None:  # type: ignore[no-untyped-def]
    """No fact is guessed — a provider's URL is not derivable from a model id."""
    with pytest.raises(ApiSpecError) as exc:
        parse_api_unit("model=claude-opus-5")
    assert "address" in str(exc.value) and "api_key_env" in str(exc.value)


def test_an_unknown_key_is_refused_rather_than_ignored() -> None:
    """A silently dropped value is a setting the operator believes they made."""
    with pytest.raises(ApiSpecError) as exc:
        parse_api_unit(f"{SPEC},region=eu")
    assert "region" in str(exc.value)


def test_a_value_that_is_not_key_equals_value_is_refused() -> None:
    with pytest.raises(ApiSpecError) as exc:
        parse_api_unit("claude-opus-5")
    assert "key=value" in str(exc.value)


def test_the_spec_keys_are_the_units_own_schema_keys() -> None:
    """One vocabulary, so the flag and the file cannot drift apart."""
    from mcgyvr.config import UNIT_FIELDS
    from mcgyvr.initialize import API_SPEC_KEYS

    names = {field.name for field in UNIT_FIELDS}
    assert set(API_SPEC_KEYS) <= names
