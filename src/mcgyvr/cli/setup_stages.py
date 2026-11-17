"""The `mcgyvr setup` wizard's run states and decision tree.

The wizard walks an ordered decision tree: each decision point is a named
node with the answers it takes and the default an empty answer picks. The
run's states are the ordered stages it passes through, and the menu's
``stop`` axis names the stage a manual run halts after (:class:`Stop`).

This module holds only the tree and the table; the prompts that ask the
questions live in :mod:`mcgyvr.cli.commands.setup`, so the data stays
readable and the questions stay beside the helpers that ask them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from mcgyvr.config import USE_CASES
from mcgyvr.serving.vramfit import LLAMACPP_CACHE_TYPES


class Stop(StrEnum):
    """Where a manual run may stop, by the word the menu passes.

    ``config`` writes the config and stops; ``emit`` also writes the launch
    specs; ``start`` also brings the servers up, sampling and locking nothing.
    """

    CONFIG = "config"
    EMIT = "emit"
    START = "start"


class State(StrEnum):
    """The ordered states a wizard run passes through, named for its nodes."""

    RIGS = "rigs"
    USE_CASE = "use-case"
    CODING = "coding"
    CHAT = "chat"
    AGENT = "agent"
    RECOMMEND = "recommend"
    DOWNLOAD = "download"
    STAGE = "stage"
    EMIT = "emit"
    START = "start"
    SAMPLE = "sample"
    LOCK = "lock"
    ALL_MANUAL = "all-manual"
    DONE = "done"


class Stage(NamedTuple):
    """One stage of the run: its state, how it reads, and the stop that halts
    after it (None when the wizard never stops there)."""

    state: State
    title: str
    stop: Stop | None


#: The ordered stage table: the stages the wizard walks, in order, each with
#: the ``stop`` value that halts a manual run after it.
STAGES: tuple[Stage, ...] = (
    Stage(State.RIGS, "where it runs", None),
    Stage(State.USE_CASE, "what it serves", None),
    Stage(State.RECOMMEND, "read and plan", None),
    Stage(State.DOWNLOAD, "fetch missed weights", None),
    Stage(State.STAGE, "stage the config", Stop.CONFIG),
    Stage(State.EMIT, "emit launch specs", Stop.EMIT),
    Stage(State.START, "start the servers", Stop.START),
    Stage(State.SAMPLE, "sample the fleet", None),
    Stage(State.LOCK, "lock the fleet live", None),
)


#: The KV cache quants the wizard offers, recommended (``f16``) first, read
#: from llama.cpp's accepted ``-ctk``/``-ctv`` types.
CONTEXT_QUANT_CHOICES: tuple[str, ...] = (
    "f16",
    *(quant for quant in LLAMACPP_CACHE_TYPES if quant != "f16"),
)


class Decision(NamedTuple):
    """One decision point of the tree: its name, the answers it takes, and
    the default an empty answer picks (None: no default, so it re-asks)."""

    name: str
    options: tuple[str, ...]
    default: str | None


#: The ordered decision tree, as the prompts in :mod:`mcgyvr.cli.commands.setup`
#: ask it (``tests/test_setup_decision_tree_holds_what_its_prompts_offer.py``
#: holds the two equal). A yes/no question takes ``yes`` or ``no``, and Enter
#: is ``no``. A node with one option takes a free answer (a count); its option
#: names the kind of answer. ``coding`` is the gated
#: ``mcgyvr-code`` use case; the raw coding use case ``code`` is served by the
#: same raw branch as ``chat`` (the KV cache quant), and
#: ``agent`` adds slots to it.
DECISION_TREE: tuple[Decision, ...] = (
    Decision("rigs", ("local", "remote", "both"), "local"),
    Decision("use-case", USE_CASES, None),
    Decision("coding.deployment", ("hybrid", "local-only"), "hybrid"),
    Decision("coding.jev", ("yes", "no"), "no"),
    Decision("coding.fanout", ("idle", "none", "full"), "idle"),
    Decision("coding.sleep-wake", ("yes", "no"), "no"),
    Decision("coding.ruff", ("yes", "no"), "no"),
    Decision("chat.context-quant", CONTEXT_QUANT_CHOICES, "f16"),
    Decision("agent.slots", ("count",), "1"),
    Decision("recommend", ("yes", "no"), "no"),
    Decision("skip-rec", ("manual", "model-path"), "manual"),
    Decision("download", ("yes", "no"), "no"),
    Decision("start", ("yes", "no"), "no"),
    Decision("lock", ("yes", "no"), "no"),
)
