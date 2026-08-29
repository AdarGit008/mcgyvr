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

import ast
import dataclasses
import textwrap
from pathlib import Path

import pytest

from mcgyvr.config import parse
from mcgyvr.pool import (
    Endpoint,
    Protocol,
    Rung,
    SourceUnavailableError,
    UnknownRungError,
    source_map,
)

SINGLE_SOURCE = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
    - name: strong
      source: local
      model: qwen2.5-coder:14b
"""

TWO_SOURCES = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
  remote:
    base_url: https://api.example.com/v1
    api: openai
    max_parallel: 4
    api_key_env: MCGYVR_TEST_KEY
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
    - name: strong
      source: remote
      model: big-model
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

    # The only thing that changes is which source the rung names.
    after = source_map(parse(TWO_SOURCES.replace("source: remote", "source: local")))

    assert after.bind("strong").base_url == "http://localhost:11434"
    assert after.bind("strong").protocol is Protocol.OLLAMA
    # The ladder above the seam is untouched: same rungs, same models.
    assert [(r.name, r.model) for r in after.rungs] == [
        (r.name, r.model) for r in before.rungs
    ]


def test_both_wire_protocols_resolve_without_a_per_vendor_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    pool = source_map(parse(TWO_SOURCES))
    assert pool.bind("cheap").protocol is Protocol.OLLAMA
    assert pool.bind("strong").protocol is Protocol.OPENAI
    # Two protocols is the whole vocabulary — a new backend is a config entry.
    assert set(Protocol) == {Protocol.OLLAMA, Protocol.OPENAI}


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


# The modules allowed to hold an `Endpoint`, which is to say the ones that live
# *below* the seam. `pool.py` defines it; `runner.py` (#21) is what it was
# defined for — dispatch is the whole reason the type exists, and a runner is
# the last place that can still be said to not know who asked. Anything else
# reaching for it is the failure this guard is here to catch, so the list is
# named rather than pattern-matched: a third entry should be an argument
# someone makes on purpose, not a file that quietly matched.
#
# `availability.py` (#22) is the third, added deliberately. The argument: it
# does the same kind of thing a runner does — it takes an endpoint and sends it
# a request over the network — and it is the only other module that needs a
# base URL and a protocol to do its job. Crucially it does not travel *upward*:
# `source_map` consults it through `SourceProbe`, which passes endpoints down
# and gets back a mapping of source name to reason, so nothing above the seam
# gains a way to learn where a rung runs. If a future module wants on this list
# because it "just needs the URL", that is the case this guard exists to make
# someone argue.
#
# `capacity.py` (#23) is the fourth, and its argument is narrower than
# availability's. It never talks to anything: of an endpoint it reads exactly two
# fields, `source` — the key its semaphores are held under — and `max_parallel`,
# the number it is enforcing. It touches neither `base_url` nor `protocol` nor
# the credential, so it cannot dispatch even by accident. And it is the use
# `Endpoint` itself names: "``source`` is the declared source name, kept for
# capacity accounting and telemetry — both of which live below the seam"
# (`pool.py`). Nothing travels upward either — a caller above the seam hands
# `run_batch` a capacity and gets back outcomes, and never an endpoint.
#
# `cooldown.py` (D09) is the fifth, and it is capacity's argument rather than
# availability's. It never talks to anything: probing is delegated whole to
# `Availability`, and of an endpoint it reads exactly one field, `source` — the
# key its failure record is held under, which is the same key capacity holds its
# semaphores under and the use `Endpoint` itself names. It touches neither
# `base_url` nor `protocol` nor the credential, so it cannot dispatch even by
# accident. Nothing travels upward: `source_map` consults it through
# `SourceProbe` exactly as it consults availability, handing endpoints down and
# getting back a mapping of source name to reason.
#
# It is on this list rather than off it because the alternative was worse. The
# same import spelled `from mcgyvr.availability import Endpoint` — a re-export —
# would satisfy this guard while changing nothing about the dependency, which is
# defeating the guard by spelling instead of making the argument it asks for.
BELOW_THE_SEAM = {
    "pool.py",
    "runner.py",
    "availability.py",
    "capacity.py",
    "cooldown.py",
}


#: The names that carry a dispatchable endpoint. ``RoleBinding`` holds one, so
#: reaching either is reaching the same thing.
BELOW_THE_SEAM_NAMES = {"Endpoint", "RoleBinding"}


def seam_offenders(root: Path) -> list[str]:
    """Every way a module under ``root`` reaches an endpoint, with where.

    Three routes, because the guard was defeated by two of them. The original
    checked one shape — ``from mcgyvr.pool import Endpoint`` — and the 2026-08-29
    pressure test found the rule crossed anyway by ``import mcgyvr.pool`` and by
    a relative import, neither of which that shape matches, and once more by
    ``SourceMap.role()``, which needs no import at all: it *returns* a
    ``RoleBinding``, so a module could hold a live ``credential()`` while
    importing nothing. A guard with three known bypasses is not a weak guard, it
    is a guard that reports on spelling.

    ``role()`` is therefore treated as below-the-seam API and
    ``SourceMap.role_model()`` is what above it may call. The check is by
    method name, which will occasionally catch an unrelated ``.role(...)``: that
    is the intended direction, and the same argument the module list makes — a
    false positive costs someone an argument, a false negative costs the rule.
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in BELOW_THE_SEAM:
            continue
        where = path.relative_to(root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # `from mcgyvr.pool import Endpoint`, and the relative spelling of
            # the same import, which resolves to the same module.
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "mcgyvr.pool" or (node.level and module == "pool"):
                    imported = {alias.name for alias in node.names}
                    if imported & BELOW_THE_SEAM_NAMES:
                        offenders.append(f"{where}: imports {sorted(imported)}")
            # `import mcgyvr.pool`, which reaches every name in it.
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mcgyvr.pool":
                        offenders.append(f"{where}: imports the module whole")
            # `something.role(...)` — an endpoint through an accessor.
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "role":
                    offenders.append(f"{where}:{node.lineno}: calls .role()")
    return offenders


def test_nothing_above_the_seam_imports_the_endpoint_type() -> None:
    """An architectural guard: if this fails, something above the seam has learned
    where work runs, and re-pointing a rung stops being a config edit.

    Checked by parsing imports rather than grepping for the word, so the guard
    stays about *who depends on the seam* rather than about who happens to use
    the name — which is what lets a same-named type elsewhere be a naming
    question instead of a false failure here.
    """
    src = Path(__file__).resolve().parent.parent / "src" / "mcgyvr"
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
    body = cfg("""
        version: 1
        sources:
          remote:
            base_url: https://api.example.com/v1
            api: openai
            max_parallel: 4
            api_key_env: MCGYVR_TEST_KEY
        ladder:
          tiers:
            - name: only
              source: remote
              model: big-model
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
    assert single.bind("cheap").source == single.bind("strong").source == "local"


# --- non-ladder roles cross the same seam ---------------------------------


def test_an_unbound_role_is_an_ordinary_none_not_a_failure() -> None:
    pool = source_map(parse(SINGLE_SOURCE))
    assert pool.role("verifier") is None
    assert pool.role("orchestrator") is None


def test_a_bound_role_resolves_through_the_seam_like_a_rung() -> None:
    body = cfg("""
        version: 1
        sources:
          local:
            base_url: http://localhost:11434
            api: ollama
            max_parallel: 3
        ladder:
          tiers:
            - name: cheap
              source: local
              model: qwen2.5-coder:7b
        verifier:
          enabled: true
          source: local
          model: qwen2.5-coder:14b
    """)
    binding = source_map(parse(body)).role("verifier")

    assert binding is not None
    assert binding.model == "qwen2.5-coder:14b"
    assert isinstance(binding.endpoint, Endpoint)
    assert binding.endpoint.protocol is Protocol.OLLAMA


def test_a_role_on_an_unusable_source_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    body = cfg("""
        version: 1
        sources:
          local:
            base_url: http://localhost:11434
            api: ollama
            max_parallel: 3
          remote:
            base_url: https://api.example.com/v1
            api: openai
            max_parallel: 4
            api_key_env: MCGYVR_TEST_KEY
        ladder:
          tiers:
            - name: cheap
              source: local
              model: qwen2.5-coder:7b
        verifier:
          enabled: true
          source: remote
          model: big-model
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
