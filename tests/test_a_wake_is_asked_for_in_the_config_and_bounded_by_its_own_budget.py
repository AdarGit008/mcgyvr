"""The two keys sleep/wake is asked for by, and where a wake's limit comes from.

RED. ``src/mcgyvr/config.py`` has no ``serving`` block, and the hand-set
``budgets.wake_timeout_s`` is gone: a wake's limit now comes from the fleet
lock — a unit's validated wake plus the lock's wake tolerance
(``records/plans/fleet-identity.md`` §5). The two keys that ask for sleep and
wake at all are still config keys, and they are the only two.

Three decisions are pinned, and all three are the owner's rather than this
file's:

* **The switch is a config key and not a flag** (§7.1). ``mcgyvr run --config``
  already says which rung runs is "this file's ... never a flag", and sleep/wake
  is the stronger case for the same rule: ``Config.digest`` is what a run is
  reproducible from, so a flag would let two runs share one digest where one of
  them started and stopped containers on a shared rig. A ``store_true`` flag can
  also never lose to a key — the ``--sandbox`` comment is the worked example —
  so the flag would have to be a tri-state, which is a worse spelling of the key.
* **The default is off** (§14). The feature is a trade and not an improvement:
  turning it on lets ``mcgyvr run`` stop containers on a rig other people share.
  An operator who wants it asks in the one place that is recorded.
* **A wake's limit is the lock's, not a budget's** (§5). ``request_timeout_s``
  bounds one reply and is priced from tokens per second; ``task_timeout_s``
  bounds a wait for a free slot on a server that is already running. Neither
  bounds a wait for a server *to exist*: that is the unit's validated wake plus
  the lock's wake tolerance, because the lock is where the validated wake and
  the tolerance are committed.
"""

from __future__ import annotations

import pytest

#: One card, two vLLM sources, the shape of the live srv2 (§6). Every worked
#: example in the design is this card because it is the multi-unit one, which is
#: the harder case; the engine on a card decides nothing (N10, ruled 2026-09-08).
CARD = """
version: 1
sources:
  srv2_3b:
    base_url: http://srv2:8001
    api: openai
    engine: vllm
    max_parallel: 2
  srv2_7b:
    base_url: http://srv2:8002
    api: openai
    engine: vllm
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen2.5-coder-3b
      source: srv2_3b
      model: qwen2.5-coder-3b
    - name: local_qwen2.5-coder-7b
      source: srv2_7b
      model: qwen2.5-coder-7b
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

    The wake limit is derived from the lock, not set by hand beside the other
    two budgets. This pins the absence of the key while keeping the two budgets
    that still answer different questions, so the removal cannot silently take
    the whole ``budgets`` block with it.
    """
    from mcgyvr.config import field_at, parse

    config = parse(
        CARD + "budgets:\n" + "  request_timeout_s: 30.0\n" + "  task_timeout_s: 60\n"
    )

    assert field_at("budgets.wake_timeout_s") is None, (
        "budgets.wake_timeout_s is still a schema key: the wake limit now comes "
        "from the lock's validated wake plus its tolerance, not a hand-set budget"
    )
    assert config.get("budgets.request_timeout_s") == 30.0
    assert config.get("budgets.task_timeout_s") == 60


def test_the_wake_limit_is_the_validated_wake_plus_its_tolerance() -> None:
    """The Waker waits for a unit's validated wake plus the lock's tolerance.

    The values are the measurement branch's; the rule is the lock's.
    """
    from mcgyvr.fleet.lock import wake_limit_s

    assert wake_limit_s(20.0, {"s": 0.5}) == pytest.approx(20.5)
    assert wake_limit_s(0.25, {"s": 0.1}) == pytest.approx(0.35)


def test_the_doors_health_budget_is_not_a_wake_budget() -> None:
    """The door still polls a unit into health; that no longer bounds a wake.

    ``HEALTH_POLLS`` and ``HEALTH_INTERVAL_S`` describe what ``serve up`` does,
    not how long a dispatch may wait for a server to exist. Keeping the door's
    own budget while dropping ``budgets.wake_timeout_s`` is the point: the wake
    limit is the lock's.
    """
    from mcgyvr.config import field_at
    from mcgyvr.serving.servelib import HEALTH_INTERVAL_S, HEALTH_POLLS

    assert HEALTH_POLLS * HEALTH_INTERVAL_S > 0, (
        "the door's own health budget disappeared along with the wake budget"
    )
    assert field_at("budgets.wake_timeout_s") is None, (
        "the wake limit comes from the lock, not from the door's health budget"
    )
