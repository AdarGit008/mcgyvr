"""Read mcgyvr's setup: what the units are, what the ladder is, and the policy.

A setup is read from a path or from text, flattened into one mapping, checked
key by key against `SCHEMA` (an unknown, missing or mis-typed key is refused
rather than ignored), cross-checked as a whole, and returned as a frozen
`Config` holding the declared `Unit`s, a `Ladder` and the values that were
actually written. No credential is ever a value here: the config records the
*name* of the environment variable that holds a key, and a key-shaped value or
key name is refused wherever it appears.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.fleet.files import (
    FleetFileError,
    _typename,
    load_fleet,
    load_policy,
    load_relief,
)
from mcgyvr.fleet.ids import _canonical_dump
from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir

# The use cases an install may serve, in the order setup offers them, are the
# wire's: `mcgyvr-code` opts in to mcgyvr between a model and you (contracts
# proposed, vetted, run up the ladder, gated, repaired, reviewed and
# re-planned, each stage under its own switch, `SWITCHES`, every one on by
# default); `code` is a coding model mcgyvr recommends, served raw; `chat` a
# raw, un-gated text endpoint; `agent` a raw, un-gated endpoint with
# tool-calling.
from mcgyvr.hubwire import AGENT as AGENT
from mcgyvr.hubwire import CHAT as CHAT
from mcgyvr.hubwire import CODE as CODE
from mcgyvr.hubwire import MCGYVR_CODE as MCGYVR_CODE
from mcgyvr.hubwire import RUNG_POSITIONS, rider_cap_fits
from mcgyvr.hubwire import USE_CASES as USE_CASES
from mcgyvr.sandbox.base import NETWORKS
from mcgyvr.schema import Dialect, join_path, walk_block
from mcgyvr.schema import Field as Field
from mcgyvr.strict_yaml import strict_loader

#: The three files a setup directory holds. `load()` reads all of them: fleet.yaml
#: is required and carries `units`; policy.yaml and relief.yaml are read as empty
#: text when they are absent.
FLEET_FILENAME = "fleet.yaml"
POLICY_FILENAME = "policy.yaml"
#: The rungs a hub lent you, written whole by `mcgyvr rig rungs sync`.
RELIEF_FILENAME = "relief.yaml"
# Names a setup path directly, ahead of the live fleet directory.
CONFIG_PATH_ENV = "MCGYVR_CONFIG"


class ConfigError(Exception):
    """Base for every error raised by this module."""


class ConfigFileError(ConfigError):
    """A setup file could not be read: an I/O error, or text that is not
    UTF-8."""


class ConfigMissingError(ConfigFileError):
    """No setup is named, and none was found where one was expected."""


class ConfigSchemaError(ConfigError):
    """A setup was read but does not hold up: an unknown, missing, mis-typed
    or cross-invalid key."""


class CredentialInConfigError(ConfigSchemaError):
    """A key is named like a credential, or a value is shaped like one, where
    only the name of the environment variable holding it is allowed."""


class UnboundValueError(ConfigError):
    """A key is not bound, or the environment variable it names is not set."""


#: Where a relief rung's host model sits against the models on your own rigs, as
#: the hub judges it: shown, never a place on the ladder. The wire's values.
POSITION_CHOICES: tuple[str, ...] = RUNG_POSITIONS

#: How a batch of work is placed across units. `none` takes the first rung in
#: ladder order whatever its load; `idle` and `full` take the first rung with a
#: slot free, and `idle` may also ride a relief rung once your own rungs are full.
FANOUT_CHOICES: tuple[str, ...] = ("none", "idle", "full")

#: Who picks the rung a contract's climb starts on. `none` starts on the first
#: rung; `jev` asks the unit bound to the `jev` role (see `mcgyvr.triage`).
TRIAGE_CHOICES: tuple[str, ...] = ("none", "jev")

#: What a batch does with a contract whose provider did not land. `hold` keeps
#: it back, unspent; `run` sends it anyway (see `mcgyvr.tree`).
DEPENDENTS_CHOICES: tuple[str, ...] = ("hold", "run")

#: How many times a batch (`mcgyvr PROMPT`) hands a line of work whose
#: ladder is spent back to the proposer to be re-planned (see
#: `mcgyvr.replan`); 0 turns re-planning off.
MAX_REPLANS_DEFAULT = 1

#: How many rounds a proposal the decomposer refused is handed back to the
#: proposer with what to change (see `mcgyvr.repropose`); 0 turns it off.
MAX_REPROPOSALS_DEFAULT = 1

#: How many split rounds classifier authoring may take on any one file, and
#: into how many parts one split may go (see `mcgyvr.refine`). The first is a
#: stop: what three rounds made is emitted. A split into more parts than the
#: second is refused with what to change rather than emitted unsplit.
MAX_SPLITS_PER_FILE_DEFAULT = 3
MAX_REFINE_FANOUT_DEFAULT = 8

#: Which failure-notes records a try is shown (see `mcgyvr.notes.handed_on`):
#: `climb` every record of the climb, `rung` this rung's previous attempt's,
#: `none` nothing.
RETRY_NOTES_CHOICES: tuple[str, ...] = ("climb", "rung", "none")

SANDBOX_FIELDS: tuple[Field, ...] = (
    Field(
        "mode",
        "enum",
        "`docker` runs each task in its own container, torn down after; with "
        "no Docker daemon answering, the task is refused unless "
        "`allow_fallback` is on. `tempdir` is the explicitly weaker mode for "
        "installs without Docker: a contract's acceptance commands run without "
        "a shell, but each runs whatever program it names, on the host, with "
        "only the host's process, network and resource isolation.",
        default="docker",
        choices=("docker", "tempdir"),
    ),
    Field(
        "allow_fallback",
        "bool",
        "What `mode: docker` does when no Docker daemon answers. Off, the task "
        "is refused and the refusal says how to go on. On, the task runs in "
        "the `tempdir` sandbox instead and says so once — the weaker mode, "
        "chosen ahead of time rather than read about after the run started.",
        default=False,
    ),
    Field(
        "network",
        "enum",
        "The network a task container is attached to. `bridge` is Docker's "
        "default: acceptance commands can fetch dependencies and reach the "
        "configured worker endpoints — and anything else this machine can "
        "reach. `none` gives the container no network at all, so a contract "
        "whose commands download anything fails. `none` needs `mode: docker`: "
        "the `tempdir` sandbox runs on this host, where the network cannot be "
        "taken away, and is refused under it.",
        default="bridge",
        choices=NETWORKS,
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
        "Commands run once when the task image is built, before any task. In "
        "docker mode the gate's type checker, eslint and prettier run in the "
        "task container, because their configuration can load code from the "
        "task's workspace, so they are found on the image's PATH. The image "
        "mcgyvr builds installs the one the repository configures (mypy, "
        "eslint, prettier) when its dependency install does not, at the "
        "lockfile's version where it pins one; pyright, or a checker the "
        "repository does not configure, is yours to put on the image, here or "
        "with `sandbox.image`. A checker the image lacks is skipped and said "
        "so, as an absent checker is on the host.",
        default=(),
    ),
)

DELIVERY_FIELDS: tuple[Field, ...] = (
    Field(
        "commit",
        "bool",
        "Whether a run commits an accepted change. Off, the change is "
        "left in your working tree, uncommitted, for you to review and commit. "
        "On, it is committed onto the branch you have checked out, or onto "
        "`branch` when that is set. `--commit` and `--no-commit` (on "
        "`mcgyvr PROMPT` and `mcgyvr direct`) "
        "decide for one run instead. Nothing here pushes or opens a pull "
        "request: the last step off this machine is yours.",
        default=False,
    ),
    Field(
        "branch",
        "str",
        "The branch an accepted change is committed onto, instead of the one "
        "you have checked out. It says where, not whether: nothing is "
        "committed while `commit` is off. A branch that does not exist is "
        "created from the commit you have checked out; one that does gets the "
        "commit on its tip, refused when its copy of the target differs from "
        "the one the change was judged against. Either way the branch you "
        "have checked out, your index and your working tree are left exactly "
        "as they were, and the run prints the `git push` to run. A branch "
        "checked out in another worktree is refused. `--branch NAME` "
        "names one for one run and implies `--commit`.",
        bind_hint="name a branch, or leave unset to commit onto the branch you "
        "have checked out",
    ),
)

#: The use cases that serve their model raw: no stage of `SWITCHES` runs, and the
#: contract verbs refuse (`requires_mcgyvr_code`).
RAW_USE_CASES: tuple[str, ...] = (CODE, CHAT, AGENT)

#: Use-case names an earlier build read and this one refuses, each with what
#: replaced it. There is no alias: a config, `setup --use-case` or `mcgyvr use`
#: that names one is refused with this sentence.
RETIRED_USE_CASES: dict[str, str] = {
    "coding": (
        "`coding` is no longer a use case: the gated coding it named is "
        "`mcgyvr-code`, and a coding model served raw is `code`; `mcgyvr use "
        "mcgyvr-code` rewrites the line"
    ),
}

#: What a batch does with two ready contracts whose scopes can write one file:
#: `wait` runs one after the other, `parallel` runs them at once.
SAME_FILE_CHOICES: tuple[str, ...] = ("wait", "parallel")

#: Where the journal is kept when `journal.dir` says nothing else: one directory
#: under the user's state directory, outside any repository a run works on.
#: A `journal.dir` overrides it, and the `~` that path may carry is expanded by
#: the reader. Nothing on the command line moves it.
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
        "it worth asking questions of. `--record DIR` on either verb adds a second "
        "copy for your own use. Read either copy back from DIR directly: one "
        "JSONL per writer, prompts and replies under `blobs/`, results under "
        "`results/`.",
        default=JOURNAL_DIR_DEFAULT,
    ),
)

# The figure a local unit's unset `request_timeout_s` is quoted as. A hosted unit
# waits for its reply however long it takes, so this bound only ever binds a unit
# on your own rig.
DEFAULT_REQUEST_TIMEOUT_S = 120.0

# How long `serving.servelib.wait_for` watches a unit come up: at most
# `HEALTH_POLLS` polls of the models it serves, `HEALTH_INTERVAL_S` seconds
# apart, so 120 polls of three seconds come to six minutes before it gives up.
HEALTH_POLLS = 120
HEALTH_INTERVAL_S = 3.0


BREADTH_FIELDS: tuple[Field, ...] = (
    Field(
        "draws",
        "int",
        "How many candidates one attempt asks its rung for before the gate "
        "picks between them. Draws are not attempts: they share one prompt and "
        "one attempt's budget, and the gate ranks the answers rather than the "
        "next attempt being told what the last one got wrong. The default of 1 "
        "is one draw, one verdict, and the draw is the answer.",
        default=1,
        min_value=1,
    ),
    Field(
        "temperature",
        "float",
        "What every draw after the first samples at. Draw 0 of every attempt "
        "is greedy (temperature 0.0), so a single-draw install sends what it "
        "always sent, byte for byte; draws 1..n-1 sample at this temperature, "
        "because a second draw exists to be a different candidate and a "
        "greedy one is the first draw again. 0.0 is refused at load wherever "
        "any unit's effective draws exceed 1: identical draws buy N gate runs "
        "and nothing else. The wire field is the OpenAI-compatible "
        "`temperature`. The journal records the temperature per row.",
        default=0.7,
        min_value=0.0,
        max_value=2.0,
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
        "by construction. It rewrites a file after the gate has spoken about "
        "it, so the bytes that come back are not the bytes the worker sent: "
        "the journal keeps the reply, the tree keeps the repaired file, and "
        "the verdict says a repair ran. Set false to have the rejection stand "
        "as the gate reached it. What no tool fixes — a failed acceptance "
        "command, a name, a line too long to wrap — is rejected exactly as "
        "before.",
        default=True,
    ),
)

GATE_FIELDS: tuple[Field, ...] = (
    Field(
        "enabled",
        "bool",
        "Whether the gate judges a change. Off, no language rung (syntax, lint, "
        "format, types, the semantic rung, `param_mutation`) and no acceptance "
        "command runs: a draw that changed its target is accepted as the worker "
        "left it, the run says `ungated` beside the change, delivery does not "
        "judge it again, and no repair runs, since a repair answers a rejection. "
        "The scope and secret checks and the parse of a structured file still "
        "refuse, because they guard the repository rather than judge the "
        "answer. The reviewer (`verifier.enabled`) is a switch of its own.",
        default=True,
    ),
    Field(
        "param_mutation",
        "enum",
        "A Python function that changes an object its caller passed in, on a "
        "line the change adds: it assigns or deletes into a parameter, an "
        "element of one or a loop variable over one (`rows[0] = x`, "
        "`item.count += 1`, `del table[key]`), or calls append, extend, insert, "
        "remove, pop, clear, sort, reverse, update, setdefault, add, discard or "
        "popitem on it. `self`, `cls`, `*args` and `**kwargs` are not checked, "
        "nor is a parameter rebound to a new object on every path before the "
        "change. `refuse` rejects the change. `report` does not reject it: the "
        "finding is listed among the gate's observations, which an enabled "
        "verifier is shown and the gate's retry note does not carry, and "
        "a run prints it once, before delivering the accepted change, "
        "as reported by this setting. `skip` does not look. Delivery judges the "
        "change again by the same setting. A contract whose `task` or "
        "`interface` asks for in-place work stands the check down under every "
        "setting.",
        default="refuse",
        choices=("refuse", "report", "skip"),
    ),
)

SERVING_FIELDS: tuple[Field, ...] = (
    Field(
        "enable_sleep_wake",
        "bool",
        "Whether mcgyvr may take a card down and bring it back on its own. Off "
        "by default, because the feature is a trade and not an improvement: "
        "turning it on lets a run stop containers on a rig other people "
        "share. It is a key here and not a `--flag` for the reason `--config` "
        "already gives about which rung runs — the config a run is "
        "made under is what a run is reproducible from, and a flag would let "
        "two runs share one config where only one of them started and stopped "
        "containers on a shared rig, putting the rig side effect outside the "
        "only record that explains the run. A card sleeps when a person runs "
        "`mcgyvr serve sleep`, or when a run swaps a sleeper in to make room "
        "and puts it back once it is idle; a sleep rests a vLLM card "
        "at level 2, which keeps its process and drops its weights and KV "
        "cache, and stops the containers of any other card, of a vLLM card "
        "with no sleep route, or of one holding a unit split across machines, "
        "whose level 2 is not measured; either way the next wake loads the "
        "model from "
        "disk. For that sleep it also makes `mcgyvr emit` start every vLLM "
        "unit with "
        "`--enable-sleep-mode` and `VLLM_SERVER_DEV_MODE=1`, which registers "
        "vLLM's development routes -- /sleep, /wake_up, /reset_prefix_cache "
        "and others -- on the unit's serving port, unauthenticated: anyone who "
        "can reach that port can sleep, wake or reset the unit. The emitted "
        "file says so in a comment. With the switch off, emit writes neither. "
        "It governs the *decisions*: `mcgyvr serve "
        "sleep|wake`, typed by a person who has therefore asked, is not gated "
        "by it. It is a key of its own rather than part of `fanout` because "
        "`fanout` decides where work goes among rungs that exist and "
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
        "`device: cuda:0` beside a unit's `address` would be two statements "
        "of one fact and would go stale the first time a unit was re-pointed, "
        "whereas this cannot go stale against anything — it says where files "
        "are, not where work runs. A config that omits it has no sleeping "
        "cards at all, only down ones: `asleep` is `down` plus a launch spec "
        "mcgyvr holds for that card, and with no directory there is no spec.",
        bind_hint=(
            "the directory `mcgyvr emit --out` writes to -- e.g. "
            "~/.mcgyvr/fleets/<fleet>/compose -- or leave it unset and this "
            "ladder has no "
            "sleeping cards, only down ones"
        ),
    ),
)

#: Whether a unit is up whenever its launch spec is (`always-on`), or a swap
#: partner that starts asleep (`sleeps-until-needed`) and wakes when needed.
ROLE_ALWAYS_ON = "always-on"
ROLE_SLEEPER = "sleeps-until-needed"
ROLES = (ROLE_ALWAYS_ON, ROLE_SLEEPER)

#: How a unit's server process is run: in a container the docker daemon keeps
#: up, or as the pinned llama.cpp binary mcgyvr fetches and supervises itself.
LAUNCHER_DOCKER = "docker"
LAUNCHER_NATIVE = "native"
LAUNCHERS = (LAUNCHER_DOCKER, LAUNCHER_NATIVE)
#: The systems whose machines run a unit natively by default: no NVIDIA
#: container runtime serves a GPU to a container there (Metal on macOS; on
#: Windows the pinned CUDA, Vulkan or CPU build).
NATIVE_BY_DEFAULT = ("darwin", "windows")


def default_launcher(*, local: bool, engine: str | None, system: str) -> str:
    """The launcher `setup` and `recommend` write for a unit.

    `native` for a llama.cpp unit (no `engine`, or `llama.cpp`) on the machine
    setup runs on (`local`) when that machine is macOS or Windows (`system`, as
    `mcgyvr.hostos.os_name` names it); `docker` otherwise, which is what a unit
    that states no launcher runs as.
    """
    if local and (engine or "llama.cpp") == "llama.cpp" and system in NATIVE_BY_DEFAULT:
        return LAUNCHER_NATIVE
    return LAUNCHER_DOCKER


#: The reply room, in tokens, that `mcgyvr setup --api` writes into a hosted
#: unit's `output_tokens`: the reply cap every request to that unit is sent,
#: hidden reasoning included. A hosted reasoning model spends its reasoning
#: inside the same budget, so the number is sized for a long deliberation rather
#: than a short answer. It is a value written into a file, not a default this
#: module applies: a unit that states its own `output_tokens` keeps it. The doc
#: of a unit's `output_tokens` quotes it.
API_OUTPUT_TOKENS = 32768

UNIT_FIELDS: tuple[Field, ...] = (
    Field(
        "address",
        "url",
        "Where this unit answers, including scheme and port. One address is \
"
        "one process.",
        required=True,
        bind_hint="e.g. http://box.example:8080",
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
        "launcher",
        "enum",
        "How this unit's server runs. `docker`: in a container, kept up by the "
        "docker daemon (Linux, NVIDIA). `native`: the llama.cpp release build "
        "mcgyvr pins, fetched into `bin/llama.cpp/<tag>/` under the mcgyvr "
        "home, checked against its pinned sha256, and kept up by mcgyvr's own "
        "supervisor, which "
        "restarts it with a growing pause and gives up after a few crashes: "
        "Metal on a Mac, CUDA where `nvidia-smi` reads a driver it runs, else "
        "Vulkan, else the CPU. A native unit listens on 127.0.0.1 alone, so no "
        "firewall asks, unless its `serve_args` state `--host`; its log is "
        "`logs/<container>.log` in the data folder. llama.cpp only. Absent "
        "means `docker`; `setup` writes `native` for a unit on a Mac or "
        "Windows machine it runs on.",
        choices=LAUNCHERS,
        bind_hint="e.g. native -- leave it out for a container",
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
        bind_hint="e.g. box.example",
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
        "Tokens this unit serves in one request. Read it back off the "
        "running process, not hoped for: `setup` reads it off a local "
        "backend and writes it, and lists a unit it could not read as not "
        "configured. Less the prompt, it is the room every reply on this unit "
        "is clamped to; a unit with neither `window` nor `output_tokens` "
        "refuses code dispatch.",
        min_value=1,
        bind_hint="e.g. 4096 -- what the unit reports, not what you hoped for",
    ),
    Field(
        "output_tokens",
        "int",
        "Room a reply on this unit is given, hidden reasoning included: the "
        "reply cap every request to it is sent — a rung's attempt, a "
        "decomposition, a review — clamped to the room `window` leaves the "
        "prompt where both are set. A hosted reasoning model needs tens of "
        f"thousands; `setup --api` writes {API_OUTPUT_TOKENS}.",
        min_value=1,
        bind_hint="e.g. 2048 -- the longest reply this unit gives",
    ),
    Field(
        "request_timeout_s",
        "float",
        "How long one dispatched request to this unit may take before the \
"
        "transport gives up, in seconds. Unset, a hosted unit (one with \
"
        "`api_key_env`) waits for its reply however long it takes, and a \
"
        f"local unit gives up after {DEFAULT_REQUEST_TIMEOUT_S:g} s.",
        min_value=0.0,
        bind_hint="seconds; leave it unset on a hosted unit",
    ),
    Field(
        "room_mib",
        "int",
        "The card room this unit needs, in MiB, measured or stated.",
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
        bind_hint="e.g. FLASH_ATTN: the backend the unit's own log names",
    ),
    Field(
        "container",
        "str",
        "The container name this unit runs under.",
        bind_hint="e.g. `mcgyvr-<host>-<unit>`",
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
        "sampling",
        "enum",
        "Who sets the sampling parameters of a request to this unit. "
        "`request`: the request states `temperature` -- 0.0 for the greedy "
        "first draw, `breadth.temperature` for the draws after it -- which is "
        "what a deterministic gate needs from a local unit. `server`: the "
        "unit's model fixes its own sampling and refuses the parameters, so "
        "none is sent; the hosted Claude models from Opus 4.7 on answer a "
        "request naming `temperature` with HTTP 400 (Anthropic's model "
        "migration guide). A `server` unit cannot be asked for more than one "
        "draw: without a temperature every draw is the first draw again. A "
        "fact about the unit's server, so it is here and not in the policy.",
        default="request",
        choices=("request", "server"),
    ),
    Field(
        "role",
        "enum",
        "Whether this unit is up whenever its launch spec is (`always-on`) or "
        "is a swap partner that starts asleep (`sleeps-until-needed`). A "
        "sleeper shares its card's one launch spec with the always-on units "
        "under a compose profile, so a whole `serve up` leaves it down and the "
        "awake set still fits the card. A run whose climb reaches it, or a "
        "fleet sample, swaps it in, stopping the units whose room it needs "
        "first; a sample starts those again when it sleeps. llama.cpp units "
        "only: "
        "a vLLM unit swaps at level 2 with its process kept.",
        default=ROLE_ALWAYS_ON,
        choices=ROLES,
    ),
    Field(
        "launch",
        "mapping",
        "The resolved launch, whole. Free-form by design: a unit hashes its \
"
        "whole resolved launch with no hand-kept field list, so a flag \
"
        "this reader has never heard of cannot go unhashed. `serve_args`, a \
"
        "list, is appended to the engine's argv as written. A llama.cpp \
"
        "server is launched with `--fit off` -- mcgyvr states its `-c` and \
"
        "`-ngl`, so llama.cpp's fitting to free memory only races the units \
"
        "starting beside it -- unless `serve_args` states `--fit` itself, \
"
        "e.g. `--fit on`; units on one card start together only when every \
"
        "one has fitting off. Two keys sizing \
"
        "reads, llama.cpp only: `speculative` (`none` | `mtp`, default `none`) \
"
        "runs the GGUF's own grafted multi-token-prediction head as the draft \
"
        "(`--spec-type draft-mtp`), and `spec_draft_n_max` (a count, at least \
"
        "1, default 2) is its `--spec-draft-n-max`. The head is read off the \
"
        "scan's tensor table and charged to the card, so the `--n-cpu-moe` \
"
        "floor rises, and a scan with no nextn block refuses the \
"
        "declaration. Whether it pays depends on the card and the width. \
"
        "A vLLM unit \
"
        "declaring `mtp` is refused: its speculative decoding is \
"
        "`--speculative-config`, a different mechanism. Keys that split a \
"
        "unit across cards, of one machine or several: `shards`, a list of \
"
        "`{rig, gpu}` (with `bind`, the IPv4 address a worker on another \
"
        "machine listens on, and `room_mib`, that card's room for the lock), \
"
        "the first on the machine the address names; `split` (`layer` | \
"
        "`tensor`, llama.cpp; `tensor` spans one machine's cards, and `row` \
"
        "has no split buffers on CUDA and is refused); `tensor_parallel` and \
"
        "`pipeline_parallel` \
"
        "(vLLM); `rpc_port` and `master_port`, the first port of llama.cpp's \
"
        "workers and vLLM's rendezvous port, each the engine's own default \
"
        "when absent; and `tensor_table_json`, a vLLM unit's `python -m \
"
        "mcgyvr.serving.safetensorscan` row. Each card is sized from the \
"
        "tensor table. A split left to mcgyvr is tensor across one machine's \
"
        "cards and pipeline across machines; what crossing between cards \
"
        "costs is reported, as an estimate by link class until your own \
"
        "reading replaces it (`mcgyvr fleet probe` times the links an awake \
"
        "split unit crosses) or your setting outranks both.",
        bind_hint="the resolved launch, e.g. serve_args, geometry_json, moe, "
        "speculative",
    ),
)

BUSY_ANSWER_FIELDS: tuple[Field, ...] = (
    Field(
        "status",
        "int",
        "The HTTP status of the answer.",
        required=True,
        min_value=100,
        max_value=599,
    ),
    Field(
        "code",
        "str",
        "The error code the answer's body carries (`error.code`).",
        required=True,
    ),
)

RELIEF_FIELDS: tuple[Field, ...] = (
    Field(
        "address",
        "url",
        "The hub's OpenAI-compatible address the rung is asked at, ending in `/v1`.",
        required=True,
        bind_hint="e.g. https://hub.example.org/v1, as the hub gave it",
    ),
    Field(
        "model",
        "str",
        "The model string sent with each request, as the hub gave it.",
        required=True,
    ),
    Field(
        "api_key_env",
        "env_name",
        "NAME of the environment variable holding your personal hub key, "
        "which each request carries.",
        required=True,
        bind_hint="the variable's NAME (e.g. MCGYVR_HUB_API_KEY), never the key",
    ),
    Field(
        "width",
        "int",
        "How many of your requests the rung takes at once.",
        required=True,
        min_value=1,
    ),
    Field(
        "position",
        "enum",
        "Where the host's model sits against the models on your own rigs, as "
        "the hub judges it. Shown, never a place on the ladder.",
        required=True,
        choices=POSITION_CHOICES,
    ),
    Field(
        "hosted_by",
        "str",
        "The handle of the person whose unit this is. They can read your "
        "prompts and the answers.",
        bind_hint="leave it to `mcgyvr rig rungs sync`, which writes the hub's word",
    ),
    Field(
        "served_model",
        "str",
        "What the host's unit runs, for display. Never sent.",
        bind_hint="leave it to `mcgyvr rig rungs sync`, which writes the hub's word",
    ),
    Field(
        "busy_answers",
        "block_list",
        "The answers, each an HTTP status and an error code, that say this "
        "rung cannot take a request now: one of them is a full rung, passed "
        "over at no cost, and any other answer is read as on any rung. Unset, "
        "the rung names no busy answers; a sync writes them.",
        block=BUSY_ANSWER_FIELDS,
        bind_hint="leave it to `mcgyvr rig rungs sync`, which writes them",
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

#: What the bound orchestrator unit is: a `proposer` that drafts contracts for
#: `mcgyvr PROMPT`, the only type there is.
ORCHESTRATOR_TYPES: tuple[str, ...] = ("proposer",)

ORCHESTRATOR_FIELDS: tuple[Field, ...] = (
    Field(
        "type",
        "enum",
        "What the bound unit is. `proposer`, the only type: the bound unit "
        "drafts contracts for `mcgyvr PROMPT`.",
        default="proposer",
        choices=ORCHESTRATOR_TYPES,
    ),
    Field(
        "authoring",
        "enum",
        "How `mcgyvr PROMPT` gets its proposals. `prose`: the bound unit is "
        "asked for JSON proposals (`delegate.build_prompt`), and the "
        "deterministic decomposer turns them into contracts. `classifier`: the "
        "`jev` unit answers typed questions (task type, target, symbol, task, "
        "interface, dependency, scope) first, and each proposal is split again "
        "until it is on one file and jev answers that it cannot be split "
        "further: a scope over several files becomes one proposal per file, and "
        "a proposal jev says holds several changes is split by the sentences of "
        "its task, the target's definitions it names, or the failing tests it "
        "demonstrates, as jev picks — two or more contracts on one file, which "
        "the dependency tree orders. A proposal is not split again once "
        "`max_splits_per_file` rounds have split its file; a split into more "
        "parts than `max_refine_fanout` is refused. `prose` stands in when jev "
        "declines. With no `jev` unit bound no model is asked: each field takes "
        "its first candidate — the first servable type and target, the "
        "target's first symbol, and the request as the task — and `prose` "
        "stands in only when there is no target or servable type to pick. "
        "Unset is `classifier` under `use_case: mcgyvr-code` when a `jev` unit "
        "is bound and on, and `prose` otherwise.",
        choices=("prose", "classifier"),
        bind_hint="name one of `prose`, `classifier`",
    ),
    *ROLE_UNIT_FIELDS,
)

JEV_FIELDS: tuple[Field, ...] = (
    Field(
        "enabled",
        "bool",
        "Whether the bound Jev unit is asked. Off, every typed decision is asked "
        "as if no unit were bound -- the verifier, the reviewing rung, the fast "
        "rung or the orchestrator answers, triage asks nobody, and authoring "
        "defaults to `prose` -- while the binding stays written, so turning it "
        "back on is one line.",
        default=True,
    ),
    *ROLE_UNIT_FIELDS,
)

VERIFIER_UNIT_FIELDS: tuple[Field, ...] = (
    Field(
        "enabled",
        "bool",
        "Model verification of the applied diff, on top of the gate. On unless "
        "set to `false`. With no `unit`, the reviewer is the next dearer local "
        "rung whose model is not the builder's; where there is none, the work "
        "is accepted and labelled unverified. A hosted unit reviews only when "
        "`unit` names it, or stands in for a hosted `unit` as `unit` says.",
        default=True,
    ),
    Field(
        "unit",
        "str",
        "Which unit reviews. A unit is the one term. It reviews every rung's "
        "work except work its own model wrote, because a model does not review "
        "its own output. That work is reviewed by a fallback: the usable rung "
        "nearest this unit on the ladder whose model is not the builder's — "
        "the rungs below it first, dearest first, then the rungs above it, "
        "cheapest first. A local rung may always be the fallback; a hosted one "
        "only when this unit is hosted and the rung is below it on the ladder. The "
        "result and the journal name the fallback and say it stood in; with "
        "none, the work is accepted and labelled unverified, saying why.",
        bind_hint="name one of the units declared under `units`",
    ),
    *(field for field in ROLE_UNIT_FIELDS if field.name != "unit"),
)

SCHEMA: tuple[Field, ...] = (
    Field(
        "use_case",
        "enum",
        "Which of the four use cases this install serves. `mcgyvr-code` opts in "
        "to mcgyvr between the model and you: contracts proposed, vetted, run up "
        "the ladder, gated, repaired, reviewed and re-planned, each stage under "
        "its own switch, every one on by default. `code` (a coding model), "
        "`chat` (a text endpoint) and `agent` (an endpoint with tool-calling) "
        "serve the model raw: no stage runs, and `mcgyvr PROMPT` and `mcgyvr "
        "direct` refuse. `mcgyvr use NAME` switches it. Unset is "
        "`mcgyvr-code`; `coding` is refused, naming what replaced it.",
        choices=USE_CASES,
        default=MCGYVR_CODE,
    ),
    Field(
        "deployment",
        "enum",
        "How mcgyvr is run. `hybrid` drives it from an API-tier "
        "orchestrator in the user's session; scoped work is offloaded to the "
        "local cheap-to-dear ladder, whose dearest rung is an API model so a "
        "task always completes. `local-only` makes mcgyvr the backend: "
        "`mcgyvr-code` provisions a local orchestrator unit, and a raw use case "
        "(`code`, `chat`, `agent`) is just the ladder serving its model.",
        choices=("hybrid", "local-only"),
        default="hybrid",
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
        choices=FANOUT_CHOICES,
    ),
    Field(
        "triage",
        "enum",
        "Who picks the rung a contract's climb starts on. `none` starts on the "
        "first rung and climbs. `jev` first asks the unit bound to `jev` one "
        "typed question: the contract and the ladder, each unit with its "
        "model, window and reply room, and which is the smallest unit that can "
        "do the job. The climb starts there; the rungs below it are skipped, "
        "not spent, and escalation goes on upward as before. `fanout` may then "
        "still start the climb on a higher rung with a free slot, never a "
        "lower one. With no jev unit bound, or one that cannot be asked or "
        "read, the climb starts on the first rung and the run result's "
        "`triage` says why. A contract that states a `start_rung`, decided "
        "ahead of time, starts there under either value and jev is not asked.",
        default="none",
        choices=TRIAGE_CHOICES,
    ),
    Field(
        "dependents",
        "enum",
        "What a batch of contracts (`mcgyvr PROMPT` or `mcgyvr direct`) does with a "
        "contract whose `depends_on` names one that did not land. `hold` keeps "
        "it back, unspent: it is sent only once what it waits on is in the "
        "tree its sandbox starts from, and one whose provider failed, or landed "
        "without a symbol it needs, is never sent — its result says `blocked`, "
        "who held it and what it needed, with no attempt spent. A contract "
        "that uses from the failed provider's file only names that are already "
        "there and that the provider was not to change still runs. `run` sends "
        "every contract once what it waits on has come to anything, as before.",
        default="hold",
        choices=DEPENDENTS_CHOICES,
    ),
    Field(
        "infer_dependencies",
        "bool",
        "Whether a batch of contracts also waits on what it can infer. On, a "
        "contract that uses a name the committed tree does not define yet waits "
        "on the sibling whose target creates it, though its `depends_on` does "
        "not say so, and one whose name nothing defines or creates is held. Off, "
        "a batch is ordered by `depends_on` alone. Contracts `mcgyvr PROMPT` "
        "proposes state such waits in `depends_on` themselves.",
        default=True,
    ),
    Field(
        "same_file",
        "enum",
        "What a batch run with `--jobs` does with two ready contracts whose "
        "scopes can write one file. `wait` runs the second once the first has "
        "settled, from the tree the first left. `parallel` runs them at once, "
        "from one base: their deliveries still take turns, and one that no "
        "longer applies is refused and named, never lost.",
        default="wait",
        choices=SAME_FILE_CHOICES,
    ),
    Field(
        "attempts",
        "int_map",
        "How many times each unit may be tried before escalation moves on.",
        default=None,
        min_value=1,
        bind_hint="e.g. `{<unit>: 2}`",
    ),
    Field(
        "draws",
        "int_map",
        "How many candidates one attempt asks *this* unit for, overriding "
        "`breadth.draws` for the units named; a unit with no entry draws the "
        "breadth. Spelled the way `attempts` is because it is the same kind of "
        "per-unit routing decision, and it is policy rather than a unit fact, "
        "which is why it is not under `units`. `mcgyvr local_pool` prints the "
        "effective number where it exceeds one.",
        default=None,
        min_value=1,
        bind_hint="e.g. `{<unit>: 3}`",
    ),
    Field(
        "rider_slots",
        "int_map",
        "How many of each named unit's slots riders may use at once "
        "(hitchhike): people the hub matches to you, whose requests for the "
        "unit's model the agent of `mcgyvr rig` passes to it and whose prompts "
        "you can read. A unit the map does not name shares none. It is policy, "
        "not a fact of the unit, so changing it never changes the setup's "
        "identity or its lock, and a running agent sends the hub the change "
        "within a second, with no reconnect. Below the unit's `width`, so you "
        "always "
        "keep a slot, and your own requests go first: a ride is taken only "
        "while the unit has a slot free, your requests and the rides in "
        "flight together fewer than its `width`, so riders use only slots you "
        "are not using, and a "
        "unit whose server does not report what it has in flight shares "
        "nothing. A ride that has started runs to its end; a request of yours "
        "that arrives meanwhile waits for a slot as any of yours does. A unit "
        "is shared only when it is on the `ladder`, needs no key "
        "(`api_key_env`), is not a relief rung, states its `window`, the "
        "context of each slot, and has a `width` of at most 16, the most the "
        "hub takes; one unit per model.",
        default=None,
        min_value=0,
        bind_hint="e.g. `{<unit>: 1}` -- at most one below the unit's `width`",
    ),
    Field(
        "max_escalations",
        "int",
        "How many rungs a task may climb before it is handed back unfinished. "
        "Unset: every rung of the ladder may be entered.",
        default=None,
        min_value=0,
        bind_hint="set a whole number of moves up the ladder, or leave it unset",
    ),
    Field(
        "max_replans",
        "int",
        "How many times a batch of contracts (`mcgyvr PROMPT`) hands "
        "a line of work whose ladder is spent back to the proposer to be "
        "re-planned. A contract that tried every rung and came to "
        "`ladder_spent` goes back with the failure notes its climb left, as "
        "evidence; the contract or contracts the proposer proposes in its "
        "place take its place in the batch, carry `replan` (the id they "
        "replace and the round), and what waited on it waits on them. A "
        "contract already at this round is not re-planned again, and one the "
        "proposer proposes unchanged is not run again. 0 turns re-planning "
        "off: a spent contract stops there, as under `mcgyvr direct`, which "
        "never re-plans.",
        default=MAX_REPLANS_DEFAULT,
        min_value=0,
        bind_hint="set a whole number of re-plans, or 0 to stop at a spent ladder",
    ),
    Field(
        "max_reproposals",
        "int",
        "How many times `mcgyvr PROMPT` hands a proposal the decomposer "
        "refused back to the proposer, with the refused field and what to "
        "change, before it reports the refusal. What comes back is checked as "
        "a first answer is: what it emits takes the refusal's place, and what "
        "is refused again is reported, or handed back again while rounds "
        "remain. A refusal of the request as a whole, or one that names no "
        "field, is reported at once. The prose proposer is shown the refused "
        "proposal and its refusal as data; the classifier asks the refused "
        "field again. 0 turns re-proposing off.",
        default=MAX_REPROPOSALS_DEFAULT,
        min_value=0,
        bind_hint="set a whole number of rounds, or 0 to report refusals at once",
    ),
    Field(
        "max_splits_per_file",
        "int",
        "How many split rounds classifier authoring (`orchestrator.authoring: "
        "classifier`, with a `jev` unit bound) takes on any one file. A "
        "proposal stops being split when it is on one file and either jev "
        "answers that it cannot be split further or its file has been split "
        "this many rounds; it is then emitted as it stands, not refused. "
        "Splitting a scope over several files into one proposal per file is "
        "not a round on any of them.",
        default=MAX_SPLITS_PER_FILE_DEFAULT,
        min_value=1,
        bind_hint="set a whole number of split rounds, 1 or more",
    ),
    Field(
        "max_refine_fanout",
        "int",
        "How many parts classifier authoring may split one proposal into at "
        "once: the files of a scope over several, or the parts of the split "
        "jev picks. A split into more is refused with this key to raise rather "
        "than emitted unsplit.",
        default=MAX_REFINE_FANOUT_DEFAULT,
        min_value=2,
        bind_hint="set a whole number of parts, 2 or more",
    ),
    Field(
        "retry_notes",
        "enum",
        "What a try is told about the attempts before it that failed. Each "
        "failed attempt leaves a record of what the gate, the reviewer or the "
        "reply parser observed, naming its rung and attempt. `climb`: every "
        "record of the climb, so a rung above starts with what the rungs "
        "below it were refused for — the latest in full, up to 20 notes, and "
        "the 4 before it a line each. `rung`: only the record of the attempt "
        "just before this one on the same rung. `none`: nothing.",
        default="climb",
        choices=RETRY_NOTES_CHOICES,
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
        "The largest share of a unit's context window one contract's prompt "
        "may claim, checked before the contract is sent, so the reply -- sent "
        "the unit's maximum within the room the prompt leaves -- keeps at "
        "least the rest; a contract claiming more fails unsent on the unit it "
        "was sent to. It is a ceiling no contract can raise: a "
        "contract's own `limits.max_window_fraction` may hold it to less, "
        "never to more, and the stricter of the two applies. Unset enforces "
        "no run-wide share.",
        min_value=0.0,
        max_value=1.0,
        bind_hint="a share between 0 and 1",
    ),
    Field(
        "users",
        "int",
        "Users this install serves at once, and therefore the slot count the "
        "local orchestrator unit is served at: one session per user. A "
        "written `width` on the orchestrator's unit wins. `1` is a "
        "single-user install, which for a local-only `mcgyvr-code` install is "
        "flagged, not refused — the resident orchestrator consumes the card "
        "the ladder would otherwise use.",
        default=1,
        min_value=1,
    ),
    Field(
        "orchestrator",
        "block",
        "Which unit turns a prompt plus a repository into contracts, and what "
        "that unit is.",
        block=ORCHESTRATOR_FIELDS,
    ),
    Field(
        "verifier",
        "block",
        "Which unit reads an applied diff in fresh context.",
        block=VERIFIER_UNIT_FIELDS,
    ),
    Field(
        "jev",
        "block",
        "Which one unit answers every typed decision: a question answered "
        "with a single-token label rather than prose. Those are the gate's "
        "Jev rung, the reviewer's verdict, the fleet's choice of whether to "
        "wake a smarter rung, the typed "
        "proposer and, under `triage: jev`, the rung a climb starts on. Left "
        "unbound, each of those keeps asking the unit it asks "
        "today: the verifier, the reviewing rung, the fast rung or the "
        "orchestrator, and triage asks nobody. `enabled: false` keeps the "
        "binding and asks as if it were unbound.",
        block=JEV_FIELDS,
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
        "gate",
        "block",
        "What the deterministic gate refuses, where a setup may choose otherwise.",
        block=GATE_FIELDS,
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
        "Where mcgyvr keeps its own record of what it dispatched. To say what "
        "a run belongs to — an experiment, a build — set `MCGYVR_RUN_TAGS` to "
        'a JSON object of text, number or true/false values, e.g. `{"round": '
        '"r7"}`, at most 4096 bytes: every row the run writes carries it under '
        "`run_tags`. Set to anything else, the run is refused before it starts.",
        block=JOURNAL_FIELDS,
    ),
    Field(
        "relief",
        "block_map",
        "Units other people lend you through a hub (hitchhike), keyed by name. "
        "Written whole to `relief.yaml` by `mcgyvr rig rungs sync`, and by "
        "nothing else. A relief rung is never a step of the ladder: under "
        "`fanout: idle` it takes work only when your own rung is full, ahead of "
        "a priced api rung, and no escalation climbs to it. Its host can read "
        "your prompts.",
        block=RELIEF_FIELDS,
    ),
)


# Key names a config may not use, compared lowercased. A key that names a
# credential is refused wherever it appears, so no setup can be read as holding
# a secret value, and the refusal says to name the environment variable that
# holds it (`api_key_env` on a unit) instead.
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

# Values shaped like a credential of a known provider: OpenAI/Anthropic-style
# `sk-` keys, GitHub tokens, AWS access keys, Slack tokens and Google API keys.
# A text value matching one is refused wherever it appears, so a key pasted in
# under a neutral key name is caught too.
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
    """One unit as a dispatch sees it: where it answers, what it serves, and
    how much of it one run may use. A relief rung is built as a `Unit` too,
    with the fields a relief block states filled in and nothing else."""

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
    #: Who states the sampling parameters of a request: `request` sends
    #: `temperature`, `server` sends none because the model fixes its own.
    sampling: str = "request"
    #: `always-on`, or `sleeps-until-needed` for a swap partner started on demand.
    role: str = ROLE_ALWAYS_ON
    #: `docker`, or `native` for the pinned llama.cpp binary mcgyvr supervises.
    launcher: str = LAUNCHER_DOCKER
    launch: Mapping[str, Any] = field(default_factory=dict)
    #: The slots riders from the hub may use on this unit at once, as
    #: `rider_slots.<name>` states it and always below the unit's `width`, so
    #: you keep one. A unit the map does not name shares none, so this is 0.
    #: It is policy, not a fact of the unit, so it never changes its identity.
    rider_slots: int = 0
    #: True for a rung lent to you through a hub: it is never a step of the
    #: ladder, only ridden under `fanout: idle` when your own rung is full, and
    #: only the facts a relief block states are filled in — `position`,
    #: `hosted_by`, `served_model`, `busy_answers` — not a rig of yours.
    relief: bool = False
    position: str | None = None
    hosted_by: str | None = None
    served_model: str | None = None
    #: The `(status, code)` answers that say the rung is full, as `busy_answers`
    #: states them; None when the rung names none.
    busy_answers: tuple[tuple[int, str], ...] | None = None

    @property
    def requires_credential(self) -> bool:
        return self.api_key_env is not None


@dataclass(frozen=True)
class Ladder:
    """The units work climbs, cheapest first, and the fan-out mode work is
    placed under."""

    names: tuple[str, ...]
    fanout: str = "none"

    def get(self, name: str) -> str | None:
        return name if name in self.names else None


#: The deployment in which mcgyvr is the backend: `mcgyvr-code` provisions a
#: local orchestrator unit, and a raw use case is the ladder serving its model.
LOCAL_ONLY = "local-only"


@dataclass(frozen=True)
class LocalOrchestrator:
    """What `local_orchestrator` decided: whether an orchestrator unit is
    provisioned, at what width, and whether a single-user install is flagged."""

    #: True when this install provisions a local orchestrator unit.
    provision: bool
    #: Slots the orchestrator is served at, one per user; None when it is not
    #: provisioned.
    width: int | None = None
    #: True for a single-user install, which is flagged rather than refused: the
    #: resident orchestrator consumes the card the ladder would otherwise use.
    flag_single_user: bool = False


def local_orchestrator(
    *, use_case: str, local_only: bool, users: int
) -> LocalOrchestrator:
    """Whether this install provisions a local orchestrator unit.

    A hybrid deployment provisions none, because an API-tier orchestrator
    drives it, and neither does a raw use case (`code`, `chat`, `agent`),
    which has no proposer in its path: it is the ladder serving the model.
    `mcgyvr-code` under local-only provisions one, served at `users` slots
    with one session per user, and a single user is flagged rather than
    refused. Raises `ValueError` when `users` is below 1 on that path; the
    other paths do not look at it.
    """
    if not local_only:
        return LocalOrchestrator(provision=False)
    if use_case != MCGYVR_CODE:
        return LocalOrchestrator(provision=False)
    if users < 1:
        raise ValueError(
            f"users must be at least 1 to provision a local orchestrator, got {users}"
        )
    return LocalOrchestrator(
        provision=True,
        width=users,
        flag_single_user=users == 1,
    )


@dataclass(frozen=True)
class Config:
    """A loaded setup: where it came from, the validated policy data, the
    declared units, the ladder, the values that were actually written and the
    relief rungs a hub lent you."""

    path: Path | None
    data: Mapping[str, Any]
    units: Mapping[str, Unit]
    ladder: Ladder
    declared: Mapping[str, Any] = field(default_factory=dict)
    relief: Mapping[str, Unit] = field(default_factory=dict)

    @property
    def is_local_only(self) -> bool:
        """True when no unit on the ladder needs a credential, so every rung
        is one of your own local units."""
        return not any(
            self.units[name].requires_credential for name in self.ladder.names
        )

    @property
    def use_case(self) -> str:
        """`use_case` from the config, `mcgyvr-code` when it is not set."""
        return str(self.get("use_case") or MCGYVR_CODE)

    @property
    def is_raw(self) -> bool:
        """True when the use case serves its model raw: no stage runs."""
        return self.use_case in RAW_USE_CASES

    @property
    def jev_on(self) -> bool:
        """True when a Jev unit is bound and `jev.enabled` leaves it on."""
        return bool(self.get("jev.unit")) and self.get("jev.enabled") is not False

    @property
    def authoring(self) -> str:
        """How proposals are authored: `orchestrator.authoring` when stated;
        otherwise `classifier` under `mcgyvr-code` with Jev on, else `prose`."""
        stated = self.get("orchestrator.authoring")
        if stated is not None:
            return str(stated)
        return "classifier" if self.use_case == MCGYVR_CODE and self.jev_on else "prose"

    @property
    def deployment(self) -> str:
        """`deployment` from the config, `hybrid` when it is not set."""
        return str(self.get("deployment", "hybrid"))

    @property
    def provisions_local_orchestrator(self) -> bool:
        """Whether this install provisions a local orchestrator unit, as
        `local_orchestrator` decides it from `use_case`, `deployment` and
        `users`."""
        return local_orchestrator(
            use_case=self.use_case,
            local_only=self.deployment == LOCAL_ONLY,
            users=int(self.get("users", 1)),
        ).provision

    def get(self, key: str, default: Any = None) -> Any:
        """The value at a dotted `key`, or `default` when no such key is
        bound.

        A list may be indexed by a numeric part; a key that is not there
        gives the default rather than an error.
        """
        try:
            return _dig(self.data, key)
        except KeyError:
            return default

    def require(self, key: str) -> Any:
        """The value at a dotted `key`, refused when it is absent or empty.

        `None`, an empty string, an empty tuple and an empty list all count
        as unbound, and the refusal names the key, the field's own doc and
        how to bind it.
        """
        try:
            value = _dig(self.data, key)
        except KeyError as exc:
            raise UnboundValueError(self._unbound(key)) from exc
        if value is None or value == "" or value == () or value == []:
            raise UnboundValueError(self._unbound(key))
        return value

    def secret(self, key: str) -> str:
        """The value of the environment variable that a dotted `key` names.

        Refused when the key is unbound or the variable is unset: the config
        carries the variable's name, never the secret, so the value comes
        from the environment and never from the file.
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
        """A canonical dump of the values that were written, which is what a
        setup's identity is computed from."""
        return _canonical_dump(self.declared)

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


@dataclass(frozen=True)
class Switch:
    """One point where mcgyvr changes what a model is sent or what comes back.

    `keys` are the policy keys (or, starting `--`, the flag) that switch it,
    `off` the value that takes mcgyvr out of that point, `doc` one line saying
    what the point does, `stage` the name `stages` answers it under (None for a
    tunable that is not an on/off stage), and `knob` its number among the four
    knobs `mcgyvr-code` exposes, `KNOBS`.
    """

    point: str
    keys: tuple[str, ...]
    off: str
    doc: str
    stage: str | None = None
    knob: int | None = None


#: The four knobs `mcgyvr-code` exposes, by number, in plain words.
KNOBS: dict[int, str] = {
    1: "ladder vs single model",
    2: "Jev unit on/off",
    3: "repair on/off",
    4: "attempts per rung and escalation",
}

#: Every point where mcgyvr sits between a model and you, with its switch. All
#: live in the policy; under a raw use case none of them runs. Operational
#: machinery (model loading, slots, sandbox, locks, waking a card) has none, nor
#: has vetting, which is what makes a proposal a runnable contract.
SWITCHES: tuple[Switch, ...] = (
    Switch(
        "authoring",
        ("orchestrator.authoring",),
        "`prose`",
        "how a request becomes proposals: typed Jev questions or one prose reply",
        stage="classifier",
    ),
    Switch(
        "Jev decisions",
        ("jev.enabled",),
        "`false`",
        "the one small unit that answers every typed decision",
        stage="jev",
        knob=2,
    ),
    Switch(
        "ladder",
        ("ladder", "max_escalations"),
        "one unit, or `0`",
        "climb cheapest first, or stay on one model",
        stage="ladder",
        knob=1,
    ),
    Switch(
        "attempts",
        ("attempts", "max_attempts", "max_escalations"),
        "per unit, ceilings",
        "tries per rung, in total, and moves up the ladder",
        knob=4,
    ),
    Switch(
        "triage",
        ("triage",),
        "`none`",
        "Jev picks the rung a climb starts on",
    ),
    Switch(
        "retry notes",
        ("retry_notes",),
        "`none`",
        "what a retry is told about the attempts that failed before it",
        stage="retry_notes",
    ),
    Switch(
        "draws",
        ("breadth.draws", "draws"),
        "`1`",
        "candidates one attempt asks for, the gate ranking them",
    ),
    Switch(
        "fan-out",
        ("fanout",),
        "`none`",
        "a batch spreads across units with free slots",
    ),
    Switch(
        "gate",
        ("gate.enabled", "gate.param_mutation"),
        "`false`",
        "the deterministic checks and acceptance commands that judge a change",
        stage="gate",
    ),
    Switch(
        "repair",
        ("cleanup.enabled",),
        "`false`",
        "the gate's own tools fix what they can in a rejected change",
        stage="repair",
        knob=3,
    ),
    Switch(
        "reviewer",
        ("verifier.enabled",),
        "`false`",
        "a second model, and Jev's typed checks, read the accepted diff",
        stage="reviewer",
    ),
    Switch(
        "replan",
        ("max_replans",),
        "`0`",
        "a contract whose ladder is spent goes back to be re-planned",
        stage="replan",
    ),
    Switch(
        "re-propose",
        ("max_reproposals",),
        "`0`",
        "a refused proposal goes back to the proposer with what to change",
        stage="repropose",
    ),
    Switch(
        "inferred edges",
        ("infer_dependencies",),
        "`false`",
        "a contract waits on the sibling that creates a name it uses",
        stage="inferred_edges",
    ),
    Switch(
        "same-file exclusion",
        ("same_file",),
        "`parallel`",
        "two contracts that can write one file never run at once",
        stage="same_file",
    ),
    Switch(
        "held dependents",
        ("dependents",),
        "`run`",
        "a contract whose provider did not land is held, not sent",
    ),
    Switch(
        "delivery",
        ("delivery.commit", "delivery.branch"),
        "`false`",
        "an accepted change is committed, not left in the working tree",
    ),
    Switch(
        "parallel dispatch",
        ("--jobs",),
        "`1`",
        "a batch runs ready contracts at once (`auto` under mcgyvr-code)",
    ),
)

#: The on/off stages `stages` answers, in the order `SWITCHES` names them.
STAGE_NAMES: tuple[str, ...] = tuple(s.stage for s in SWITCHES if s.stage is not None)


def stages(config: Config) -> dict[str, bool]:
    """Which stages stand between a model and you under this config.

    A raw use case runs none. `mcgyvr-code` runs each one its switch leaves on;
    repair answers the gate's rejections, so it runs only with the gate.
    """
    if config.is_raw:
        return dict.fromkeys(STAGE_NAMES, False)
    gate = config.get("gate.enabled") is not False
    on = {
        "classifier": config.authoring == "classifier",
        "jev": config.jev_on,
        "ladder": len(config.ladder.names) > 1 and config.get("max_escalations") != 0,
        "retry_notes": config.get("retry_notes", "climb") != "none",
        "gate": gate,
        "repair": gate and config.get("cleanup.enabled") is not False,
        "reviewer": config.get("verifier.enabled") is not False,
        "replan": int(config.get("max_replans", MAX_REPLANS_DEFAULT) or 0) > 0,
        "repropose": int(config.get("max_reproposals", MAX_REPROPOSALS_DEFAULT) or 0)
        > 0,
        "inferred_edges": config.get("infer_dependencies") is not False,
        "same_file": config.get("same_file", "wait") == "wait",
    }
    return {name: on[name] for name in STAGE_NAMES}


def requires_mcgyvr_code(config: Config) -> str | None:
    """Why a contract verb refuses this config, or None when it may run.

    The guard every verb that runs mcgyvr's pipeline calls once its config is
    loaded, before any model, gate or proposer is touched: a raw use case serves
    its model as is, so there is nothing for the verb to do.
    """
    if not config.is_raw:
        return None
    return (
        f"use case `{config.use_case}` serves its model raw: no proposer, gate, "
        f"repair, reviewer or ladder is in its path, so contracts are not run "
        f"here. `mcgyvr use mcgyvr-code` opts in to them."
    )


def default_jobs(config: Config) -> int:
    """How many contracts a batch runs at once when `--jobs` is not given:
    the fleet's slots (0, `auto`) under `mcgyvr-code`, one otherwise."""
    return 0 if config.use_case == MCGYVR_CODE else 1


def _declared(data: Any, raw: Any, fields: tuple[Field, ...]) -> dict[str, Any]:
    """The values a config actually wrote, pruned against the schema's
    defaults.

    `data` is the validated mapping and `raw` its counterpart straight from
    the file, so a key the schema filled in with a default is left out and
    only stated values are declared. Blocks, block maps and block lists
    recurse; every other kind is declared when it differs from its default,
    and a non-empty mapping is always declared.
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
            # Each entry is pruned against the raw entry of the same name, so
            # a key a block holds only because the schema filled it in is not
            # declared. The entry itself is kept even when it declares
            # nothing, so the dump still names every block that was written.
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


def field_at(key: str) -> Field | None:
    """The `Field` a dotted key names, or None when the schema has no such
    key."""
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
            index += 1  # step past the map or list key, which has no name here
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


_join = join_path


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


def _reject_credential_anywhere(raw: object, path: str) -> None:
    """Refuse a free-form mapping that holds a credential anywhere in it.

    Walks dicts and lists, checking every key name and every text value, so
    a mapping field (a unit's `launch`) cannot become a place a key is
    pasted into.
    """
    if isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(key, str):
                _reject_credential_key(key, path)
            _reject_credential_anywhere(item, _join(path, str(key)))
    elif isinstance(raw, list):
        for i, item in enumerate(raw):
            _reject_credential_anywhere(item, f"{path}.{i}")
    elif isinstance(raw, str):
        _reject_credential_literal(raw.strip(), path)


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
        # A bool is an int in Python, so it is excluded by name.
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
        # An int is a valid value here; a bool is not.
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
        if spec.kind == "enum" and value not in spec.choices:
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
        given = _mapping(raw, path)
        _reject_credential_anywhere(given, path)
        return dict(given)

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


#: The config's half of the schema walk.
_DIALECT = Dialect(
    noun="config",
    error=ConfigSchemaError,
    mapping=_mapping,
    value=_value,
    missing=_missing,
    default_for=_default_for,
    check_key=_reject_credential_key,
)


def _block(raw: object, fields: tuple[Field, ...], path: str) -> dict[str, Any]:
    return walk_block(raw, fields, path, _DIALECT)


def _refuse_userinfo(name: str, base_url: str, block: str = "units") -> None:
    """Refuse an address that carries `user:password@` in its URL.

    `name` and `block` say which address it is. The userinfo is refused
    because a URL is quoted in error messages, probe verdicts and
    `mcgyvr local_pool`, so a key written there reaches logs and terminals
    that a key in the environment never does.
    """
    userinfo = urllib.parse.urlsplit(base_url).netloc.rpartition("@")[0]
    if not userinfo:
        return
    raise ConfigSchemaError(
        f"{block}.{name}.address: carries credentials in the URL "
        f"({userinfo.split(':')[0]}:...@). A URL is quoted in error messages, "
        f"probe verdicts and `mcgyvr local_pool`, so a key written here reaches "
        f"logs and terminals that a key in the environment never does. Remove "
        f"the `user:password@` part and name the variable holding it with "
        f"`api_key_env`."
    )


def _resolved_paths(data: dict[str, Any], path: Path | None) -> dict[str, Any]:
    """Resolve each unit's relative `launch.geometry_json` against the
    config's own directory.

    A relative geometry is the scan filed beside the config file, so `path`
    is the directory it is read from and a config parsed without one is
    refused rather than resolved against the process's working directory. A
    path written in full, or with `~`, is expanded but not joined to it.
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
    """The setup path `MCGYVR_CONFIG` names, or None when it is unset."""
    override = os.environ.get(CONFIG_PATH_ENV)
    return Path(override).expanduser() if override else None


def config_path() -> Path:
    """The setup path to load: the one `MCGYVR_CONFIG` names, else the live
    fleet directory.

    Raises `ConfigFileError` when the live fleet cannot be read, and
    `ConfigMissingError` when no fleet is live, so the caller is told how to
    name or make one.
    """
    override = named_config_path()
    if override is not None:
        return override
    try:
        live = live_fleet_dir()
    except LiveFleetError as exc:
        raise ConfigFileError(str(exc)) from exc
    if live is None:
        from mcgyvr.fleet.roots import live_file

        raise ConfigMissingError(
            f"no setup is named: {CONFIG_PATH_ENV} is unset and no fleet is "
            f"live ({live_file()} names none). {_absent_remedy(None)}"
        )
    return live


def parse(
    fleet_text: str,
    policy_text: str = "",
    path: Path | None = None,
    relief_text: str = "",
) -> Config:
    """Parse setup text into a `Config`.

    `fleet_text` is the fleet document, `policy_text` the policy and
    `relief_text` the relief rungs. With no policy text the fleet text is
    split first, so one document holding every block is read as a whole
    setup. `path` is where the setup was loaded from: it is quoted in errors
    and a relative `launch.geometry_json` resolves beside it. A malformed
    document is refused as a `ConfigSchemaError`.
    """
    if not policy_text:
        fleet_text, policy_text, split_relief = _split_setup(fleet_text)
        relief_text = relief_text or split_relief
    try:
        fleet = load_fleet(fleet_text)
        policy = load_policy(policy_text) if policy_text.strip() else {}
        relief = load_relief(relief_text) if relief_text.strip() else {}
    except FleetFileError as exc:
        raise ConfigSchemaError(str(exc)) from exc
    return _build(fleet, policy, path, relief)


#: The top-level keys belonging to the fleet and relief documents rather than
#: the policy, used to split a setup written as one document.
_FLEET_ONLY = frozenset({"units", "rigs", "fleets"})
_RELIEF_ONLY = frozenset({"relief"})


def _split_setup(text: str) -> tuple[str, str, str]:
    """Split one setup document into fleet, policy and relief texts.

    Text that does not parse, or that has no `units` top-level key, is
    returned unchanged as fleet text, so the fleet reader reports what is
    wrong with it instead of this split guessing.
    """
    try:
        raw = yaml.load(text, Loader=strict_loader(ConfigSchemaError))
    except yaml.YAMLError:
        return text, "", ""
    if not isinstance(raw, dict) or "units" not in raw:
        return text, "", ""
    fleet = {key: value for key, value in raw.items() if key in _FLEET_ONLY}
    relief = {key: value for key, value in raw.items() if key in _RELIEF_ONLY}
    policy = {
        key: value
        for key, value in raw.items()
        if key not in _FLEET_ONLY and key not in _RELIEF_ONLY
    }
    return (
        yaml.safe_dump(fleet, sort_keys=False),
        yaml.safe_dump(policy, sort_keys=False) if policy else "",
        yaml.safe_dump(relief, sort_keys=False) if relief else "",
    )


def _build(
    fleet: Mapping[str, Any],
    policy: Mapping[str, Any],
    path: Path | None,
    relief: Mapping[str, Any] | None = None,
) -> Config:
    """Validate the three parsed documents into a `Config`.

    Fleet, policy and relief are merged, `rigs`, `fleets` and each unit's
    `unit_id` are dropped, and the result is read against `SCHEMA` and then
    cross-checked. The units become `Unit`s (relief rungs too, flagged as
    such), the ladder becomes a `Ladder`, and `declared` keeps only the
    values the config actually wrote.
    """
    merged: dict[str, Any] = {
        key: value
        for key, value in {**fleet, **policy, **(relief or {})}.items()
        if key not in ("rigs", "fleets")
    }
    if isinstance(merged.get("units"), Mapping):
        merged["units"] = {
            name: (
                {key: value for key, value in block.items() if key != "unit_id"}
                if isinstance(block, Mapping)
                else block
            )
            for name, block in merged["units"].items()
        }
    retired = RETIRED_USE_CASES.get(str(merged.get("use_case")))
    if retired is not None:
        raise ConfigSchemaError(f"use_case: {retired}")
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
            sampling=block.get("sampling") or "request",
            role=block.get("role") or ROLE_ALWAYS_ON,
            launcher=block.get("launcher") or LAUNCHER_DOCKER,
            launch=block["launch"],
            rider_slots=(data["rider_slots"] or {}).get(name, 0),
        )
        for name, block in data["units"].items()
    }
    lent = {
        name: Unit(
            name=name,
            address=block["address"],
            model=block["model"],
            api_key_env=block["api_key_env"],
            width=block["width"],
            relief=True,
            position=block["position"],
            hosted_by=block["hosted_by"],
            served_model=block["served_model"],
            # A rung that names no busy answers gets None, which is what a
            # dispatch reads as a rung that named none.
            busy_answers=tuple(
                (answer["status"], answer["code"]) for answer in block["busy_answers"]
            )
            or None,
        )
        for name, block in data["relief"].items()
    }
    ladder = Ladder(names=tuple(data["ladder"]), fanout=data["fanout"])
    return Config(
        path=path,
        data=data,
        units=units,
        ladder=ladder,
        declared=declared,
        relief=lent,
    )


def _cross_validate_fleet(data: Mapping[str, Any]) -> None:
    """Check the declared units, ladder and routing maps against each other.

    Every ladder step, `attempts` and `draws` entry must name a declared
    unit, no name may be used twice, no unit address may carry credentials,
    the draws a unit would use must be able to differ, and every role must
    bind a unit that exists. What each check refuses is a setup that could
    not dispatch, or would dispatch somewhere the file does not say.
    """
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

    overrides = data.get("draws") or {}
    for name in overrides:
        if name not in units:
            raise ConfigSchemaError(
                f"draws.{name}: {name!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )

    # More than one draw costs N gate runs, so the draws must be able to
    # differ: a temperature of 0.0 makes every draw the first draw again, and
    # a unit with `sampling: server` is sent no temperature at all. Either way
    # the extra draws would buy nothing, so both are refused rather than
    # accepted and ignored. A unit with no `draws` entry uses the breadth's.
    breadth = data["breadth"]["draws"]
    temperature = data["breadth"]["temperature"]
    widened = {
        name: overrides.get(name, breadth)
        for name in sorted(units)
        if overrides.get(name, breadth) > 1
    }
    if temperature == 0.0 and widened:
        listed = ", ".join(f"{name} draws {count}" for name, count in widened.items())
        raise ConfigSchemaError(
            f"breadth.temperature: 0.0 with {listed} asks for identical draws. "
            "Draw 0 is always greedy, so a temperature of zero makes every "
            "draw the first draw again, buying N gate runs and nothing else. "
            "Raise `breadth.temperature`, or set the draws back to 1."
        )
    fixed = {
        name: count
        for name, count in widened.items()
        if units[name].get("sampling") == "server"
    }
    if fixed:
        listed = ", ".join(f"{name} draws {count}" for name, count in fixed.items())
        raise ConfigSchemaError(
            f"{listed}, and `sampling: server` sends that unit no temperature, "
            "so every draw would be the first draw again. Set its draws to 1, "
            "or point the breadth at a unit whose requests state a temperature."
        )

    _cross_validate_relief(data, units)
    _cross_validate_shares(data, units)

    for role in ("orchestrator", "verifier", "jev"):
        bound = data[role].get("unit")
        if bound is not None and bound not in units:
            raise ConfigSchemaError(
                f"{role}.unit: {bound!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )


def _cross_validate_shares(data: Mapping[str, Any], units: Mapping[str, Any]) -> None:
    """Check `rider_slots`: only your own unit may be shared, and only below
    its width.

    A relief rung is not yours to share, a unit naming `api_key_env` is a
    provider's, and a count that is not below the unit's `width` would leave
    you no slot. A count of 0 shares nothing and passes.
    """
    for name, shared in (data.get("rider_slots") or {}).items():
        where = f"rider_slots.{name}"
        if name in data["relief"]:
            raise ConfigSchemaError(
                f"{where}: {name!r} is a relief rung, another person's unit "
                f"lent to you, and not yours to share with riders."
            )
        if name not in units:
            raise ConfigSchemaError(
                f"{where}: {name!r} is not a declared unit. "
                f"Declared: {', '.join(sorted(units))}"
            )
        if not shared:
            continue
        block = units[name]
        if block["api_key_env"] is not None:
            raise ConfigSchemaError(
                f"{where}: the unit names `api_key_env`, so it is a hosted "
                f"provider's and not yours to share with riders. Share a unit "
                f"you run, or remove the entry."
            )
        width = block["width"]
        if shared > 0 and not rider_cap_fits(shared, 1 if width is None else width):
            stated = "unset, so 1" if width is None else str(width)
            raise ConfigSchemaError(
                f"{where}: {shared} is not below the unit's `width` ({stated}). "
                f"Riders use part of the slots the unit serves at once, and you "
                f"keep at least one: set it below `width`, or 0 to share none."
            )


def _cross_validate_relief(data: Mapping[str, Any], units: Mapping[str, Any]) -> None:
    """Check the relief rungs: no name clashes with a unit of the fleet, since
    a name is one machine, and no address carries credentials."""
    for name, block in data["relief"].items():
        if name in units:
            raise ConfigSchemaError(
                f"relief.{name}: {name!r} is a unit of the fleet too. A name "
                f"is one machine; sync again, or rename the unit."
            )
        _refuse_userinfo(name, str(block["address"]), "relief")


def _absent_remedy(path: Path | None) -> str:
    """The sentence a missing-setup error ends with.

    It differs by how the setup was named: a path the caller passed means
    name one that is there, a path `MCGYVR_CONFIG` named means run `mcgyvr
    setup` or name an existing file, and with nothing named it means set up a
    fleet or point the variable at one.
    """
    if path is not None:
        return "Name one that is there."
    if named_config_path() is not None:
        return (
            "`mcgyvr setup` writes there: run it to generate one, or "
            "name a file that already exists."
        )
    return (
        f"Run `mcgyvr setup` to set up and make a fleet live, or point it at "
        f"an existing setup with `--config PATH` or `${CONFIG_PATH_ENV}`."
    )


def load(path: Path | None = None) -> Config:
    """Load the setup at `path`, or at `config_path()` when none is given.

    A path that names a file is read as one setup document; a directory is
    read as its fleet.yaml, with policy.yaml and relief.yaml read when they
    are there. Every read error and every schema error carries the path it
    came from.
    """
    chosen = path
    where = path if path is not None else config_path()
    if where.is_file():
        # A file is one setup document: `parse` splits it into fleet, policy
        # and relief. Only a directory is read as the three files. The file's
        # own directory is passed as `path`, so a relative geometry resolves
        # beside it.
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
    relief_path = where / RELIEF_FILENAME
    try:
        relief_text = relief_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        relief_text = ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigFileError(f"cannot read {relief_path}: {exc}") from exc
    try:
        return parse(fleet_text, policy_text, path=where, relief_text=relief_text)
    except ConfigError as exc:
        raise ConfigSchemaError(f"{where}: {exc}") from exc
