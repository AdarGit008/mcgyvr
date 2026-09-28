"""The two keys sleep/wake is asked for by, and where a wake's limit comes from.

Three decisions are pinned, and all three are the owner's rather than this
file's:

* **The switch is a config key and not a flag**
  (``mcgyvr-lab/records/plans/sleep-wake.md`` §7.1). ``mcgyvr run --config``
  already says which rung runs is "this file's ... never a flag", and sleep/wake
  is the stronger case for the same rule: the config is what a run is
  reproducible from, so a flag would let two runs share one setup where one of
  them started and stopped containers on a shared rig. A ``store_true`` flag can
  also never lose to a key — the ``--sandbox`` comment is the worked example —
  so the flag would have to be a tri-state, which is a worse spelling of the key.
* **The default is off** (sleep-wake.md §14). The feature is a trade and not an
  improvement: turning it on lets ``mcgyvr run`` stop containers on a rig other
  people share. An operator who wants it asks in the one place that is recorded.
* **A wake's limit is the lock's, not a budget's**
  (``mcgyvr-lab/records/plans/fleet-identity.md`` §5). ``request_timeout_s``
  bounds one reply and is priced from tokens per second; ``task_timeout_s``
  bounds a wait for a free slot on a server that is already running. Neither
  bounds a wait for a server *to exist*: that is the unit's validated wake plus
  the lock's wake tolerance, because the lock is where the validated wake and
  the tolerance are committed.
"""

from __future__ import annotations

import pytest

#: One card, two vLLM sources. Every worked example in the sleep-wake design is
#: this card because it is the multi-unit one, which is the harder case; the
#: engine on a card decides nothing (N10).
CARD = """\
units:
  local_qwen2.5-coder-3b:
    address: http://srv2:8001
    model: qwen2.5-coder-3b
    rig: srv2_3b
    width: 2
    engine: vllm
  local_qwen2.5-coder-7b:
    address: http://srv2:8002
    model: qwen2.5-coder-7b
    rig: srv2_7b
    width: 2
    engine: vllm
ladder:
- local_qwen2.5-coder-3b
- local_qwen2.5-coder-7b
"""


def test_a_config_that_says_nothing_has_sleep_and_wake_turned_off() -> None:
    """The default is the safe value, and it is filled in rather than absent.

    ``False`` and not ``None``: a run that did not ask is recorded as not
    having asked, which is the same discipline ``budgets.max_window_fraction``
    states for its own unset case. A caller reading the loaded tree must be
    able to see the answer without knowing that the key was omitted.
    """
    from mcgyvr.config import parse

    config = parse(CARD)

    assert config.get("serving.enable_sleep_wake") is False, (
        "a config that says nothing about sleep and wake did not read as off. "
        "The switch has no schema entry, so nothing fills a default and the "
        "feature's own default cannot be read from a loaded config at all"
    )


def test_a_config_that_asks_for_sleep_and_wake_is_not_refused_as_an_unknown_key() -> (
    None
):
    """``serving.enable_sleep_wake`` is a key of the schema, and it is honoured.

    The block is ``serving.`` and not ``ladder.`` because ``ladder.fanout``
    decides where work goes among rungs *that exist*, and this decides whether
    rungs come into existence — two authorities, and only one of them touches a
    rig (§7.1).
    """
    from mcgyvr.config import parse

    config = parse(CARD + "serving:\n  enable_sleep_wake: true\n")

    assert config.get("serving.enable_sleep_wake") is True


def test_the_directory_this_checkout_keeps_launch_specs_in_is_a_key_of_its_own() -> (
    None
):
    """``serving.compose_dir`` — one key, a directory, and not a device (D1).

    The one schema addition the design allows is not a card and not a host: it
    states where *this checkout* keeps the launch specs ``mcgyvr emit`` wrote,
    because ``mcgyvr emit --out`` defaults to the current directory and the wake
    path has to find the file again. It cannot go stale against a re-pointed
    source the way a ``device:`` on a source would, and a config that omits it
    has no sleeping cards at all — only down ones (D2).
    """
    from mcgyvr.config import parse

    config = parse(CARD + "serving:\n  compose_dir: /etc/mcgyvr/config\n")

    assert str(config.get("serving.compose_dir")) == "/etc/mcgyvr/config"


def test_a_wake_has_no_budget_of_its_own() -> None:
    """``budgets.wake_timeout_s`` is gone; request and task budgets remain.

    No wake limit is set by hand beside the other two budgets. This pins the
    absence of the key while keeping the two budgets that still answer different
    questions, so the removal cannot silently take the whole ``budgets`` block
    with it.
    """
    from mcgyvr.config import field_at, parse

    card = CARD.replace(
        "    width: 2\n    engine: vllm\n",
        "    width: 2\n    engine: vllm\n    request_timeout_s: 30.0\n",
        1,
    )
    config = parse(card + "task_timeout_s: 60\n")

    assert field_at("budgets.wake_timeout_s") is None, (
        "budgets.wake_timeout_s is a schema key: a wake has no hand-set budget"
    )
    assert config.units["local_qwen2.5-coder-3b"].request_timeout_s == 30.0
    assert config.get("task_timeout_s") == 60


def test_the_wake_limit_is_the_validated_wake_plus_its_tolerance() -> None:
    """The lock's wake limit is a unit's validated wake plus the lock's tolerance.

    The values are placeholders; the rule is the lock's.
    """
    from mcgyvr.fleet.lock import wake_limit_s

    assert wake_limit_s(20.0, {"s": 0.5}) == pytest.approx(20.5)
    assert wake_limit_s(0.25, {"s": 0.1}) == pytest.approx(0.35)


def test_the_doors_health_budget_is_not_a_wake_budget() -> None:
    """The door polls a unit into health; that poll is not a configured budget.

    ``HEALTH_POLLS`` and ``HEALTH_INTERVAL_S`` describe what ``serve up`` does.
    Keeping the door's own budget while dropping ``budgets.wake_timeout_s`` is
    the point: the config holds no wake budget.
    """
    from mcgyvr.config import field_at
    from mcgyvr.serving.servelib import HEALTH_INTERVAL_S, HEALTH_POLLS

    assert HEALTH_POLLS * HEALTH_INTERVAL_S > 0, (
        "the door's own health budget disappeared along with the wake budget"
    )
    assert field_at("budgets.wake_timeout_s") is None, (
        "budgets.wake_timeout_s is a schema key beside the door's health budget"
    )
