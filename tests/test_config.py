"""The config file is public surface a stranger edits by hand.

These tests hold the loader to the four acceptance properties of the
schema: a missing binding is named, an unknown key fails, a credential
cannot be written as a value, and a config with no API provider is a valid
local-only install rather than a degraded one.

Error *messages* are asserted on, not just error types. An unparseable
rejection is a defect here: the message is the whole remedy a hand-editing
user gets.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcgyvr.config import (
    CONFIG_PATH_ENV,
    SCHEMA,
    ConfigFileError,
    ConfigSchemaError,
    CredentialInConfigError,
    Field,
    UnboundValueError,
    config_path,
    field_at,
    load,
    parse,
)

LOCAL_ONLY = """\
units:
  cheap:
    address: http://localhost:8080
    model: qwen2.5-coder:7b
    rig: local
    width: 3
  strong:
    address: http://localhost:8080
    model: qwen2.5-coder:14b
    rig: local
    width: 3
ladder:
- cheap
- strong
"""


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


# --- a keyless install is a supported configuration -----------------------


def test_no_api_provider_yields_a_valid_local_only_ladder() -> None:
    config = parse(LOCAL_ONLY)
    assert config.is_local_only
    assert list(config.ladder.names) == ["cheap", "strong"]
    assert config.units["cheap"].requires_credential is False


def test_defaults_that_ship_are_real_working_values() -> None:
    """Every default must be usable as-is, not a placeholder to be edited."""
    config = parse(LOCAL_ONLY)
    assert config.data["sandbox"]["mode"] == "docker"
    # `branch` and not `pull_request`: the old default named a handback nothing
    # here performs, and every mode committed to the checked-out branch instead.
    assert config.data["delivery"]["mode"] == "branch"
    assert config.get("task_timeout_s") > 0
    # Verification is off rather than on-and-unbound, so a keyless install
    # loads and runs without touching the config.
    assert config.data["verifier"]["enabled"] is False


def test_a_source_needing_a_key_is_not_local_only() -> None:
    config = parse(
        cfg(
            """\
            units:
              cheap:
                address: http://localhost:8080
                model: qwen2.5-coder:7b
                rig: local
              ceiling:
                address: https://api.anthropic.com
                model: claude-opus-5
                rig: cloud
                api_key_env: ANTHROPIC_API_KEY
            ladder:
            - cheap
            - ceiling
            """
        )
    )
    assert not config.is_local_only
    assert config.units["ceiling"].requires_credential


# --- a missing binding is named ------------------------------------------


def test_missing_required_key_names_the_key() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            cfg(
                """\
                units:
                  cheap:
                    model: qwen2.5-coder:7b
                    rig: local
                ladder:
                - cheap
                """
            )
        )
    assert "units.cheap.address" in str(exc.value)
    assert "http://srv2:8002" in str(exc.value), "the message must show a shape"


def test_tier_bound_to_an_undeclared_source_is_rejected() -> None:
    """Self-contradictory: schema-valid, but the binding cannot resolve."""
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            cfg(
                """\
                units:
                  cheap:
                    address: http://localhost:8080
                    model: qwen2.5-coder:7b
                    rig: local
                ladder:
                - cheap
                - typo
                """
            )
        )
    message = str(exc.value)
    assert "ladder.1" in message
    assert "cheap" in message, "the message must name what IS declared"


def test_duplicate_tier_names_are_rejected() -> None:
    with pytest.raises(ConfigSchemaError, match="more than once"):
        parse(
            cfg(
                """\
                units:
                  cheap:
                    address: http://localhost:8080
                    model: b
                    rig: local
                ladder:
                - cheap
                - cheap
                """
            )
        )


def test_enabled_verifier_without_a_source_is_rejected_at_load() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            LOCAL_ONLY
            + cfg("""
            verifier:
              enabled: true
            """)
        )
    assert "verifier.unit" in str(exc.value)
    assert "verifier.enabled: false" in str(exc.value), "name the other way out"


def test_unbound_optional_fails_at_the_point_of_use_not_at_load() -> None:
    """A config with no orchestrator loads; asking for one is what fails."""
    config = parse(LOCAL_ONLY)
    with pytest.raises(UnboundValueError) as exc:
        config.require("orchestrator.model")
    message = str(exc.value)
    assert "orchestrator.model" in message
    assert "To bind it:" in message


def test_get_returns_a_default_where_require_raises() -> None:
    config = parse(LOCAL_ONLY)
    assert config.get("orchestrator.model") is None
    assert config.get("sandbox.mode") == "docker"


def test_dotted_reads_reach_into_lists() -> None:
    config = parse(LOCAL_ONLY)
    assert config.units[config.ladder.names[1]].model == "qwen2.5-coder:14b"


# --- fan-out is a knob, and its default is no fan-out ---------------------


def test_fanout_defaults_to_none_when_the_key_is_absent() -> None:
    """Absent means today's behaviour: a batch queues on the cheapest rung."""
    config = parse(LOCAL_ONLY)
    assert config.ladder.fanout == "none"
    assert config.get("fanout") == "none"


@pytest.mark.parametrize("mode", ["none", "idle", "full"])
def test_each_fanout_mode_parses_and_reaches_the_ladder(mode: str) -> None:
    """The router reads `config.ladder.fanout`, so the value has to land there."""
    config = parse(LOCAL_ONLY + f"fanout: {mode}\n")
    assert config.ladder.fanout == mode


def test_an_unknown_fanout_mode_lists_the_valid_values() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(LOCAL_ONLY + "fanout: spread\n")
    message = str(exc.value)
    assert "fanout" in message
    assert "none" in message and "idle" in message and "full" in message


# --- an unknown key fails -------------------------------------------------


def test_unknown_top_level_key_fails_rather_than_being_ignored() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(LOCAL_ONLY + cfg("sandbxo:\n  mode: tempdir\n"))
    assert "sandbxo" in str(exc.value)


def test_unknown_nested_key_names_its_valid_siblings() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            cfg(
                """\
                units:
                  cheap:
                    address: http://localhost:8080
                    model: qwen2.5-coder:7b
                    rig: local
                    parallel: 4
                ladder:
                - cheap
                """
            )
        )
    message = str(exc.value)
    assert "units.cheap: unknown key 'parallel'" in message
    assert "width" in message


def test_duplicate_keys_are_rejected_rather_than_silently_last_wins() -> None:
    with pytest.raises(ConfigSchemaError, match="duplicate key"):
        parse(LOCAL_ONLY.replace("    width: 3", "    width: 3\n    width: 4", 1))


def test_wrong_types_are_named_in_plain_words() -> None:
    with pytest.raises(ConfigSchemaError, match="expected a number"):
        parse(LOCAL_ONLY.replace("width: 3", "width: lots"))


def test_a_boolean_is_not_a_capacity() -> None:
    """bool is an int in Python; `width: true` must not pass as 1."""
    with pytest.raises(ConfigSchemaError, match="expected a number"):
        parse(LOCAL_ONLY.replace("width: 3", "width: true"))


def test_invalid_enum_lists_the_valid_values() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            LOCAL_ONLY.replace(
                "    rig: local", "    rig: local\n    engine: llamacpp", 1
            )
        )
    assert "llama.cpp" in str(exc.value), "the refusal lists what is valid"


def test_a_url_without_a_scheme_is_rejected() -> None:
    with pytest.raises(ConfigSchemaError, match="needs a scheme"):
        parse(LOCAL_ONLY.replace("http://localhost:8080", "localhost:8080"))


def test_empty_value_is_not_the_same_as_unset() -> None:
    with pytest.raises(ConfigSchemaError, match="is empty"):
        parse(LOCAL_ONLY.replace("model: qwen2.5-coder:7b", 'model: ""'))


def test_an_empty_ladder_is_rejected() -> None:
    with pytest.raises(ConfigSchemaError, match="ladder"):
        parse(
            cfg(
                """\
                units:
                  cheap:
                    address: http://localhost:8080
                    model: qwen2.5-coder:7b
                ladder: []
                """
            )
        )


# --- no credential can be expressed as a literal --------------------------


def test_a_credential_key_is_rejected_with_the_right_remedy() -> None:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            LOCAL_ONLY.replace("    width: 3", "    api_key: sk-not-a-real-key-value")
        )
    assert "api_key_env" in str(exc.value), "point at the key that IS allowed"


def test_a_credential_shaped_value_is_rejected_even_in_an_allowed_key() -> None:
    """`api_key_env` takes a NAME. Putting the key there is the likely slip."""
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            LOCAL_ONLY.replace(
                "    width: 3",
                "    api_key_env: sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA",
            )
        )
    assert "NAME" in str(exc.value) or "name" in str(exc.value)


def test_an_env_key_that_is_not_a_variable_name_is_rejected() -> None:
    """The likely slip is pasting a value; the likely typo is pasting a path."""
    with pytest.raises(ConfigSchemaError) as exc:
        parse(
            LOCAL_ONLY.replace(
                "    width: 3", "    api_key_env: ~/.config/anthropic/key"
            )
        )
    assert "is not an environment variable name" in str(exc.value)


def test_a_credential_shaped_value_anywhere_is_rejected() -> None:
    with pytest.raises(CredentialInConfigError, match="Rotate"):
        parse(LOCAL_ONLY.replace("model: qwen2.5-coder:7b", "model: ghp_" + "A" * 36))


def test_secrets_resolve_from_the_environment_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse(
        cfg(
            """\
            units:
              ceiling:
                address: https://api.anthropic.com
                model: claude-opus-5
                rig: cloud
                api_key_env: MCGYVR_TEST_KEY
            ladder:
            - ceiling
            """
        )
    )
    monkeypatch.setenv("MCGYVR_TEST_KEY", "resolved-at-point-of-use")
    assert config.secret("units.ceiling.api_key_env") == "resolved-at-point-of-use"


def test_an_unset_environment_variable_names_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct from an unbound key: the config named a variable, it is just empty."""
    config = parse(
        cfg(
            """\
            units:
              ceiling:
                address: https://api.anthropic.com
                model: claude-opus-5
                rig: cloud
                api_key_env: MCGYVR_TEST_KEY
            ladder:
            - ceiling
            """
        )
    )
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    with pytest.raises(UnboundValueError) as exc:
        config.secret("units.ceiling.api_key_env")
    assert "MCGYVR_TEST_KEY is not set" in str(exc.value)
    assert "never write the value into the config" in str(exc.value)


# --- file handling --------------------------------------------------------


def test_a_missing_file_says_how_to_get_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two answers, and which is right turns on who chose the path.

    This asked for "run ``mcgyvr init``" from a path passed straight in, and
    got it because that was the answer to everything — including to a caller
    who had named a file and mistyped it. The remedy now follows the naming
    (see ``tests/test_a_command_told_where_the_config_is_...``), so the
    generative half is asserted where it belongs: on the location nobody named.
    """
    monkeypatch.delenv(CONFIG_PATH_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigFileError, match="mcgyvr init"):
        load()
    with pytest.raises(ConfigFileError, match="Name one that is there"):
        load(tmp_path / "absent.yaml")


def test_malformed_yaml_is_reported_as_such(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    path.mkdir()
    (path / "fleet.yaml").write_text("version: 1\n  bad: indent\n", encoding="utf-8")
    with pytest.raises(ConfigSchemaError, match="not valid YAML"):
        load(path)


def test_an_empty_file_is_not_an_empty_config(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    path.mkdir()
    (path / "fleet.yaml").write_text("# nothing but a comment\n", encoding="utf-8")
    with pytest.raises(ConfigSchemaError, match="is empty"):
        load(path)


def test_a_version_key_is_retired() -> None:
    with pytest.raises(ConfigSchemaError, match=r"version|fleet"):
        parse(LOCAL_ONLY.replace("units:", "version: 1\nunits:"))


def test_loaded_config_remembers_where_it_came_from(tmp_path: Path) -> None:
    from tests._helpers import write_setup

    path = write_setup(tmp_path / "setup", LOCAL_ONLY)
    config = load(path)
    assert config.path == path
    # Errors raised later must be able to say which file to edit.
    with pytest.raises(UnboundValueError, match=str(path)):
        config.require("orchestrator.source")


def test_the_config_path_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "elsewhere.yaml"))
    assert config_path() == tmp_path / "elsewhere.yaml"


# --- the schema is the single source of truth -----------------------------


def _all_fields(fields: tuple[Field, ...]) -> list[tuple[str, Field]]:
    out: list[tuple[str, Field]] = []
    for spec in fields:
        out.append((spec.name, spec))
        out.extend((f"{spec.name}.{n}", f) for n, f in _all_fields(spec.block))
    return out


def test_every_schema_field_documents_itself() -> None:
    """The config reference is generated from these docs, so a blank one ships blank."""
    for path, spec in _all_fields(SCHEMA):
        assert spec.doc.strip(), f"{path} has no documentation"


def test_optional_leaf_fields_without_a_default_carry_a_bind_hint() -> None:
    """A point-of-use failure has to say how to fix itself."""
    structural = {"block", "block_map", "block_list", "str_list"}
    for path, spec in _all_fields(SCHEMA):
        if spec.required or spec.kind in structural or spec.default is not None:
            continue
        assert spec.bind_hint, f"{path} can be unbound but never says how to bind it"


def test_field_lookup_skips_map_keys_and_list_indexes() -> None:
    found = field_at("units.local.api_key_env")
    assert found is not None and found.name == "api_key_env"
    assert field_at("units.local.nonexistent") is None
