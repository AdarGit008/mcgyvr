"""The two keys sleep/wake is asked for by, and the budget a wake is bounded by.

RED. Nothing in this file passes today, and none of it may be made to pass by
editing a test: ``records/plans/sleep-wake.md`` is the approved design and
``src/mcgyvr/config.py`` has no ``serving`` block and no ``budgets.wake_timeout_s``
at all, so every config here is refused as an unknown key.

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
* **A wake is bounded by a budget of its own** (§8.3). ``request_timeout_s``
  bounds one reply and is priced from tokens per second; ``task_timeout_s``
  bounds a wait for a free slot on a server that is already running.
  ``wake_timeout_s`` bounds a wait for a server *to exist*. One knob for three
  faults would mean setting reply length and boot time with the same number.

The *value* 480.0 was N7 in the design's §16 — the one row a measurement
settled rather than a ruling — and the measurement was taken on 2026-09-08
(``records/measurements/wake-2026-09-08/``). Five cold starts across both rigs:
82 s for a single vLLM unit alone on an empty card, 50-128 s for llama.cpp on
srv1, and **203 s** for srv1's ceiling model, which is the worst this fleet can
produce. So the value is pinned here now, against the two things it has to
clear: the door's own health budget, and the slowest wake anyone has measured.
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


def _door_health_budget() -> float:
    """The seconds ``serve up`` will itself spend polling a unit into health.

    Read from the door rather than written down here, because the whole point
    of the refusal below is that the two numbers must not be able to drift
    apart: a caller budget under this one abandons a wake the door is still
    working on.
    """
    from mcgyvr.serving.servelib import HEALTH_INTERVAL_S, HEALTH_POLLS

    return HEALTH_POLLS * HEALTH_INTERVAL_S


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


def test_a_wake_budget_is_neither_the_request_nor_the_task_one() -> None:
    """Three faults, three numbers, and none of them derived from another.

    Stated together so that a single knob cannot satisfy this test: the three
    are set to three different values and each must read back as the one it was
    given. Sharing ``request_timeout_s`` with the wake would mean raising the
    reply budget to survive a 130-second boot, after which every hung request
    hangs for 130 seconds too; sharing ``task_timeout_s`` would make a deep
    queue and a cold rig the same fault.
    """
    from mcgyvr.config import parse

    config = parse(
        CARD
        + "budgets:\n"
        + "  request_timeout_s: 30.0\n"
        + "  task_timeout_s: 60\n"
        + "  wake_timeout_s: 500.0\n"
    )

    assert config.get("budgets.request_timeout_s") == 30.0
    assert config.get("budgets.task_timeout_s") == 60
    assert config.get("budgets.wake_timeout_s") == 500.0


def test_a_wake_budget_is_defaulted_and_is_not_a_re_spelling_of_the_other_two() -> None:
    """A config that states none of the three still has all three, distinctly.

    What is asserted here is that it is a number, that it is the door's own
    budget or more (the ruled relation, below), and that it did not arrive by
    being handed one of its neighbours' defaults. The value itself is pinned
    separately, against the measurement that settled N7.
    """
    from mcgyvr.config import parse

    config = parse(CARD)
    wake = config.get("budgets.wake_timeout_s")

    assert isinstance(wake, float), (
        f"budgets.wake_timeout_s read as {wake!r}: a wake has no budget of its "
        "own, so a caller waiting for a server to exist is bounded by nothing "
        "or by a budget priced for something else"
    )
    assert wake >= _door_health_budget()
    assert wake != config.get("budgets.request_timeout_s")
    assert wake != float(config.get("budgets.task_timeout_s"))


def test_a_wake_budget_under_the_doors_own_health_budget_is_refused_by_name() -> None:
    """The one relation between the two numbers the design ruled on (§8.3).

    ``serve up`` polls each unit into health for ``HEALTH_POLLS``
    times ``HEALTH_INTERVAL_S`` seconds. A caller budget below that abandons a wake
    while the door is still working and leaves a card half-up — which D2 says
    is the one state the reading cannot name and must not act on. So the
    disagreement is named at the one moment both numbers are in hand, in the
    shape of ``Capacity.of``'s width refusal, rather than quietly corrected.

    The assertion is not merely that the config is refused: an unknown key is
    refused today, and a test satisfied by that would go green on the wrong
    behaviour and stay green. The refusal has to be *about the door's budget*.
    """
    from mcgyvr.config import ConfigSchemaError, parse

    too_low = _door_health_budget() - 1.0

    with pytest.raises(ConfigSchemaError) as caught:
        parse(CARD + f"budgets:\n  wake_timeout_s: {too_low}\n")

    message = str(caught.value)
    assert "unknown key" not in message, (
        "the config was refused for not having the key rather than for the "
        "value it gave it: the schema has no wake budget to compare against "
        f"the door's own {_door_health_budget():g}s. Refusal: {message}"
    )
    assert f"{_door_health_budget():g}" in message, message


def test_a_wake_budget_at_or_above_the_doors_health_budget_is_accepted() -> None:
    """The other side of the refusal, so it cannot be satisfied by refusing all."""
    from mcgyvr.config import parse

    config = parse(CARD + f"budgets:\n  wake_timeout_s: {_door_health_budget()}\n")

    assert config.get("budgets.wake_timeout_s") == _door_health_budget()


#: The slowest wake anyone has measured on this fleet: srv1's ceiling model,
#: KAT-Coder 35.5B/A3B, 16.9 GiB of blob against 15 GiB of RAM, cold to first
#: 200 on /v1/models (2026-09-08). Every other rig and model measured that day
#: came in faster, the 35.7 GiB 80B on srv2 included, because a wake is paid in
#: memory pressure and not in bytes.
WORST_MEASURED_WAKE_S = 203.0


def test_the_default_wake_budget_clears_the_slowest_wake_ever_measured() -> None:
    """N7, settled by measurement rather than by ruling.

    480 was priced from the door's 360 s health budget before anyone had timed
    the thing it bounds. The timing exists now and the number survives it: the
    fleet's worst wake is 203 s, which 480 clears twice over. A budget that
    merely exceeded the worst case would be a budget that fails the first time a
    rig is a little slower than the day it was measured, so the margin is what
    is asserted, not the bare inequality.

    If a future ladder holds a model this fails for, the fix is a re-measurement
    and a new default — not a wider assertion.
    """
    from mcgyvr.config import parse

    wake = parse(CARD).get("budgets.wake_timeout_s")

    assert wake >= 2 * WORST_MEASURED_WAKE_S, (
        f"the default wake budget is {wake!r}s against a measured worst wake of "
        f"{WORST_MEASURED_WAKE_S:g}s. A caller that gives up near the measured "
        "ceiling abandons wakes that were about to land, and leaves the card up"
    )
