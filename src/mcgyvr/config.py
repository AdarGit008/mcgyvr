"""The setup's schema, loader and failure behaviour, and the two files it reads.

A setup is two files in one directory, written by ``mcgyvr init``: ``fleet.yaml``
holds the units (what runs where, locked) and ``policy.yaml`` holds the ladder
and how work moves over it (not locked). Both are read by
:mod:`mcgyvr.fleet.files`, which owns the vocabulary and the refusals; this
module declares the schema, fills defaults, and presents the loaded setup as
typed ``units`` and ``ladder``. The files are YAML rather than JSON because
they carry policy, and policy needs comments to stay hand-editable
("Known tension").

Three properties are load-bearing and each is enforced here rather than
documented and hoped for:

1. **No silent defaults for things that must be bound.** A default ships
   only when it is a real working value. Anything else is absent, and its
   absence surfaces at the point of use naming the key and how to bind it —
   never as a fallback that makes a misconfiguration look like a bug.
2. **Unknown keys fail.** A typo'd key that is ignored is a config that
   silently does something other than what it says.
3. **Credentials are never values.** The config records only the NAME of
   the environment variable holding each key; the orchestrator process
   resolves it, and a task sandbox never sees it (see ``archive/SECURITY.md``).

``SCHEMA`` below is declarative data, not a set of hand-written checks: it
is what the validator walks and what the config reference is generated
from, so a documented key and a validated key cannot drift apart.

This module only declares and loads. Detecting hardware, proposing
bindings, and writing the file are separate concerns and do not live here.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.strict_yaml import strict_loader

#: A setup is two files in one directory. ``fleet.yaml`` is locked and holds
#: the units, rigs and fleets — what runs where. ``policy.yaml`` is not locked
#: and holds the ladder and the routing policy over it.
FLEET_FILENAME = "fleet.yaml"
POLICY_FILENAME = "policy.yaml"
CONFIG_PATH_ENV = "MCGYVR_CONFIG"
#: What a config's identity starts with (:meth:`Config.digest`), so it can
#: never be read as a product digest or a blob name: those are bare hex.
DIGEST_PREFIX = "cfg-"
#: Where the journal keeps the config each run was made under, by its digest
#: (:func:`keep`): ``<journal.dir>/configs/<digest>.yaml``. Naming that file
#: in ``MCGYVR_CONFIG`` re-selects the setup a result names, in one command.
CONFIGS_DIR = "configs"
#: The user-level config directory (owner, 2026-09-05). A literal with `~` so
#: help text reads the same on every machine; expanded at the point of use.
#: This is the third and last place a config is looked for, after the
#: environment override and the working directory, and where `mcgyvr init`
#: writes when nobody names a path. `$XDG_CONFIG_HOME` is not consulted.
USER_CONFIG_DIR = "~/.mcgyvr/config"


class ConfigError(Exception):
    """Base class for every configuration failure."""


class ConfigFileError(ConfigError):
    """The config file is missing, unreadable, or not parseable as YAML."""


class ConfigMissingError(ConfigFileError):
    """There is no config file at all.

    A class rather than a message to grep, because "there is none" and "the
    one that is there cannot be read" ask for different answers from a caller
    that can run without a config. The deterministic floor is one: it
    dispatches nothing, needs no ladder, and an install with no config is a
    supported install — so a missing file is silence, while a file the
    operator wrote and this run could not use is something to say out loud.

    Silence is the *default location's* to earn, not this class's. Whether the
    path was one the caller named is what :func:`named_config_path` answers,
    and a caller that treats this exception as "nothing to mention" has to ask:
    nobody chose the empty default, whereas ``--config`` or ``$MCGYVR_CONFIG``
    pointing at nothing is a path somebody typed, and a run that goes quietly
    on under some other directory is the operator's problem to discover later.
    """


class ConfigSchemaError(ConfigError):
    """The config parsed, but does not satisfy the schema."""


class CredentialInConfigError(ConfigSchemaError):
    """A credential was written into the config as a literal value.

    Distinct from a plain schema error because the remedy is not "fix the
    key" — the secret is now in a file that gets committed, and it has to be
    rotated.
    """


class UnboundValueError(ConfigError):
    """A value the running code needs is not bound.

    Raised at the point of use, never at load: a config that omits an API
    provider is valid, and only becomes a problem if something tries to use
    one.
    """


Kind = Literal[
    "int",
    "float",
    "str",
    "url",
    "bool",
    "enum",
    "env_name",
    "str_list",
    "mapping",
    "int_map",
    "block",
    "block_map",
    "block_list",
]


@dataclass(frozen=True)
class Field:
    """One key in the schema, with everything needed to validate and document it.

    ``doc`` has no default on purpose: a key that cannot be explained does
    not belong in a file a stranger is asked to edit.
    """

    name: str
    kind: Kind
    doc: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    block: tuple[Field, ...] = ()
    min_value: float | None = None
    #: Inclusive upper bound, for the values that have one because they are a
    #: share of something rather than a count of it. Absent on every counting
    #: field: attempts and timeouts have no natural ceiling, and inventing one
    #: would refuse a config nobody has shown to be wrong.
    max_value: float | None = None
    bind_hint: str = ""

    retired: tuple[tuple[str, str], ...] = ()
    """Enum values this build recognises and refuses, each with why and what to
    set instead.

    Distinct from simply dropping the value out of ``choices``, which is what
    was tried first. That produces "not a valid value. Valid: ...", which is
    true and unhelpful: a value that used to work — and, in the one case here,
    used to be the *default* — was doing something other than what its name
    said, and an operator who wrote it deserves to be told which behaviour they
    were actually getting. A retired value is still recognised, so the message
    can be specific; it is refused, so the config cannot resolve to it."""


SANDBOX_FIELDS: tuple[Field, ...] = (
    Field(
        "mode",
        "enum",
        "`docker` runs each task in its own container, torn down after. "
        "`tempdir` is the explicitly weaker fallback for installs without "
        "Docker: acceptance commands are arbitrary shell from a contract, "
        "running on someone else's machine.",
        default="docker",
        choices=("docker", "tempdir"),
    ),
    Field(
        "image",
        "str",
        "Base image for task containers. Unset means detect the repository's "
        "stack and build one.",
        bind_hint="name an image tag, or leave unset to let the stack be detected",
    ),
    Field(
        "setup",
        "str_list",
        "Commands run once when the task image is built, before any task.",
        default=(),
    ),
)

DELIVERY_FIELDS: tuple[Field, ...] = (
    Field(
        "mode",
        "enum",
        "Where an accepted change is committed. `branch` puts it on a new "
        "local branch named after the contract and leaves the branch you have "
        "checked out, your index and your working tree exactly as they were — "
        "the delivery tells you the `git push` to run. `none` commits onto the "
        "branch you have checked out. Nothing here pushes or opens a pull "
        "request: mcgyvr reaches your repository through `git` and has no "
        "forge, so the last step off this machine is yours.",
        default="branch",
        choices=("branch", "none"),
        retired=(
            (
                "pull_request",
                "is no longer a mode. It never opened one — every mode "
                "committed straight to your checked-out branch, and the pull "
                "request was recorded as owed to something that does not "
                "exist. Opening one needs a forge and a credential this build "
                "has nowhere to put. Set `branch` for a commit on a branch of "
                "its own plus the push to run, or `none` to commit onto the "
                "branch you have checked out.",
            ),
        ),
    ),
)

#: Where the live journal goes when `journal.dir` is left out. A literal with
#: `~` rather than an expanded path so the reference reads the same on every
#: machine; expanded at the point of use. The XDG state dir is the convention
#: `mcgyvr scan` already keeps its records under.
JOURNAL_DIR_DEFAULT = "~/.local/state/mcgyvr/journal"

JOURNAL_FIELDS: tuple[Field, ...] = (
    Field(
        "dir",
        "str",
        "Where every run journals what it asked, what came back and how it "
        "landed: one `<orchestrator>.jsonl` per writer, the prompts and replies "
        "content-addressed under `blobs/`, and each run's result file under "
        "`results/`. Deterministic runs are here too, with a row naming the "
        "program instead of a model. This is mcgyvr's own record, it never "
        "lands in the repository a run works on, and nothing on the command "
        "line moves it: it is the one place every run is, which is what makes "
        "it worth asking questions of. `mcgyvr run --record DIR` adds a second "
        "copy for your own use. Read either back with `tools/live/review.py "
        "DIR`. The config each run was made under is kept here too, as "
        "`configs/<digest>.yaml`, and every row and result names that "
        "digest: `MCGYVR_CONFIG=<dir>/configs/<digest>.yaml` re-selects the "
        "exact setup a result was produced under.",
        default=JOURNAL_DIR_DEFAULT,
    ),
)

# How long one dispatched request may take before the transport gives up.
# Defined here rather than in :mod:`mcgyvr.runner` because it is now a config
# default as well as the runner's constant, and the two must be one number:
# a literal in each is how the door and `emit` came apart over `-c` (see
# `kv_bytes_for_run`). Measured against on 2026-09-06: the top local rung
# gives 27.2 tok/s to one stream and 5.09 tok/s to each of eight, so what this
# number forbids is a function of the width a rung serves and the cap a
# contract declares, which is why it has to be declarable beside them.
DEFAULT_REQUEST_TIMEOUT_S = 120.0

# How long `serve up` polls a unit into health after bringing it up: a vLLM
# server measured 87 s to health on srv2 and llama.cpp 54-129 s on srv1
# (2026-09-05), so six minutes is three of the slowest with room. The door
# (`mcgyvr.serving.servelib`) polls by these, so they read them from here:
# `config` is the one module both halves of the seam may import, and the door
# is not.
HEALTH_POLLS = 120
HEALTH_INTERVAL_S = 3.0


BUDGET_FIELDS: tuple[Field, ...] = (
    Field(
        "max_escalations",
        "int",
        "How many rungs a task may climb before it is handed back unfinished. "
        "A cheap rung that fails and escalates costs more than starting "
        "higher, so this is a real ceiling, not a retry count.",
        default=1,
        min_value=0,
    ),
    Field(
        "max_attempts",
        "int",
        "Hard ceiling on how many attempts one task may spend in total, "
        "across every rung and every family it climbs. Unset means the "
        "ladder's own budget bounds it — the sum of each reachable rung's "
        "`attempts`, which `mcgyvr pool` prints — so leaving it unset is not "
        "unbounded. Set it when you have raised a rung's `attempts` or "
        "`max_escalations` and want one number that still holds. A decline "
        "costs nothing against it: a rung that stepped aside spent no attempt.",
        min_value=1,
        bind_hint=(
            "set a whole number of attempts, or leave it unset to be bounded "
            "by the ladder's own budget (`mcgyvr pool` prints that number)"
        ),
    ),
    Field(
        "request_timeout_s",
        "float",
        "How long one dispatched request may take before the transport gives "
        "up, in seconds. A reply of `limits.max_output_tokens` tokens takes "
        "the time its rung's per-stream rate says it takes, and that rate "
        "falls as the rung serves more streams at once, so this bound, the "
        "cap and the rung's width are three numbers that decide each other. "
        "Left as a constant in the runner it decided the other two silently: "
        "a cap an operator was free to declare was unreachable at a width "
        "they were also free to declare, and the failure arrived as a socket "
        "timeout naming neither. Raise it for a slow rung serving a large "
        "cap; lower it to fail faster.",
        default=DEFAULT_REQUEST_TIMEOUT_S,
        min_value=0.0,
    ),
    Field(
        "task_timeout_s",
        "int",
        "Wall-clock ceiling for one task, including acceptance commands.",
        default=900,
        min_value=1,
    ),
    Field(
        "max_window_fraction",
        "float",
        "The largest share of a rung's context window one contract may claim "
        "-- its prompt and its own declared reply together, over the whole "
        "window. Distinct from whether the two *fit*, which the fit check "
        "already asks: a contract that fits with nothing to spare leaves the "
        "rung nothing to absorb a long estimate with. Unset enforces no "
        "share, which is not the same as 1.0: a run that declared none is "
        "recorded as having declared none.",
        min_value=0.0,
        max_value=1.0,
        bind_hint=(
            "a share between 0 and 1 -- e.g. 0.75 to keep a quarter of every "
            "rung's window clear -- or leave it unset to enforce no share"
        ),
    ),
)

BREADTH_FIELDS: tuple[Field, ...] = (
    Field(
        "draws",
        "int",
        "How many candidates one attempt asks its rung for before the gate "
        "picks between them. Draws are not attempts: they share one prompt and "
        "one attempt's budget, and the gate ranks the answers rather than the "
        "next attempt being told what the last one got wrong. The default of 1 "
        "is  unchanged — one draw, one verdict, and the draw is the "
        "answer. Raising it is most defensible on a cheap rung that is often "
        "almost right, where three draws are still cheaper than escalating; a "
        "lever whose whole benefit is fewer crossings into the api family "
        "cannot be evaluated before the telemetry that counts crossings, which "
        "is why this is something to ask for rather than something you are "
        "given.",
        default=1,
        min_value=1,
    ),
)

CLEANUP_FIELDS: tuple[Field, ...] = (
    Field(
        "enabled",
        "bool",
        "Repair a change the gate rejected with the deterministic tools — the "
        "declared imports, the linter's own autofixes, the formatter — and "
        "judge it again on the same rung, instead of spending an attempt or a "
        "climb on what a tool clears for nothing. The tools are the ones the "
        "gate already checks with, so a repair produces the shape the rungs "
        "ask for rather than a second opinion about it, and it costs no tokens "
        "by construction. On by default (owner, 2026-09-05): the first live "
        "ladder rejected all nine replies on a reflowed line, whitespace on a "
        "blank line or an unsorted import block and paid a climb for each, "
        "and running the fixers after a rung is done is the point — it lifts "
        "every task the deterministic floor could not take outright. It "
        "rewrites a file after the gate has spoken about it, so the bytes "
        "that come back are not the bytes the worker sent: the journal keeps "
        "the reply, the tree keeps the repaired file, and the verdict says a "
        "repair ran. Set false to have the rejection stand as the gate "
        "reached it. What no tool fixes — a failed acceptance command, a "
        "name, a line too long to wrap — is rejected exactly as before.",
        default=True,
    ),
)

SERVING_FIELDS: tuple[Field, ...] = (
    Field(
        "enable_sleep_wake",
        "bool",
        "Whether mcgyvr may take a card down and bring it back on its own. Off "
        "by default, because the feature is a trade and not an improvement: "
        "turning it on lets `mcgyvr run` stop containers on a rig other people "
        "share. It is a key here and not a `--flag` for the reason `mcgyvr run "
        "--config` already gives about which rung runs — `Config.digest` is "
        "what a run is reproducible from, and a flag would let two runs share "
        "one digest where only one of them started and stopped containers on a "
        "shared rig, putting the rig side effect outside the only record that "
        "explains the run. It governs the *decisions*: `mcgyvr serve "
        "sleep|wake`, typed by a person who has therefore asked, is not gated "
        "by it. It sits here rather than under `ladder` because "
        "`ladder.fanout` decides where work goes among rungs that exist and "
        "this decides whether rungs come into existence — two authorities, and "
        "only one of them touches a rig.",
        default=False,
    ),
    Field(
        "compose_dir",
        "str",
        "Where this checkout keeps the launch specs `mcgyvr emit` wrote. The "
        "one thing that has to be stated rather than derived, because `mcgyvr "
        "emit --out` defaults to the current directory and a wake has to find "
        "the file again. It is deliberately not a device and not a host: a "
        "`device: cuda:0` beside a `base_url` would be two statements of one "
        "fact and would go stale the first time a source was re-pointed, "
        "whereas this cannot go stale against anything — it says where files "
        "are, not where work runs. A config that omits it has no sleeping "
        "cards at all, only down ones: `asleep` is `down` plus a launch spec "
        "mcgyvr holds for that card, and with no directory there is no spec.",
        bind_hint=(
            "the directory `mcgyvr emit --out` writes to -- e.g. "
            "~/.mcgyvr/config -- or leave it unset and this ladder has no "
            "sleeping cards, only down ones"
        ),
    ),
)

UNIT_FIELDS: tuple[Field, ...] = (
    Field(
        "address",
        "url",
        "Where this unit answers, including scheme and port. One address is \
"
        "one process: a unit is the one term for what used to be a source.",
        required=True,
        bind_hint="e.g. http://srv2:8002",
    ),
    Field(
        "model",
        "str",
        "Model identifier as the unit names it.",
        required=True,
    ),
    Field(
        "engine",
        "enum",
        "Which server program runs behind this address. Absent means \
"
        "llama.cpp.",
        choices=("llama.cpp", "vllm"),
        bind_hint="e.g. vllm -- leave it out for llama.cpp",
    ),
    Field(
        "image",
        "str",
        "Container image this unit runs, as a tag or digest.",
        bind_hint="e.g. vllm/vllm-openai@sha256:<hex>",
    ),
    Field(
        "api_key_env",
        "env_name",
        "NAME of the environment variable holding this unit's key.",
        bind_hint=(
            "set it to the variable's NAME (e.g. ANTHROPIC_API_KEY), never "
            "the key itself"
        ),
    ),
    Field(
        "rig",
        "str",
        "The rig this unit runs on, by the name fleet.yaml uses. Units that \
"
        "share a rig and an address are served by one process.",
        bind_hint="e.g. srv2",
    ),
    Field(
        "width",
        "int",
        "How many requests this unit may run at once. Concurrency is a \
"
        "property of the process, so it is a unit fact.",
        min_value=1,
        bind_hint="e.g. 8 -- the slot count the backend was started with",
    ),
    Field(
        "window",
        "int",
        "Tokens this unit serves in one request. Read it back off the \
"
        "running process, not hoped for.",
        min_value=1,
        bind_hint="e.g. 4096 -- what the unit reports, not what you hoped for",
    ),
    Field(
        "output_tokens",
        "int",
        "Room a reply on this unit is given, the `max_tokens` its backend is \
"
        "actually sent.",
        min_value=1,
        bind_hint="e.g. 2048 -- the reply length this unit needs",
    ),
    Field(
        "request_timeout_s",
        "float",
        "How long one dispatched request to this unit may take before the \
"
        "transport gives up.",
        min_value=0.0,
        bind_hint="e.g. 180",
    ),
    Field(
        "room_mib",
        "int",
        "The card room this unit needs, in MiB, measured or stated. Replaces \
"
        "the model block's vram/ram/disk sizes.",
        min_value=0,
        bind_hint="e.g. 7000 -- the card room this unit needs",
    ),
    Field(
        "kv_cache_memory_bytes",
        "int",
        "The vLLM KV cache this unit pins, in bytes. Absent where the engine \
"
        "sizes its own cache; required before a vLLM unit is locked.",
        min_value=0,
        bind_hint="e.g. 34359738368",
    ),
    Field(
        "attention_backend",
        "str",
        "The attention backend this vLLM unit pins, because the card decides \
"
        "what is valid.",
        bind_hint="e.g. FLASH_ATTN, or TRITON_ATTN on cc 7.5",
    ),
    Field(
        "container",
        "str",
        "The container name this unit runs under.",
        bind_hint="e.g. mcgyvr-srv2-srv2_7b",
    ),
    Field(
        "hf_cache",
        "str",
        "The HuggingFace cache on the rig holding this unit's weights, as an \
"
        "absolute path there. A serving fact about this unit, not a knob.",
        bind_hint="e.g. /home/<user>/.cache/huggingface, as the rig sees it",
    ),
    Field(
        "launch",
        "mapping",
        "The resolved launch, whole. Free-form by design: a unit hashes its \
"
        "whole resolved launch with no hand-kept field list (ID-2), so a flag \
"
        "this reader has never heard of cannot go unhashed.",
        bind_hint="the resolved launch, e.g. serve_args, geometry_json, moe",
    ),
)

ROLE_UNIT_FIELDS: tuple[Field, ...] = (
    Field(
        "unit",
        "str",
        "Which unit serves this role. A unit is the one term.",
        bind_hint="name one of the units declared under `units`",
    ),
    Field(
        "model",
        "str",
        "Model identifier as that unit names it; absent means the unit's own.",
        bind_hint="name a model the bound unit serves",
    ),
)

VERIFIER_UNIT_FIELDS: tuple[Field, ...] = (
    Field(
        "enabled",
        "bool",
        "Model verification of the applied diff, on top of the gate.",
        default=False,
    ),
    *ROLE_UNIT_FIELDS,
)

SCHEMA: tuple[Field, ...] = (
    Field(
        "profile",
        "enum",
        "Which setup this file is: `live` or `dev`. A fleet fact: live \
"
        "outranks dev on the rigs.",
        choices=("live", "dev"),
        default="live",
    ),
    Field(
        "units",
        "block_map",
        "What runs where, keyed by a name you choose. A unit carries every \
"
        "fact about what it is and can physically do: its address, engine, \
"
        "model, width, window, reply size and timeout.",
        required=True,
        block=UNIT_FIELDS,
    ),
    Field(
        "ladder",
        "str_list",
        "The ordered list of unit names work climbs, cheapest first.",
        required=True,
    ),
    Field(
        "fanout",
        "enum",
        "Whether a batch of contracts spreads across units or queues on one.",
        default="none",
        choices=("none", "idle", "full"),
    ),
    Field(
        "attempts",
        "int_map",
        "How many times each unit may be tried before escalation moves on.",
        default=None,
        min_value=1,
        bind_hint="e.g. {srv2_7b: 2}",
    ),
    Field(
        "max_escalations",
        "int",
        "How many rungs a task may climb before it is handed back unfinished.",
        default=1,
        min_value=0,
    ),
    Field(
        "max_attempts",
        "int",
        "Hard ceiling on how many attempts one task may spend in total.",
        min_value=1,
        bind_hint="set a whole number of attempts, or leave it unset",
    ),
    Field(
        "task_timeout_s",
        "int",
        "Wall-clock ceiling for one task, including acceptance commands.",
        default=900,
        min_value=1,
    ),
    Field(
        "max_window_fraction",
        "float",
        "The largest share of a unit's context window one contract may claim.",
        min_value=0.0,
        max_value=1.0,
        bind_hint="a share between 0 and 1",
    ),
    Field(
        "orchestrator",
        "block",
        "Which unit turns a prompt plus a repository into contracts.",
        block=ROLE_UNIT_FIELDS,
    ),
    Field(
        "verifier",
        "block",
        "Which unit reads an applied diff in fresh context.",
        block=VERIFIER_UNIT_FIELDS,
    ),
    Field("sandbox", "block", "Where a task's commands run.", block=SANDBOX_FIELDS),
    Field(
        "delivery",
        "block",
        "How accepted work gets back to you.",
        block=DELIVERY_FIELDS,
    ),
    Field(
        "breadth",
        "block",
        "How many answers one attempt asks for.",
        block=BREADTH_FIELDS,
    ),
    Field(
        "cleanup",
        "block",
        "What may be fixed without asking a model.",
        block=CLEANUP_FIELDS,
    ),
    Field(
        "serving",
        "block",
        "What mcgyvr may do to the machines that serve the units. A unit's "
        "HuggingFace cache is a fact about that unit and lives on it, not "
        "here: only the policy of starting and stopping a card is a setting.",
        block=SERVING_FIELDS,
    ),
    Field(
        "journal",
        "block",
        "Where mcgyvr keeps its own record of what it dispatched.",
        block=JOURNAL_FIELDS,
    ),
)


# Keys that would hold a credential as a value. They are unknown keys and
# would be rejected anyway, but the generic "unknown key" message is the
# wrong advice: what matters is that a secret must not be written here at
# all.
_CREDENTIAL_KEYS = frozenset(
    {
        "access_key",
        "api_key",
        "apikey",
        "auth",
        "auth_token",
        "credential",
        "credentials",
        "key",
        "passwd",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "token",
    }
)

# High-signal credential shapes. This is a tripwire for the obvious cases,
# not a secret scanner — the schema is what actually keeps keys out, by
# giving them nowhere to go.
_CREDENTIAL_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^sk-[A-Za-z0-9_\-]{16,}$"),
    re.compile(r"^(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}$"),
    re.compile(r"^github_pat_[A-Za-z0-9_]{20,}$"),
    re.compile(r"^AKIA[0-9A-Z]{16}$"),
    re.compile(r"^xox[baprs]-[A-Za-z0-9\-]{10,}$"),
    re.compile(r"^AIza[0-9A-Za-z_\-]{30,}$"),
)

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Unit:
    """One process at one address, and every fact about what it is.

    A unit is the one term. It carries its own endpoint (``address``), the
    model it serves, the width it was started with, the window it serves, the
    reply room it needs, its timeout, its card room, and its whole resolved
    ``launch`` as a free-form mapping (ID-2). Nothing here is a hand-kept list
    of launch flags: ``launch`` is whatever the operator wrote, and the engine
    gate is what validates it.
    """

    name: str
    address: str
    model: str
    engine: str | None = None
    image: str | None = None
    api_key_env: str | None = None
    rig: str | None = None
    width: int | None = None
    window: int | None = None
    output_tokens: int | None = None
    request_timeout_s: float | None = None
    room_mib: int | None = None
    kv_cache_memory_bytes: int | None = None
    attention_backend: str | None = None
    container: str | None = None
    hf_cache: str | None = None
    launch: Mapping[str, Any] = field(default_factory=dict)

    @property
    def requires_credential(self) -> bool:
        return self.api_key_env is not None


@dataclass(frozen=True)
class Ladder:
    """The ordered unit names work climbs, and how a batch spreads."""

    names: tuple[str, ...]
    fanout: str = "none"

    def get(self, name: str) -> str | None:
        return name if name in self.names else None


@dataclass(frozen=True)
class Config:
    """A loaded, validated setup: what runs where, and the policy over it.

    ``data`` is the validated tree with defaults filled in and path-valued
    keys resolved against the config's own location (:func:`_resolved_paths`);
    ``units`` and ``ladder`` are typed views over what runs where and in what
    order. Values that are legitimately optional are reached through
    ``require`` and ``secret``, which fail at the point of use rather than at
    load.

    ``declared`` is the identity tree: ``data`` pruned to the settings the
    file actually stated, with every default the loader filled in left out.
    It is what :meth:`canonical` renders.

    ``path`` is where the caller found the config directory, kept for error
    messages. It is not consulted after :func:`parse`.
    """

    path: Path | None
    data: Mapping[str, Any]
    units: Mapping[str, Unit]
    ladder: Ladder
    declared: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_local_only(self) -> bool:
        """Whether every laddered unit runs on an endpoint needing no credential."""
        return not any(
            self.units[name].requires_credential for name in self.ladder.names
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Read a dotted key, or ``default`` when it is unbound."""
        try:
            return _dig(self.data, key)
        except KeyError:
            return default

    def require(self, key: str) -> Any:
        """Read a dotted key, failing loud by name when it is not bound.

        This is the point of use. The error names the key and says how to
        bind it, because the alternative — a plausible default — turns a
        misconfiguration into a bug report about something else.
        """
        try:
            value = _dig(self.data, key)
        except KeyError as exc:
            raise UnboundValueError(self._unbound(key)) from exc
        if value is None or value == "" or value == () or value == []:
            raise UnboundValueError(self._unbound(key))
        return value

    def secret(self, key: str) -> str:
        """Resolve the credential whose variable NAME is bound at ``key``.

        Two distinct failures, kept distinct: the config does not say which
        variable holds the key, or it does and that variable is not set.
        """
        var = self.require(key)
        value = os.environ.get(str(var))
        if not value:
            raise UnboundValueError(
                f"environment variable {var} is not set — it is named by "
                f"`{key}`{self._in_file()}. Export it in your shell or put it "
                f"in a git-ignored .env; never write the value into the "
                f"config file."
            )
        return value

    def canonical(self) -> str:
        """The config as one YAML text, the same for every spelling of it.

        Keys sorted, no anchors or aliases, block style throughout, and
        rendered over :attr:`declared` — the settings the file stated, with
        every default the loader filled in left out. Two files that load to
        the same config render to the same bytes, whatever their comments,
        blank lines or key order: a defaulted key is not identity. A relative
        ``geometry_json`` has already been resolved into ``data`` and
        ``declared``, so a kept copy names the file the original did.
        """
        return yaml.dump(
            _plain(self.declared),
            Dumper=_CanonicalDumper,
            sort_keys=True,
            default_flow_style=False,
            allow_unicode=True,
            width=1_000_000,
        )

    def digest(self) -> str:
        """The config's identity: ``cfg-`` and the sha256 of :meth:`canonical`.

        Over the loaded and validated tree and never over the file's bytes,
        because an identity that moved when a comment was added would name
        the edit and not the setup (owner's ruling R2, 2026-09-06).
        """
        raw = self.canonical().encode("utf-8")
        return DIGEST_PREFIX + hashlib.sha256(raw).hexdigest()

    def _unbound(self, key: str) -> str:
        spec = field_at(key)
        parts = [f"`{key}` is not bound{self._in_file()}."]
        if spec is not None:
            parts.append(spec.doc)
            if spec.bind_hint:
                parts.append(f"To bind it: {spec.bind_hint}.")
        return " ".join(parts)

    def _in_file(self) -> str:
        return f" in {self.path}" if self.path is not None else ""


class _CanonicalDumper(yaml.SafeDumper):
    """A SafeDumper that never writes an anchor.

    Two keys sharing one default object — a tuple declared once in the
    schema — would otherwise render as ``&id001`` and ``*id001``, and the
    digest would depend on object identity inside this process.
    """

    def ignore_aliases(self, data: object) -> bool:
        return True


def _plain(value: Any) -> Any:
    """``value`` as plain dicts, lists and scalars, for a canonical dump."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _declared(data: Any, raw: Any, fields: tuple[Field, ...]) -> dict[str, Any]:
    """``data`` pruned to what the file declared, and only to what it changes.

    The identity tree :meth:`Config.canonical` renders. ``data`` is the
    validated tree with defaults filled in and paths resolved; ``raw`` is the
    same tree as parsed, before the loader ran. A key the file stated is kept
    only when it states something the omission did not already mean: a key
    spelled out at its default value is not identity, and a key the file never
    stated is not identity either, which is what keeps a schema gaining an
    optional key from re-identifying every config that predates it.

    Path-valued keys stay resolved: the scalar kept is ``data``'s, which
    :func:`_resolved_paths` has already made absolute, so a relative
    ``geometry_json`` keeps naming the file it actually resolves to.
    """
    out: dict[str, Any] = {}
    raw_map = raw if isinstance(raw, Mapping) else {}
    for spec in fields:
        name = spec.name
        if name not in data:
            continue
        value = data[name]
        if spec.kind == "block":
            block_pruned = _declared(value, raw_map.get(name), spec.block)
            if block_pruned:
                out[name] = block_pruned
        elif spec.kind == "block_map":
            # Every entry is kept even when its block prunes to empty, unlike
            # ``block`` above: a map's keys are user-chosen names with no
            # "absent" default, so an entry the file named is identity whether
            # or not its own fields all sit at their defaults.
            raw_entries = raw_map.get(name)
            raw_entries = raw_entries if isinstance(raw_entries, Mapping) else {}
            map_pruned: dict[str, Any] = {}
            for key, block in value.items():
                map_pruned[key] = _declared(block, raw_entries.get(key), spec.block)
            if map_pruned:
                out[name] = map_pruned
        elif spec.kind == "block_list":
            raw_items = raw_map.get(name)
            raw_items = raw_items if isinstance(raw_items, list) else []
            items: list[Any] = []
            for index, block in enumerate(value):
                raw_item = raw_items[index] if index < len(raw_items) else None
                items.append(_declared(block, raw_item, spec.block))
            if items:
                out[name] = items
        elif spec.kind in ("mapping", "int_map"):
            if value:
                out[name] = value
        elif spec.kind == "str_list":
            if value != list(spec.default or ()):
                out[name] = value
        else:
            if value != spec.default:
                out[name] = value
    return out


def keep(config: Config, journal_dir: Path) -> Path:
    """File ``config`` under ``journal_dir`` by its digest, and return the path.

    ``<journal_dir>/configs/<digest>.yaml``, holding :meth:`Config.canonical`:
    the one place a result's ``config_digest`` can be followed back to, and
    the file to name in ``MCGYVR_CONFIG`` to run under exactly that setup
    again. Content-addressed, so one that is already there and reads as the
    text it should hold is left alone; one that reads otherwise — a copy a
    crash left short — is replaced, because a kept copy that will not load
    is worse than none. A new one is staged under a name unique to this
    writer, opened exclusively, and moved into place whole, as the journal's
    blobs are: two runs keeping the same config at once each stage their
    own, and the last move wins with bytes identical to the first. An
    ``OSError`` propagates: a copy that cannot be written is a result that
    cannot be traced, and the caller says so.
    """
    text = config.canonical()
    where = journal_dir / CONFIGS_DIR
    path = where / f"{config.digest()}.yaml"
    try:
        if path.read_text(encoding="utf-8") == text:
            return path
    except (OSError, UnicodeDecodeError):
        pass
    where.mkdir(parents=True, exist_ok=True)
    staging = where / f".{path.name}.{os.getpid()}-{threading.get_ident()}.part"
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        try:
            data = text.encode("utf-8")
            while data:
                data = data[os.write(fd, data) :]
        finally:
            os.close(fd)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return path


def field_at(key: str) -> Field | None:
    """Find the schema field a dotted key addresses, if it names one.

    Segments that are a user-chosen map key or a list index are skipped —
    ``units.local.api_key_env`` and ``ladder.0`` both resolve.
    """
    return _field_in(SCHEMA, key.split("."))


def _field_in(fields: tuple[Field, ...], parts: list[str]) -> Field | None:
    index = 0
    while index < len(parts):
        found = next((f for f in fields if f.name == parts[index]), None)
        if found is None:
            return None
        index += 1
        if found.kind == "block":
            fields = found.block
        elif found.kind in ("block_map", "block_list"):
            index += 1  # the caller-chosen name or index
            fields = found.block
        else:
            return found if index == len(parts) else None
        if index == len(parts):
            return found
    return None


def _dig(data: Mapping[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, str):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(key) from exc
        else:
            raise KeyError(key)
    return current


def _typename(value: object) -> str:
    if value is None:
        return "nothing"
    return {
        bool: "a true/false value",
        int: "a number",
        float: "a number",
        str: "text",
        list: "a list",
        dict: "a block of keys",
    }.get(type(value), type(value).__name__)


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _reject_credential_literal(value: str, path: str) -> None:
    if any(p.match(value) for p in _CREDENTIAL_VALUE_PATTERNS):
        raise CredentialInConfigError(
            f"{path}: this looks like a credential written into the config. "
            f"Credentials are never values here — the config records only the "
            f"NAME of the environment variable holding a key. Rotate this "
            f"secret, then bind it by name."
        )


def _reject_credential_key(name: str, path: str) -> None:
    if name.lower() in _CREDENTIAL_KEYS:
        raise CredentialInConfigError(
            f"{_join(path, name)}: a credential cannot be expressed in the "
            f"config. Name the environment variable that holds it instead "
            f"(`api_key_env` on a unit), and keep "
            f"the value in your environment."
        )


def _mapping(raw: object, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigSchemaError(
            f"{path or 'config'}: expected a block of keys, found {_typename(raw)}"
        )
    for key in raw:
        if not isinstance(key, str):
            raise ConfigSchemaError(
                f"{path or 'config'}: key {key!r} is not text — keys must be names"
            )
    return dict(raw)


def _default_for(spec: Field) -> Any:
    if spec.kind == "block":
        return _block({}, spec.block, "")
    if spec.kind in ("block_map", "mapping", "int_map"):
        return {}
    if spec.kind == "block_list":
        return []
    if spec.kind == "str_list":
        return list(spec.default or ())
    return spec.default


def _missing(spec: Field, path: str) -> ConfigSchemaError:
    parts = [f"{path}: required key is not set.", spec.doc]
    if spec.bind_hint:
        parts.append(f"To bind it: {spec.bind_hint}.")
    return ConfigSchemaError(" ".join(parts))


def _value(raw: object, spec: Field, path: str) -> Any:
    if spec.kind == "int":
        # bool is an int in Python; `max_parallel: true` is not a capacity.
        if not isinstance(raw, int) or isinstance(raw, bool):
            raise ConfigSchemaError(
                f"{path}: expected a number, found {_typename(raw)}"
            )
        if spec.min_value is not None and raw < spec.min_value:
            raise ConfigSchemaError(
                f"{path}: must be at least {spec.min_value}, found {raw}"
            )
        if spec.max_value is not None and raw > spec.max_value:
            raise ConfigSchemaError(
                f"{path}: must be at most {spec.max_value}, found {raw}"
            )
        return raw

    if spec.kind == "float":
        # An int is a valid decimal, but a bool is not: `moe: true` and
        # `disk_gb: true` must not both be accepted by the same rule.
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ConfigSchemaError(
                f"{path}: expected a number, found {_typename(raw)}"
            )
        if spec.min_value is not None and raw < spec.min_value:
            raise ConfigSchemaError(
                f"{path}: must be at least {spec.min_value}, found {raw}"
            )
        if spec.max_value is not None and raw > spec.max_value:
            raise ConfigSchemaError(
                f"{path}: must be at most {spec.max_value}, found {raw}"
            )
        return float(raw)

    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise ConfigSchemaError(
                f"{path}: expected true or false, found {_typename(raw)}"
            )
        return raw

    if spec.kind in ("str", "url", "enum", "env_name"):
        if not isinstance(raw, str):
            raise ConfigSchemaError(f"{path}: expected text, found {_typename(raw)}")
        value = raw.strip()
        if not value:
            raise ConfigSchemaError(
                f"{path}: is empty. Remove the key or give it a value — an "
                f"empty value is not the same as an unset one."
            )
        _reject_credential_literal(value, path)
        if spec.kind == "enum":
            for name, why in spec.retired:
                if value == name:
                    raise ConfigSchemaError(f"{path}: `{value}` {why}")
            if value not in spec.choices:
                raise ConfigSchemaError(
                    f"{path}: {value!r} is not a valid value. Valid: "
                    f"{', '.join(spec.choices)}"
                )
        if spec.kind == "url" and not value.startswith(("http://", "https://")):
            raise ConfigSchemaError(
                f"{path}: {value!r} is not a URL — it needs a scheme, e.g. "
                f"http://{value}"
            )
        if spec.kind == "env_name" and not _ENV_NAME.match(value):
            raise ConfigSchemaError(
                f"{path}: {value!r} is not an environment variable name. This "
                f"key takes the NAME of the variable holding the value (e.g. "
                f"ANTHROPIC_API_KEY), never the value itself."
            )
        return value

    if spec.kind == "str_list":
        if not isinstance(raw, list):
            raise ConfigSchemaError(f"{path}: expected a list, found {_typename(raw)}")
        out: list[str] = []
        for i, item in enumerate(raw):
            if not isinstance(item, str) or not item.strip():
                raise ConfigSchemaError(
                    f"{path}.{i}: expected text, found {_typename(item)}"
                )
            _reject_credential_literal(item.strip(), f"{path}.{i}")
            out.append(item.strip())
        return out

    if spec.kind == "mapping":
        return dict(_mapping(raw, path))

    if spec.kind == "int_map":
        given = _mapping(raw, path)
        mapped: dict[str, int] = {}
        for name, item in given.items():
            if not isinstance(item, int) or isinstance(item, bool):
                raise ConfigSchemaError(
                    f"{_join(path, name)}: expected a number, found {_typename(item)}"
                )
            if spec.min_value is not None and item < spec.min_value:
                raise ConfigSchemaError(
                    f"{_join(path, name)}: must be at least {spec.min_value}, "
                    f"found {item}"
                )
            mapped[name] = item
        return mapped

    if spec.kind == "block":
        return _block(raw, spec.block, path)

    if spec.kind == "block_map":
        given = _mapping(raw, path)
        return {
            name: _block(item, spec.block, _join(path, name))
            for name, item in given.items()
        }

    if spec.kind == "block_list":
        if not isinstance(raw, list):
            raise ConfigSchemaError(f"{path}: expected a list, found {_typename(raw)}")
        if not raw:
            raise ConfigSchemaError(f"{path}: is empty. {spec.doc}")
        return [_block(item, spec.block, f"{path}.{i}") for i, item in enumerate(raw)]

    raise ConfigSchemaError(f"{path}: unsupported field kind {spec.kind!r}")


def _block(raw: object, fields: tuple[Field, ...], path: str) -> dict[str, Any]:
    given = _mapping(raw if raw is not None else {}, path)
    known = {f.name: f for f in fields}

    for key in given:
        _reject_credential_key(key, path)
        if key not in known:
            where = f"{path}: " if path else "config: "
            raise ConfigSchemaError(
                f"{where}unknown key {key!r}. An ignored key is a config that "
                f"does not do what it says. Valid keys here: "
                f"{', '.join(sorted(known))}"
            )

    result: dict[str, Any] = {}
    for spec in fields:
        if spec.name in given and given[spec.name] is not None:
            result[spec.name] = _value(given[spec.name], spec, _join(path, spec.name))
        elif spec.required:
            raise _missing(spec, _join(path, spec.name))
        else:
            result[spec.name] = _default_for(spec)
    return result


def _refuse_userinfo(name: str, base_url: str) -> None:
    """Refuse a ``base_url`` that carries a credential in its userinfo.

    ``https://user:key@host`` is a credential written into the config file,
    which :meth:`Config.secret` refuses in the one place it is asked for — "put
    it in a git-ignored .env; never write the value into the config file". The
    same rule, held where the value enters rather than where it is read.

    Refusing here is what makes the rule cheap everywhere else. A ``base_url``
    is interpolated into roughly a dozen operator-facing strings — every runner
    transport error, every availability verdict, ``mcgyvr sources``, the init
    summary — and a credential that cannot be in the value cannot be in any of
    them. Scrubbing each sink instead would have to be got right once per sink
    and again for every sink added later, which is the shape of defect this
    check exists to make impossible rather than to keep catching.
    """
    userinfo = urllib.parse.urlsplit(base_url).netloc.rpartition("@")[0]
    if not userinfo:
        return
    raise ConfigSchemaError(
        f"units.{name}.address: carries credentials in the URL "
        f"({userinfo.split(':')[0]}:...@). A URL is quoted in error messages, "
        f"probe verdicts and `mcgyvr sources`, so a key written here reaches "
        f"logs and terminals that a key in the environment never does. Remove "
        f"the `user:password@` part and name the variable holding it with "
        f"`api_key_env`."
    )


def _resolved_paths(data: dict[str, Any], path: Path | None) -> dict[str, Any]:
    """``data`` with every path-valued key made absolute against the config.

    One key has this shape today: ``models.<id>.geometry_json``, which may be
    written relative and means "the scan filed beside this config" — the live
    config writes it that way (``~/.mcgyvr/config/mcgyvr.yaml:54``,
    ``geometry_json: ./Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json``).

    Resolved **here**, once, and never again. Until 2026-09-08 the join was
    done twice and later: by ``Config._pinned`` for the digest and by
    :func:`mcgyvr.serving.declared_models` for the file that is opened. Two
    derivations of one meaning are two answers waiting to differ, and both
    already differed from each other under a symlink. A value in ``data`` is
    one answer that every reader gets, including a reader that never heard of
    ``self.path``.

    Two decisions are pinned in the three lines below, and each prevents a
    named failure.

    **A relative path with no config location is refused, not guessed.** The
    line means "next to me", and a config parsed from text nobody filed
    (:func:`parse` with ``path=None``) has no "me". The two old sites took
    that as permission to carry the word unresolved: the digest named
    ``./x.json`` — a different file from every directory — and
    ``declared_models`` handed the bare name to ``open``, so the run read
    whatever the process's working directory held. Measured on the live config
    on 2026-09-08: from its path ``cfg-02ab991e…``, from the same bytes with
    no path ``cfg-68b454c9…``, the second naming a file that exists from
    nowhere. Resolving against the working directory instead would keep both
    of those and add a third: a config whose meaning depends on where the
    operator was standing when they ran it. The remaining answer is to say so.
    This repo already answers a missing fact this way rather than inventing
    one — ``emit.py`` refuses to report an unscanned host, and
    ``check_contract_against_rung`` says an invented window "is the defect this
    function exists to end" — and :meth:`Config.canonical`'s promise that
    loading its text back yields the same digest (``config.py:974``) is
    unconditional, so the case it cannot keep must not be loadable.

    **The route to the config file is resolved before its directory is taken.**
    ``records/plans/config-library.md`` §6/D5 selects a ladder by symlinking
    its entry to the default config path. The scan sits beside the *entry*,
    because that is where the entry's author filed it; taking ``path.parent``
    through the link named the link's directory instead, so one file with one
    set of bytes got two identities — ``cfg-25d592ef…`` and ``cfg-97b08fad…``
    on a copy of the live config, 2026-09-08 — and one of them named a scan
    that was never written. :meth:`Config.digest` is the config's identity, and
    an identity that moved with the route taken to the file would name the
    route. The cost is real and accepted: a config reached through a link whose
    *target* directory does not hold the scan now fails loudly at the point of
    use instead of quietly reading a different file, and the remedy is one
    absolute path in that entry. ``resolve`` also settles a config named by a
    relative path (``--config ./mcgyvr.yaml``) against the directory the file
    was actually read from, rather than leaving the geometry relative for
    whatever comes later to interpret.
    """
    beside = path.resolve() if path is not None else None

    def resolve(owner: str, block: Mapping[str, Any]) -> Mapping[str, Any]:
        stated = block.get("geometry_json")
        if not stated:
            return block
        where = Path(str(stated)).expanduser()
        if not where.is_absolute():
            if beside is None:
                raise ConfigSchemaError(
                    f"{owner}.geometry_json: {str(stated)!r} is a "
                    f"relative path, and this config has no location to read "
                    f"it beside. A relative geometry is the scan filed next to "
                    f"the config file, so it can only be resolved by a config "
                    f"that was loaded from one. Load the file with "
                    f"`mcgyvr.config.load(path)`, pass `parse(text, "
                    f"path=...)`, or write the geometry's path out in full."
                )
            where = beside / where
        return {**block, "geometry_json": str(where)}

    out = dict(data)
    units = data.get("units")
    if isinstance(units, Mapping):
        resolved_units: dict[str, Any] = {}
        for name, block in units.items():
            if not isinstance(block, Mapping):
                resolved_units[name] = block
                continue
            launch = block.get("launch")
            if isinstance(launch, Mapping) and launch.get("geometry_json"):
                block = {**block, "launch": resolve(f"units.{name}.launch", launch)}
            resolved_units[name] = block
        out["units"] = resolved_units
    return out


def named_config_path() -> Path | None:
    """The config path the environment names, or ``None`` if it names none.

    Split out of :func:`config_path` because "somebody chose this path" is a
    fact about the *caller*, not about the file, and it survives the file not
    being there — which is the only moment it matters. A default location with
    nothing in it is a bare install; ``$MCGYVR_CONFIG`` pointing at nothing is
    a variable set ahead of the ``init`` that fills it, or a typo, and the two
    want different sentences. Callers that take a path from a flag already know
    the answer and do not need this.
    """
    override = os.environ.get(CONFIG_PATH_ENV)
    return Path(override).expanduser() if override else None


def user_config_path() -> Path:
    """``~/.mcgyvr/config``, expanded against the current HOME."""
    return Path(USER_CONFIG_DIR).expanduser()


def config_path() -> Path:
    """Locate the config directory: explicit override, then cwd, then HOME.

    The user dir is :data:`USER_CONFIG_DIR` and nothing else: the XDG config
    home was the third answer until 2026-09-05, and the owner asked for one
    directory of mcgyvr's own. A path that depends on an environment variable
    only some shells export is a config that is found from one terminal and
    not another.
    """
    override = named_config_path()
    if override is not None:
        return override
    local = Path.cwd()
    if (local / FLEET_FILENAME).is_file():
        return local
    return user_config_path()


#: Words the fleet vocabulary retired. One term — "unit" — replaced several
#: (``records/plans/fleet-identity.md`` §2). A config that names one is refused
#: naming what replaced it, exactly as ``mcgyvr.fleet.files`` refuses them.
def parse(
    fleet_text: str,
    policy_text: str = "",
    path: Path | None = None,
) -> Config:
    """Validate a setup from the two documents that define it.

    ``fleet_text`` is ``fleet.yaml`` — the units, rigs and fleets: what runs
    where. ``policy_text`` is ``policy.yaml`` — the ladder (an ordered list of
    unit names) and the routing policy over it. Both go through
    :mod:`mcgyvr.fleet.files`, the one reader that knows the vocabulary and
    refuses a key in the wrong file, so there is no second set of rules here.

    A caller holding one merged document (an editor, a test) may pass it as
    ``fleet_text`` alone: it is split into the two documents by key and each
    half goes through the same reader. The loader itself reads two files.
    """
    if not policy_text:
        fleet_text, policy_text = _split_setup(fleet_text)
    try:
        fleet = load_fleet(fleet_text)
        policy = load_policy(policy_text) if policy_text.strip() else {}
    except FleetFileError as exc:
        raise ConfigSchemaError(str(exc)) from exc
    return _build(fleet, policy, path)


#: The keys that belong in ``fleet.yaml``. Everything else in a merged
#: document is policy.
_FLEET_ONLY = frozenset({"profile", "units", "rigs", "fleets"})


def _split_setup(text: str) -> tuple[str, str]:
    """One merged document as ``(fleet.yaml, policy.yaml)`` texts.

    A document with no ``units`` is handed through whole: it is not a merged
    setup, and the fleet reader is the one that should refuse whatever it is.
    """
    try:
        raw = yaml.load(text, Loader=strict_loader(ConfigSchemaError))
    except yaml.YAMLError:
        return text, ""
    if not isinstance(raw, dict) or "units" not in raw:
        return text, ""
    fleet = {key: value for key, value in raw.items() if key in _FLEET_ONLY}
    policy = {key: value for key, value in raw.items() if key not in _FLEET_ONLY}
    return (
        yaml.safe_dump(fleet, sort_keys=False),
        yaml.safe_dump(policy, sort_keys=False) if policy else "",
    )


def _build(
    fleet: Mapping[str, Any],
    policy: Mapping[str, Any],
    path: Path | None,
) -> Config:
    """The :class:`Config` for a loaded ``fleet.yaml`` and ``policy.yaml``.

    ``rigs`` and ``fleets`` are the lock's, not the run's, and are dropped
    here rather than carried in the run's tree. Everything else is validated
    once, with the schema filling defaults, and then read into ``units`` and
    ``ladder``.
    """
    merged: dict[str, Any] = {
        key: value
        for key, value in {**fleet, **policy}.items()
        if key not in ("rigs", "fleets")
    }
    data = _block(merged, SCHEMA, "")
    _cross_validate_fleet(data)
    data = _resolved_paths(data, path)
    declared = _declared(data, merged, SCHEMA)

    units = {
        name: Unit(
            name=name,
            address=block["address"],
            model=block["model"],
            engine=block["engine"],
            image=block["image"],
            api_key_env=block["api_key_env"],
            rig=block["rig"],
            width=block["width"],
            window=block["window"],
            output_tokens=block["output_tokens"],
            request_timeout_s=block["request_timeout_s"],
            room_mib=block["room_mib"],
            kv_cache_memory_bytes=block["kv_cache_memory_bytes"],
            attention_backend=block["attention_backend"],
            container=block["container"],
            hf_cache=block["hf_cache"],
            launch=block["launch"],
        )
        for name, block in data["units"].items()
    }
    ladder = Ladder(names=tuple(data["ladder"]), fanout=data["fanout"])
    return Config(path=path, data=data, units=units, ladder=ladder, declared=declared)


def _cross_validate_fleet(data: Mapping[str, Any]) -> None:
    """Reject a fleet document that satisfies the schema but contradicts itself."""
    units: Mapping[str, Any] = data["units"]
    if not units:
        raise ConfigSchemaError(
            "units: no unit is declared. mcgyvr needs at least one unit to "
            "dispatch work to."
        )

    for name, block in units.items():
        _refuse_userinfo(name, str(block["address"]))

    seen: set[str] = set()
    if not data["ladder"]:
        raise ConfigSchemaError(
            "ladder: is empty. A fleet needs at least one unit on its ladder."
        )
    for index, name in enumerate(data["ladder"]):
        if name in seen:
            raise ConfigSchemaError(
                f"ladder.{index}: {name!r} is listed more than once. A unit is "
                f"one step of the ladder."
            )
        seen.add(name)
        if name not in units:
            raise ConfigSchemaError(
                f"ladder.{index}: {name!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )

    attempts = data.get("attempts") or {}
    for name in attempts:
        if name not in units:
            raise ConfigSchemaError(
                f"attempts.{name}: {name!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )

    for role in ("orchestrator", "verifier"):
        bound = data[role].get("unit")
        if bound is not None and bound not in units:
            raise ConfigSchemaError(
                f"{role}.unit: {bound!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )

    if data["verifier"]["enabled"] and data["verifier"]["unit"] is None:
        raise ConfigSchemaError(
            "verifier.unit: required key is not set. Verification is enabled, "
            "so it needs a unit to run on — bind one, or set "
            "`verifier.enabled: false` to accept on the deterministic gate "
            "alone."
        )


def _absent_remedy(path: Path | None) -> str:
    """What to do about a config that is not there, given who chose the path.

    Three situations wearing one exception. ``path`` is what the caller named
    on purpose — a ``--config`` flag — or ``None`` when nobody did and
    :func:`load` located the file itself; in that second case
    ``$MCGYVR_CONFIG`` may still have named it, and that is a third answer
    again.

    Nobody named one: both remedies are open and both are said. The variable
    named it: ``mcgyvr init`` writes to exactly that path — ``_init`` resolves
    its destination the same way and its help says so — so a fresh install
    with the documented ``export MCGYVR_CONFIG=...`` already done is one
    command from finished, and answering it with "set the variable" is advice
    to do again what has just been done. A flag named it: the file typed is not
    there, and only a different path helps.
    """
    if path is not None:
        return "Name one that is there."
    if named_config_path() is not None:
        return (
            "`mcgyvr init` writes there: run it to generate one, or "
            "name a file that already exists."
        )
    return (
        f"Run `mcgyvr init` to generate one, or set {CONFIG_PATH_ENV} "
        f"to point at an existing file."
    )


def load(path: Path | None = None) -> Config:
    """Load and validate the setup at ``path``, or the located one.

    A setup is a directory holding ``fleet.yaml`` and ``policy.yaml``:
    ``path`` names that directory, and ``None`` locates it (the environment
    override, then the working directory, then the user config dir). A policy
    file is optional — a fleet with one unit and no policy is the smallest
    working install — but a fleet file is not.
    """
    chosen = path
    where = path if path is not None else config_path()
    if where.is_file():
        # A single merged document, written by an editor or a test. A setup is
        # a directory, but this is the same content in one file and the two
        # readers below still see their own halves.
        try:
            text = where.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ConfigFileError(
                f"cannot read {where}: it is not UTF-8 text ({exc})"
            ) from exc
        except OSError as exc:
            raise ConfigFileError(f"cannot read {where}: {exc}") from exc
        try:
            return parse(text, path=where.resolve().parent)
        except ConfigError as exc:
            raise ConfigSchemaError(f"{where}: {exc}") from exc
    fleet_path = where / FLEET_FILENAME
    policy_path = where / POLICY_FILENAME
    try:
        fleet_text = fleet_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigMissingError(
            f"no fleet.yaml at {fleet_path}. {_absent_remedy(chosen)}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigFileError(
            f"cannot read {fleet_path}: it is not UTF-8 text ({exc})"
        ) from exc
    except OSError as exc:
        raise ConfigFileError(f"cannot read {fleet_path}: {exc}") from exc
    try:
        policy_text = policy_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        policy_text = ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigFileError(f"cannot read {policy_path}: {exc}") from exc
    try:
        return parse(fleet_text, policy_text, path=where)
    except ConfigError as exc:
        raise ConfigSchemaError(f"{where}: {exc}") from exc
