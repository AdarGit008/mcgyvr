"""The one credential vocabulary is a floor: nothing any of the four checks
refused before the lists were merged is let through after.

Four checks used to decide what a credential is, each from its own list: the
gate's secret scan, the config loader's refusal of a pasted key, the sandbox's
environment filter and its rc-file check. ``mcgyvr.credential_shapes`` is now the
one place that policy lives. These tests pin two things the merge had to keep
true:

* **The value shapes are the widest of the old lists.** Where the gate and the
  config loader disagreed on a length or a character class, the shape kept is
  the one that matches *more*, so a key that either used to refuse is still
  refused by both — through the gate's search-anywhere anchoring and the config
  loader's whole-value anchoring alike. The headline gap this closes is an
  ``sk-proj-...`` key whose hyphens stopped the gate's old ``[A-Za-z0-9]{20,}``
  run while the config loader refused it: both refuse it now.
* **The name words are one vocabulary, matched three ways.** The config loader
  matches an exact key, the sandbox env filter a word inside a variable name,
  the rc-file check a word followed by ``=``. Every word any list held is in
  the shared set, so a name refused in one place is no longer passed in another.

Secret-shaped fixtures are assembled at runtime, never written as a literal, so
no high-signal secret is committed to this source file — the same precaution
``tests/test_secrets.py`` takes, so the gate's own scan and push protection do
not flag the fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import CredentialInConfigError, _reject_credential_key
from mcgyvr.config import _reject_credential_literal as reject_value
from mcgyvr.credential_shapes import (
    CREDENTIAL_WORDS,
    NAME_ASSIGNMENT,
    VALUE_SHAPES,
    scan_pattern,
    whole_value_pattern,
)
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.secrets import scan_secrets
from mcgyvr.sandbox.base import is_credential_var

# Runtime-assembled samples: (code, value). Each is a credential of its shape at
# the shared vocabulary's floor length, so a shape that quietly tightened would
# drop it.
_GHP = "ghp_" + "a" * 20  # old gate needed exactly 36; floor is now 20
_PAT = "github_pat_" + "b" * 20  # old gate needed 22; floor is now 20
_GOOGLE = "AIza" + "c" * 30  # old gate needed exactly 35; floor is now 30
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
_SLACK = "xox" + "b-" + "1" * 12 + "-" + "d" * 16
_STRIPE = "sk" + "_live_" + "e" * 24  # the config loader had no Stripe shape
_SK_PLAIN = "sk-" + "f" * 16  # old gate needed 20 plain chars; floor is 16
_SK_PROJ = "sk-" + "proj-" + "g1h2-i3j4-k5l6-m7n8"  # hyphens; old gate missed it
_PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"  # config had no key shape

_SAMPLES: list[tuple[str, str]] = [
    ("github-token", _GHP),
    ("github-pat", _PAT),
    ("google-api-key", _GOOGLE),
    ("aws-access-key-id", _AWS),
    ("slack-token", _SLACK),
    ("stripe-secret-key", _STRIPE),
    ("openai-key", _SK_PLAIN),
    ("openai-key", _SK_PROJ),
    ("private-key", _PRIVATE_KEY),
]


def _one_file(repo: Path, text: str) -> ChangeSet:
    (repo / "c.py").write_text(text, encoding="utf-8")
    change = FileChange("c.py", "A", frozenset({1}), is_binary=False)
    return ChangeSet(repo=repo, base="HEAD", files=(change,))


@pytest.mark.parametrize("code, value", _SAMPLES)
def test_every_shape_is_refused_by_both_anchorings(code: str, value: str) -> None:
    """One shape, two anchorings, one verdict: refuse.

    The whole-value pattern is what the config loader applies; the scan pattern
    is what the gate applies to a line. A sample at the floor length must match
    both, which is the property the merge exists to guarantee — the two checks
    reading one policy.
    """
    shape = next(s for s in VALUE_SHAPES if s.code == code)
    assert whole_value_pattern(shape).match(value), f"config would pass {code}"
    assert scan_pattern(shape).search(f"x = {value!r}"), f"gate would pass {code}"


@pytest.mark.parametrize("code, value", _SAMPLES)
def test_the_gate_scan_flags_every_shape(tmp_path: Path, code: str, value: str) -> None:
    """The gate's own entry point reports the shape on an added line."""
    findings = scan_secrets(_one_file(tmp_path, f"tok = {value!r}\n"))
    assert code in {f.code for f in findings}, f"gate missed {code}: {findings}"


@pytest.mark.parametrize("code, value", _SAMPLES)
def test_the_config_loader_refuses_every_shape(code: str, value: str) -> None:
    """The config loader refuses a value that is exactly one shape.

    Stripe and the private-key header reach this check only now — they were the
    gate's alone before — and that is the point: the config loader refuses
    everything the gate's scan would, not a subset of it.
    """
    with pytest.raises(CredentialInConfigError):
        reject_value(value, "units.cheap.api_key_env")


def test_sk_proj_key_slipped_the_old_gate_and_does_not_now(tmp_path: Path) -> None:
    """The gap the merge closes, written out.

    The old gate scan ran ``[A-Za-z0-9]{20,}`` after ``sk-``; the first hyphen of
    an ``sk-proj-...`` key ended that run before it reached twenty, so the gate
    passed a key the config loader refused. The shared shape allows ``-`` and
    ``_`` and drops the floor to sixteen, so both refuse it.
    """
    findings = scan_secrets(_one_file(tmp_path, f"k = {_SK_PROJ!r}\n"))
    assert "openai-key" in {f.code for f in findings}


def test_config_key_names_are_an_exact_match_over_the_shared_words() -> None:
    """The config loader's rule is an exact key, drawn from the shared words.

    ``session`` is in the vocabulary because the sandbox filter held it; the
    config loader now refuses a key named exactly ``session`` too, where it did
    not before. A word only *inside* a key name is not an exact match and passes.
    """
    for word in CREDENTIAL_WORDS:
        with pytest.raises(CredentialInConfigError):
            _reject_credential_key(word, "units.cheap")
    _reject_credential_key("session_count", "units.cheap")  # not an exact key
    _reject_credential_key("width", "units.cheap")


def test_env_names_match_the_shared_words_as_a_substring() -> None:
    """The sandbox env filter's rule is a word inside the variable name.

    Every vocabulary word makes an upper-cased variable name a credential, and
    ``OAUTH_CLIENT`` matches now because the shared ``auth`` word is no longer
    fenced to ``_auth`` — a strictly wider refusal than before.
    """
    for word in CREDENTIAL_WORDS:
        name = f"MY_{word.upper()}_VALUE"
        assert is_credential_var(name), f"env filter passed {name}"
    assert is_credential_var("OAUTH_CLIENT_ID")
    assert not is_credential_var("HOME")


def test_rc_login_lines_match_the_shared_words_before_an_assignment() -> None:
    """The rc-file check's rule is a word then ``=`` or ``:``.

    It now covers ``key``, ``apikey``, ``credential`` and ``session`` as well as
    the ``auth``/``token``/``password``/``secret`` it always did, so a login line
    in a ``.npmrc``-style file is caught whichever word it uses.
    """
    for word in ("key", "apikey", "credential", "session", "auth", "token"):
        assert NAME_ASSIGNMENT.search(f"{word}=value"), word
        assert NAME_ASSIGNMENT.search(f"{word}: value"), word
    assert not NAME_ASSIGNMENT.search("registry=https://example.invalid")
