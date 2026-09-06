"""``contract / whole_window <= X``: the share of a rung one contract may claim.

The existing fit check asks whether a contract's prompt and its own reply can
*fit* a window at all. This asks a different question: how much of the window
one contract is allowed to want. A contract that fits with nothing to spare
leaves a rung unable to hold anything else and unable to absorb an estimate
that ran long, and "it fits" cannot see either.

``X`` is declared per run rather than fixed here, so a refusal is reproducible
from the run's record rather than from a constant this module chose. Absent, no
fraction is enforced: an invented default would be exactly the unsourced number
the project refuses elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigError
from mcgyvr.config import load as load_config
from mcgyvr.gate.preflight import PreflightIssue, check_window_fraction

CONFIG = """
version: 1
sources:
  local:
    base_url: "http://127.0.0.1:8080"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local
      source: local
      model: a-model
journal:
  dir: /nowhere/configured
"""


def _config(tmp_path: Path, budgets: str = "") -> object:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(CONFIG + budgets, encoding="utf-8")
    return load_config(path)


def test_a_declared_fraction_resolves(tmp_path: Path) -> None:
    config = _config(tmp_path, "budgets:\n  max_window_fraction: 0.6\n")
    assert config.get("budgets.max_window_fraction") == 0.6


def test_no_fraction_declared_resolves_to_nothing(tmp_path: Path) -> None:
    """Unset is an answer -- "no share is enforced" -- and never a default.

    A number invented here would bound every run on every install that never
    asked for one, and would do it with a figure nobody measured.
    """
    assert _config(tmp_path).get("budgets.max_window_fraction") is None


def test_a_fraction_above_one_is_refused(tmp_path: Path) -> None:
    """More than the whole window is not a share of it."""
    with pytest.raises(ConfigError) as caught:
        _config(tmp_path, "budgets:\n  max_window_fraction: 1.5\n")
    assert "max_window_fraction" in str(caught.value)
    assert "1" in str(caught.value)


def test_a_negative_fraction_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        _config(tmp_path, "budgets:\n  max_window_fraction: -0.1\n")


def test_a_contract_inside_its_share_passes() -> None:
    """1024 of a 4096 window is a quarter, and a half was allowed."""
    assert check_window_fraction(1024, context_window=4096, fraction=0.5) is None


def test_a_contract_exactly_at_its_share_passes() -> None:
    """The bound is inclusive: ``<=``, as declared, not ``<``."""
    assert check_window_fraction(2048, context_window=4096, fraction=0.5) is None


def test_a_contract_over_its_share_is_refused() -> None:
    """Refused with both fractions named, so the reader can see the gap.

    The claim and the allowance are both on the message because the fix
    differs by which one is wrong: a contract to re-decompose, or a share to
    re-declare.
    """
    issue = check_window_fraction(3072, context_window=4096, fraction=0.5)
    assert isinstance(issue, PreflightIssue)
    assert issue.reason == "window-share"
    assert "0.75" in issue.message
    assert "0.50" in issue.message
    assert "3072" in issue.message and "4096" in issue.message


def test_no_fraction_enforces_nothing() -> None:
    """A run that declared no share is not silently given one."""
    assert check_window_fraction(4096, context_window=4096, fraction=None) is None


def test_a_zero_window_is_refused_rather_than_divided_by() -> None:
    """A rung with no window is a routing error, not a division."""
    issue = check_window_fraction(1, context_window=0, fraction=0.5)
    assert issue is not None and issue.reason == "window-share"


# --- the share is the contract's, and the config's only as a fallback ------


CONTRACT = """
id: c1
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


def test_a_contract_declares_its_own_share() -> None:
    """The share rides on the contract, beside the reply cap it is measured with.

    ``limits`` is where a contract already states what one execution of it may
    cost, and a share of the window is that same kind of statement — not a
    property of the ladder, which is why it is not a flag and not the config's
    to fix.
    """
    from mcgyvr.contract import loads

    contract = loads(CONTRACT + "limits:\n  max_window_fraction: 0.6\n")
    assert contract.limits.max_window_fraction == 0.6


def test_a_contract_that_declares_no_share_carries_none() -> None:
    """Absent on the contract is absent, not a default the loader invented."""
    from mcgyvr.contract import loads

    assert loads(CONTRACT).limits.max_window_fraction is None


def test_a_share_above_one_is_refused_on_a_contract_too() -> None:
    from mcgyvr.contract import ContractError, loads

    with pytest.raises(ContractError) as caught:
        loads(CONTRACT + "limits:\n  max_window_fraction: 1.4\n")
    assert "max_window_fraction" in str(caught.value)


def test_a_declared_share_survives_a_round_trip() -> None:
    """A contract that states a share re-loads with it: the emitted form is
    the contract, and a key that vanished there would be a share nobody could
    reproduce a refusal from."""
    import json

    from mcgyvr.contract import loads

    stated = loads(CONTRACT + "limits:\n  max_window_fraction: 0.6\n")
    assert loads(json.dumps(stated.as_dict())).limits.max_window_fraction == 0.6


# --- the two checks together, at the one seam that runs both --------------


def _contract(limits: str = "") -> object:
    from mcgyvr.contract import loads

    return loads(CONTRACT + "limits:\n  max_output_tokens: 512\n" + limits)


def test_a_contract_within_both_bounds_passes() -> None:
    from mcgyvr.gate.preflight import check_contract_fits

    assert (
        check_contract_fits(_contract("  max_window_fraction: 0.9\n"), "x" * 400, 4096)
        is None
    )


def test_the_share_is_refused_on_a_contract_that_still_fits() -> None:
    """The point of the share: it fits, and it is still too much of the rung.

    2400 characters estimate to 600 tokens, charged to 792, plus a 512 reply
    is 1304 of a 2048 window -- inside it, and 0.64 of it against a declared
    half.
    """
    from mcgyvr.gate.preflight import check_contract_fits

    issue = check_contract_fits(
        _contract("  max_window_fraction: 0.5\n"), "x" * 2400, 2048
    )
    assert issue is not None and issue.reason == "window-share"


def test_a_contract_that_cannot_fit_is_named_as_that_and_not_as_a_share() -> None:
    """One failure, the harder one. Re-declaring a share would not fix this."""
    from mcgyvr.gate.preflight import check_contract_fits

    issue = check_contract_fits(
        _contract("  max_window_fraction: 0.5\n"), "x" * 40000, 2048
    )
    assert issue is not None and issue.reason == "prompt-too-large"


def test_a_standing_default_applies_only_where_the_contract_is_silent() -> None:
    """A contract that stated a share is not overruled by the caller's default.

    The contract's text has to stay true: a config that could tighten or
    loosen a share the contract declared would make the contract a suggestion.
    """
    from mcgyvr.gate.preflight import check_contract_fits

    silent = _contract()
    assert check_contract_fits(silent, "x" * 2400, 2048) is None
    assert (
        check_contract_fits(silent, "x" * 2400, 2048, default_fraction=0.5) is not None
    )
    stated = _contract("  max_window_fraction: 0.9\n")
    assert check_contract_fits(stated, "x" * 2400, 2048, default_fraction=0.5) is None
