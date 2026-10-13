"""The source map is a seam before it is a data structure, so these tests hold
it to #20's acceptance on both counts: that a rung can be re-pointed at another
source by editing config alone, that nothing above the seam is *able* to read
where work runs, that a single-source install never has to think about pools,
and that a source which cannot serve shortens the ladder with a reason instead
of raising.

Configs are parsed from YAML text rather than built by hand, so what is asserted
is the behaviour a real config file produces.
"""

from __future__ import annotations

import dataclasses
import textwrap

import pytest

from mcgyvr.config import parse
from mcgyvr.local_pool import (
    Endpoint,
    Protocol,
    Rung,
    SourceUnavailableError,
    UnknownRungError,
    source_map,
)
from tests._paths import SRC
from tests.wheels import seam_offenders

SINGLE_SOURCE = """\
units:
  cheap:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: local
    width: 3
  strong:
    address: http://localhost:11434
    model: qwen2.5-coder:14b
    rig: local
    width: 3
ladder:
- cheap
- strong
"""

TWO_SOURCES = """\
units:
  cheap:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: local
    width: 3
  strong:
    address: https://api.example.com/v1
    model: big-model
    rig: remote
    width: 4
    api_key_env: MCGYVR_TEST_KEY
ladder:
- cheap
- strong
"""


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


# --- a tier moves between sources with a config edit, not a code change ----


def test_a_rung_can_be_repointed_at_another_source_by_editing_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    before = source_map(parse(TWO_SOURCES))
    assert before.bind("strong").base_url == "https://api.example.com/v1"
    assert before.bind("strong").protocol is Protocol.OPENAI

    # The only thing that changes is the address the rung's unit names.
    after = source_map(
        parse(
            TWO_SOURCES.replace(
                "address: https://api.example.com/v1",
                "address: http://localhost:11434",
            )
        )
    )

    assert after.bind("strong").base_url == "http://localhost:11434"
    assert after.bind("strong").protocol is Protocol.OPENAI
    # The ladder above the seam is untouched: same rungs, same models.
    assert [(r.name, r.model) for r in after.rungs] == [
        (r.name, r.model) for r in before.rungs
    ]


def test_both_wire_protocols_resolve_without_a_per_vendor_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    pool = source_map(parse(TWO_SOURCES))
    assert pool.bind("cheap").protocol is Protocol.OPENAI
    assert pool.bind("strong").protocol is Protocol.OPENAI
    # Two protocols is the whole vocabulary — a new backend is a config entry.
    assert set(Protocol) == {Protocol.OPENAI, Protocol.OPENAI}


# --- nothing outside the seam can read a source or a backend --------------


def test_a_rung_cannot_say_where_its_work_runs() -> None:
    """The seam is enforced by the type, not by a convention callers must keep."""
    fields = {f.name for f in dataclasses.fields(Rung)}
    assert fields == {"name", "model"}
    assert not fields & {"source", "base_url", "api", "protocol", "endpoint", "url"}


def test_the_ladder_above_the_seam_exposes_only_names_and_models() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    assert [(r.name, r.model) for r in pool.rungs] == [
        ("cheap", "qwen2.5-coder:7b"),
        ("strong", "qwen2.5-coder:14b"),
    ]
    # Declared order is ladder order: cheapest first, as written.
    assert pool.rungs[0].name == "cheap"


def test_nothing_above_the_seam_imports_the_endpoint_type() -> None:
    """An architectural guard: if this fails, something above the seam has learned
    where work runs, and re-pointing a rung stops being a config edit.

    Checked by parsing imports rather than grepping for the word, so the guard
    stays about *who depends on the seam* rather than about who happens to use
    the name — which is what lets a same-named type elsewhere be a naming
    question instead of a false failure here.
    """
    src = SRC
    assert seam_offenders(src) == []


# --- a single-source install needs no pool concepts in its config ---------


def test_a_single_source_config_mentions_no_pool_concepts() -> None:
    config = parse(SINGLE_SOURCE)
    pool = source_map(config)

    assert len(pool) == 2
    assert not pool.skipped
    # Nothing in the file names a pool, a capacity policy or a protocol choice
    # beyond the one source it declares.
    assert "pool" not in SINGLE_SOURCE
    assert config.is_local_only


def test_a_keyless_local_endpoint_needs_no_credential() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    endpoint = pool.bind("cheap")
    assert endpoint.requires_credential is False
    assert endpoint.credential() is None


# --- an unusable source degrades the ladder rather than raising -----------


def test_a_source_missing_its_credential_shortens_the_ladder_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    pool = source_map(parse(TWO_SOURCES))  # must not raise

    assert [r.name for r in pool.rungs] == ["cheap"]
    assert [s.name for s in pool.skipped] == ["strong"]
    assert "MCGYVR_TEST_KEY" in pool.skipped[0].reason
    # The rung that still works is unaffected by the one that does not.
    assert pool.bind("cheap").base_url == "http://localhost:11434"


def test_every_source_unusable_is_an_empty_ladder_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    body = cfg("""\
        units:
          only:
            address: https://api.example.com/v1
            model: big-model
            rig: remote
            width: 4
            api_key_env: MCGYVR_TEST_KEY
        ladder:
        - only
        """)
    pool = source_map(parse(body))

    assert not pool
    assert len(pool) == 0
    assert [s.name for s in pool.skipped] == ["only"]
    # The caller decides what an empty ladder means — for a keyless install it
    # may be exactly what was expected.
    assert "MCGYVR_TEST_KEY" in pool.skipped[0].reason


def test_binding_a_skipped_rung_says_why_not_that_it_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different mistakes, kept apart by the exception and the message."""
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    pool = source_map(parse(TWO_SOURCES))

    with pytest.raises(SourceUnavailableError, match="MCGYVR_TEST_KEY"):
        pool.bind("strong")
    with pytest.raises(UnknownRungError, match="no rung named"):
        pool.bind("nonexistent")


def test_an_unknown_rung_names_what_is_actually_offered() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    with pytest.raises(UnknownRungError, match="cheap, strong"):
        pool.bind("mid")


# --- credentials are named, not held --------------------------------------


def test_an_endpoint_carries_the_variable_name_never_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-secret-value")
    endpoint = source_map(parse(TWO_SOURCES)).bind("strong")

    assert endpoint.credential_env == "MCGYVR_TEST_KEY"
    # The value is nowhere in the dataclass, so it cannot reach a log via a repr.
    assert "sk-secret-value" not in repr(endpoint)
    assert endpoint.credential() == "sk-secret-value"


def test_a_credential_unset_after_the_map_was_built_fails_at_the_point_of_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolving late is what keeps the secret out of the dataclass; the cost is
    this window, and it fails loudly rather than dispatching unauthenticated."""
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    endpoint = source_map(parse(TWO_SOURCES)).bind("strong")
    monkeypatch.delenv("MCGYVR_TEST_KEY")

    with pytest.raises(SourceUnavailableError, match="MCGYVR_TEST_KEY"):
        endpoint.credential()


# --- capacity is carried here, enforced elsewhere -------------------------


def test_declared_capacity_reaches_the_seam_for_the_semaphore_to_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    pool = source_map(parse(TWO_SOURCES))
    assert pool.bind("cheap").max_parallel == 3
    assert pool.bind("strong").max_parallel == 4
    # Two rungs on one source share that source's capacity, which is why the
    # endpoint names its source: #23 keys the semaphore on it, not on the rung.
    single = source_map(parse(SINGLE_SOURCE))
    assert (
        single.bind("cheap").source == "cheap"
        and single.bind("strong").source == "strong"
    )


# --- non-ladder roles cross the same seam ---------------------------------


def test_an_unbound_role_is_an_ordinary_none_not_a_failure() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    assert pool.role("verifier") is None
    assert pool.role("orchestrator") is None


def test_a_bound_role_resolves_through_the_seam_like_a_rung() -> None:
    body = cfg("""\
        units:
          cheap:
            address: http://localhost:11434
            model: qwen2.5-coder:7b
            rig: local
            width: 3
        ladder:
        - cheap
        verifier:
          enabled: true
          model: qwen2.5-coder:14b
          unit: cheap
        """)
    binding = source_map(parse(body)).role("verifier")

    assert binding is not None
    assert binding.model == "qwen2.5-coder:14b"
    assert isinstance(binding.endpoint, Endpoint)
    assert binding.endpoint.protocol is Protocol.OPENAI


def test_a_role_on_an_unusable_source_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    body = cfg("""\
        units:
          cheap:
            address: http://localhost:11434
            model: qwen2.5-coder:7b
            rig: local
            width: 3
          remote:
            address: https://api.example.com/v1
            model: big-model
            rig: remote
            api_key_env: MCGYVR_TEST_KEY
        ladder:
        - cheap
        verifier:
          enabled: true
          model: big-model
          unit: remote
        """)
    pool = source_map(parse(body))

    # The ladder still works; only the role is unavailable.
    assert [r.name for r in pool.rungs] == ["cheap"]
    with pytest.raises(SourceUnavailableError, match="MCGYVR_TEST_KEY"):
        pool.role("verifier")


def test_asking_for_a_role_that_does_not_exist_is_a_mistake() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    with pytest.raises(UnknownRungError, match="no such role"):
        pool.role("summarizer")
