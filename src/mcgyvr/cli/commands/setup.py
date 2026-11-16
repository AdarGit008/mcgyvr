"""`mcgyvr setup`: stage a fleet config, then start, sample and lock it live.

Two ways in. With flags the command stages a config from named rigs — each one
scanned, then a model and engine recommended from its hardware — plus hosted
API units and a priority, and it starts nothing unless `--start` asks it to
emit and start the recommended servers after the write. Run with no flags on a
terminal, it is the wizard: it asks for the rigs, the use case and
Jev, reads each rig, plans a placement per rig, fetches missed weights,
stages the config, emits launch specs, starts the containers, samples them and
locks the fleet live on the user's yes. A fleet nothing could sample is locked
only once the user acknowledges it on no evidence. Every failure a step raises is
printed as an error and answered with exit code 1.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import hostos
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.capability import (
    CapabilityTableError,
)
from mcgyvr.config import (
    AGENT,
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    DEFAULT_ENGINE,
    DEPLOYMENT_FIELD,
    FLEET_FILENAME,
    MCGYVR_CODE,
    NATIVE_BY_DEFAULT,
    POLICY_FILENAME,
    RAW_USE_CASES,
    RETIRED_USE_CASES,
    USE_CASES,
    ConfigError,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.fleet.files import (
    FleetFileError,
    load_fleet,
    retired_policy_lines,
    without_retired_lines,
)
from mcgyvr.fleet.roots import (
    FolderError,
)
from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    unit_names,
)
from mcgyvr.scan import ModelOnDisk, Scan
from mcgyvr.serving import (
    UnitError,
    units_for,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.detect import Detection
    from mcgyvr.knowledge.record import ModelRecord

from mcgyvr.cli.common import INIT_DEFAULT_HELP, _named_path, _OneSetup
from mcgyvr.cli.setup_stages import CONTEXT_QUANT_CHOICES, Stop
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs
from mcgyvr.serving.rigfile import recorded_scans, resolve_hosts


class _SetupInteractiveError(Exception):
    """A wizard step could not finish; its message is the error setup reports."""


def _stdin_isatty() -> bool:
    """Answer whether stdin is a terminal, which the wizard needs to ask anything."""
    return sys.stdin.isatty()


def _setup_is_interactive(args: argparse.Namespace) -> bool:
    """Answer whether this run is the wizard: a terminal, and no flag that
    answers its questions.

    Any flag that names a host, a rig's address, an API unit, a use case or a
    Jev unit, or that forces the write, asks to start, or accepts an unsampled
    lock, makes the run the flag path instead. `--deployment` is the one
    exception: it answers a question the wizard itself asks, so it is carried
    into the wizard rather than silencing it.
    """
    if not _stdin_isatty():
        return False
    return not (
        bool(args.host)
        or bool(args.rig_address)
        or bool(args.api)
        or args.force
        or args.priority is not None
        or args.use_case is not None
        or args.jev is not None
        or args.start
        or args.accept_unsampled
    )


def _parse_setup_rigs(answer: str) -> tuple[str, ...]:
    """Read rig names from a typed answer, dropping `--host`, flags and repeats."""
    rigs: list[str] = []
    for token in answer.replace(",", " ").split():
        if token == "--host":
            continue
        if token.startswith("--host="):
            token = token.split("=", 1)[1]
        elif token.startswith("--"):
            continue
        if token:
            rigs.append(token)
    return tuple(dict.fromkeys(rigs))


_RIG_CHOICES = ("local", "remote", "both")


def _ask_setup_rigs() -> tuple[str, ...]:
    """Ask whether the local rig, remote rigs or both serve this setup, and
    answer the rigs.

    The local rig is named `localhost`; both puts it ahead of the remote rigs the
    next question names.
    """
    _note("local  — this machine only")
    _note("remote — GPU rigs you reach over ssh")
    _note("both   — this machine plus the remote rigs")
    said = _setup_choose(
        "Which rig(s) should serve this setup? [local] ",
        _RIG_CHOICES,
        "a rig choice",
    )
    if said == "local":
        return ("localhost",)
    hosts = _ask_remote_rigs()
    if said == "remote":
        return hosts
    return ("localhost", *hosts)


def _ask_remote_rigs() -> tuple[str, ...]:
    """Ask for remote rigs until one is named, or fail after ``_SETUP_TRIES``
    empty answers.

    A rig is named the way ssh names it — a host, or an alias from
    ``~/.ssh/config`` — never ``user@host``: the ssh user belongs in
    ``~/.ssh/config``.
    """
    _note("name each rig the way ssh names it — a host or an alias from ~/.ssh/config")
    for _ in range(_SETUP_TRIES):
        hosts = _parse_setup_rigs(_ask("Remote rig(s) (ssh host or alias): "))
        if hosts:
            return hosts
    raise _SetupInteractiveError("no remote rig was named")


def _parse_rig_addresses(specs: Sequence[str]) -> dict[str, list[str]]:
    """Each `RIG=ADDRESS` spec's addresses by rig, in the order given.

    A spec without `=`, or with nothing on either side of it, is a `ValueError`
    naming it; whether the address is one is for the rig file to say.
    """
    stated: dict[str, list[str]] = {}
    for spec in specs:
        rig, sep, address = spec.partition("=")
        if not sep or not rig.strip() or not address.strip():
            raise ValueError(
                f"--rig-address {spec!r} is not RIG=ADDRESS, e.g. gpu-box=10.0.0.7"
            )
        stated.setdefault(rig.strip(), []).append(address.strip())
    return stated


def _setup_rig_addresses(specs: Sequence[str]) -> int | None:
    """Record each `--rig-address` in its rig's file, or answer 1 on a refusal.

    Every spec is parsed before any file is written, so a malformed one leaves
    every rig file as it was. None when there was nothing to state, or all of it
    was recorded.
    """
    from mcgyvr.serving import rigfile

    try:
        stated = _parse_rig_addresses(specs)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for rig, addresses in stated.items():
        try:
            where = rigfile.state_addresses(rig, addresses)
        except rigfile.RigFileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"Recorded {', '.join(addresses)} as where {rig}'s units are "
            f"reached ({where})"
        )
    return None


def _ask_rig_addresses(rigs: Sequence[str]) -> None:
    """Ask for the address of each rig whose rig file records none, and record it.

    A rig's scan records the addresses it answers at; one that recorded none (no
    ssh, no `ip`) is asked for the address its units are reached at, offering
    what its name resolves to here. An empty answer with nothing offered leaves
    it unrecorded, and an answer that is not an address is asked again, up to
    `_SETUP_TRIES` times, after which the step fails naming it. This machine is
    not asked about: a name for it finds its rig by the machine's id.
    """
    from mcgyvr.detect import is_local_host
    from mcgyvr.serving import rigfile

    for rig in dict.fromkeys(rigs):
        if is_local_host(rig):
            continue
        saved = rigfile.read(rig)
        if saved is None or saved.reached_at:
            continue
        offered = next(
            (one for one in rigfile.addresses_of(rig) if _takes_address(one)), ""
        )
        _note(f"{rig}'s scan recorded no address its units are reached at")
        shown = f" [{offered}]" if offered else " (empty to skip)"
        said = ""
        for _ in range(_SETUP_TRIES):
            said = _ask(f"Address of {rig}{shown}: ") or offered
            if not said:
                break
            try:
                rigfile.state_addresses(rig, (said,))
            except rigfile.RigFileError as exc:
                print(f"{exc}.")
                continue
            print(f"Recorded {said} for {rig}")
            break
        else:
            raise _SetupInteractiveError(f"{said!r} is not an address for {rig}")


def _takes_address(said: str) -> bool:
    """Whether a rig file would take ``said`` as an address its units are reached at."""
    from mcgyvr.serving import rigfile

    try:
        rigfile.stated_address(said)
    except ValueError:
        return False
    return True


def _confirm(question: str, prompt: Callable[[str], str] = input) -> bool:
    """Answer whether a yes/no answer said yes: `y` or `yes`, and nothing else."""
    return str(prompt(question)).strip().lower() in {"y", "yes"}


def _ask(question: str, prompt: Callable[[str], str] = input) -> str:
    """Ask a question through `prompt` and answer the reply with whitespace stripped."""
    return str(prompt(question)).strip()


_SETUP_TRIES = 3


def _setup_choose(
    question: str,
    choices: Sequence[str],
    what: str,
    *,
    default: bool = True,
    names: Sequence[str] = (),
) -> str:
    """Ask for one of `choices`, taking the first as the default on an empty answer.

    With `default` off an empty answer is no answer: it is reported and asked
    again like any other. A word of `names` is taken as the choice at its
    position. An answer outside the choices is reported and asked for again, up
    to `_SETUP_TRIES` times, after which the step fails naming what it offers.
    """
    said = ""
    for _ in range(_SETUP_TRIES):
        said = _ask(question)
        if not said and default:
            return choices[0]
        if said in choices:
            return said
        if said in names:
            return choices[list(names).index(said)]
        if not said:
            print(f"There is no default here: pick one of {', '.join(choices)}.")
            continue
        print(f"{said!r} is not {what}: pick {_spoken_or(choices)}.")
    raise _SetupInteractiveError(
        f"{said!r} is not {what}; setup offers {_spoken_or(choices)}"
    )


def _spoken_or(names: Sequence[str]) -> str:
    """Render names the way a prompt says them: `a`, `a or b`, or `a, b or c`."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


_RULE_WIDTH = 72


def _rule(title: str) -> None:
    """A titled section divider on stdout: a blank line, then ``title`` centred
    on a rule of :data:`_RULE_WIDTH` box-drawing dashes.

    Purely presentational: it changes how the wizard reads in scrollback,
    never what setup decides or writes.
    """
    print()
    body = f" {title} "
    left = (_RULE_WIDTH - len(body)) // 2
    print("─" * left + body + "─" * (_RULE_WIDTH - len(body) - left))


def _note(text: str) -> None:
    """One indented note line on stdout, under a prompt it explains."""
    print(f"  {text}")


#: The prefix every "the fleet could not be made live" limit starts with.
_NOT_LIVE = "No fleet was made live"


def _refusal(lines: Sequence[str]) -> None:
    """A lock refusal boxed on stdout, unmissable in the wizard's scrollback.

    Purely presentational: it changes how a refusal reads in scrollback, never
    what setup decides or writes.
    """
    print()
    inner = max((len(line) for line in lines), default=0)
    bar = "─" * (inner + 4)
    print(f"┌{bar}┐")
    for line in lines:
        print(f"│ {line.ljust(inner)} │")
    print(f"└{bar}┘")
    print()


def _report_limits(limits: Sequence[str]) -> bool:
    """Print the setup limits: the fleet-not-live refusals boxed and loud,
    everything else under the usual "What is NOT configured" heading. Returns
    whether a refusal was among them, so the caller can skip the PATH offer."""
    refusals = tuple(line for line in limits if line.startswith(_NOT_LIVE))
    rest = tuple(line for line in limits if not line.startswith(_NOT_LIVE))
    if rest:
        print("What is NOT configured, and what that costs:")
        for limit in rest:
            print(f"  - {limit}")
    if refusals:
        _refusal(refusals)
    return bool(refusals)


def _setup_use_cases() -> tuple[str, ...]:
    """Answer the use-case names on offer, in the config's order: mcgyvr-code,
    then the raw ones.

    Only the catalog's use cases a config accepts are offered. The catalog is
    read here rather than imported at module load, so the setup command does not
    pull it in for runs that never ask.
    """
    from mcgyvr.catalog import catalog

    declared = {u.name for u in catalog().use_cases}
    return tuple(name for name in USE_CASES if name in declared)


#: The letter each offered use case is picked by, in `USE_CASES` order.
_USE_CASE_LETTERS = ("m", "k", "c", "a")


def _ask_setup_use_case() -> str:
    """Ask for a use case by single letter (or its name) and answer the name.

    There is no default: an empty answer is asked again, because choosing
    `mcgyvr-code` -- mcgyvr between the model and you -- is the act of opting
    in, and the raw use cases are the other choice, not a fallback.
    """
    names = _setup_use_cases()
    letters = _USE_CASE_LETTERS[: len(names)]
    by_letter = dict(zip(letters, names, strict=False))
    options = ", ".join(
        f"[{letter}] {name}" for letter, name in zip(letters, names, strict=False)
    )
    return by_letter[
        _setup_choose(
            f"Use case — {options}: ",
            letters,
            "a use-case letter",
            default=False,
            names=names,
        )
    ]


JEV_QUESTION = "Dedicate a unit to Jev, which answers typed decisions? [y/n] "


def _setup_pick_unit(role: str, units: Sequence[str]) -> str:
    """Ask which setup unit holds `role`, answering the only one if just one."""
    if len(units) == 1:
        return units[0]
    return _setup_choose(
        f"Which unit is {role}: {', '.join(units)}? [{units[0]}] ",
        units,
        "a unit of this setup",
    )


#: The coding branch's deployment question, and its two answers.
DEPLOYMENT_QUESTION = (
    "Run mcgyvr how? [hybrid] hybrid (an API-tier session agent drives it) "
    "or local-only (mcgyvr is the backend): "
)
#: The coding branch's fan-out question, default `idle` under mcgyvr-code.
FANOUT_QUESTION = "Fan-out across units? [idle] idle, none or full: "
#: The coding branch's sleep/wake switch, the fleet's `serving.enable_sleep_wake`.
SLEEP_WAKE_QUESTION = "May mcgyvr sleep and wake cards on its own? [y/n] "
#: The coding branch's ruff switch: the lint/format gate and its repair.
RUFF_QUESTION = "Install ruff and enable the lint/format gate and its repair? [y/n] "
#: The raw branch's context window question; Enter keeps the recommended one.
CONTEXT_SIZE_QUESTION = "Context window in tokens (Enter for the recommended): "
#: The raw branch's KV cache quant question, default `f16`.
CONTEXT_QUANT_QUESTION = f"KV cache quant? [f16] {', '.join(CONTEXT_QUANT_CHOICES)}: "
#: The raw branch's model question; Enter keeps the recommended one.
MODEL_QUESTION = "Model (id or path, Enter for the recommended): "
#: The agent branch's slot-count question, default 1.
SLOTS_QUESTION = "Slots (concurrent requests)? [1] "
#: The consent gate, between the printed placement and committing it.
CONSENT_QUESTION = "Commit this placement and stage the setup? [y/n] "
#: The skip-recommend branch: a model store, or leave it all-manual.
SKIP_REC_QUESTION = (
    "Skip the recommendation: [model-path] I have a model path, or "
    "[manual] I'll do it myself? [manual] "
)
MODEL_STORE_QUESTION = "Model store directory (a folder of .gguf files): "


def _ask_deployment(preferred: str | None = None) -> str:
    """Ask how mcgyvr is run, answering `preferred` when a flag already said.

    The default is `hybrid`; `local-only` makes mcgyvr the backend and, for
    `mcgyvr-code`, provisions a local proposer unit.
    """
    if preferred is not None:
        return preferred
    return _setup_choose(
        DEPLOYMENT_QUESTION,
        ("hybrid", "local-only"),
        "a deployment",
    )


def _ask_fanout() -> str:
    """Ask how batches spread across units; the gated default is `idle`."""
    return _setup_choose(
        FANOUT_QUESTION,
        ("idle", "none", "full"),
        "a fan-out",
    )


def _ask_sleep_wake() -> bool:
    """Ask whether the fleet switch `serving.enable_sleep_wake` is on."""
    return _confirm(SLEEP_WAKE_QUESTION)


def _ask_ruff() -> bool:
    """Ask whether ruff runs as the lint/format gate and its repair."""
    return _confirm(RUFF_QUESTION)


def _install_ruff() -> None:
    """Install ruff (`uv tool install ruff`) for the gate and its repair.

    The config is already staged; a missing `uv` or a failed install is
    reported, not fatal, so the run completes and a later install finishes
    what the gate needs.
    """
    done = subprocess.run(
        ["uv", "tool", "install", "ruff"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hostos.popen_no_window_kwargs(),
    )
    if done.returncode != 0:
        said = (done.stderr or done.stdout or "").strip()
        print(
            "ruff was not installed: `uv tool install ruff` failed"
            + (f": {said}" if said else ".")
        )


def _ask_context_size() -> int | None:
    """Ask for the served context window, or None for the recommended one."""
    for _ in range(_SETUP_TRIES):
        said = _ask(CONTEXT_SIZE_QUESTION)
        if not said:
            return None
        try:
            value = int(said)
        except ValueError:
            print(f"{said!r} is not a token count.")
            continue
        if value < 1:
            print("a context window is at least 1 token.")
            continue
        return value
    raise _SetupInteractiveError("no context window was named")


def _ask_context_quant() -> str:
    """Ask for the KV cache quant, defaulting to `f16` (the recommended one)."""
    return _setup_choose(
        CONTEXT_QUANT_QUESTION,
        CONTEXT_QUANT_CHOICES,
        "a KV cache quant",
    )


def _ask_model() -> str | None:
    """Ask for a model id or path to serve, or None for the recommended one."""
    return _ask(MODEL_QUESTION) or None


def _ask_slots() -> int:
    """Ask for the slot count a unit serves at once, defaulting to 1."""
    for _ in range(_SETUP_TRIES):
        said = _ask(SLOTS_QUESTION)
        if not said:
            return 1
        try:
            value = int(said)
        except ValueError:
            print(f"{said!r} is not a slot count.")
            continue
        if value < 1:
            print("a unit serves at least 1 request at once.")
            continue
        return value
    raise _SetupInteractiveError("no slot count was named")


def _ask_raw_model() -> tuple[int | None, str, str | None]:
    """Ask the raw use-case questions: context size, context quant, model."""
    return _ask_context_size(), _ask_context_quant(), _ask_model()


def _consent_to_placement() -> bool:
    """The consent gate: whether the printed placement may be committed.

    Nothing is staged unless this is an explicit yes; Enter is no.
    """
    return _confirm(CONSENT_QUESTION)


def _print_all_manual(use_case: str, rigs: Sequence[str]) -> None:
    """The all-manual terminal: nothing was stamped, so print how to do it by hand."""
    _rule("Nothing was stamped — the setup is all-manual")
    print("Nothing was written, started or locked. To stage this setup by hand:")
    named = " ".join(rigs) if rigs else "localhost"
    print(f"  1. mcgyvr scan --rig {named}")
    print(f"  2. mcgyvr recommend --profile {use_case} --users 1 --host {named}")
    print("  3. Write fleet.yaml and policy.yaml from that plan (see SETUP.md).")
    print("  4. mcgyvr emit, then mcgyvr serve up, sample and lock by hand.")
    print()


def _recommend_consented(
    rigs: Sequence[str],
    scans: Mapping[str, Scan],
    use_case: str,
    *,
    users: int = 1,
    auto: bool = False,
) -> dict[str, Mapping[str, Any]] | None:
    """Plan a placement, print it, and answer it only on the consent gate.

    A skipped recommendation asks whether the user has a model store to plan
    from instead, or will do the setup by hand; the latter is the all-manual
    terminal, answered None. With `auto` the placement is committed without
    asking.
    """
    model_stores: tuple[str, ...] = ()
    while True:
        plans = _setup_placements(
            rigs, scans, use_case, users=users, model_stores=model_stores
        )
        if auto or _consent_to_placement():
            return plans
        said = _setup_choose(
            SKIP_REC_QUESTION,
            ("model-path", "manual"),
            "a way to go on",
            names=("I have a model path", "I'll do it myself"),
        )
        if said == "manual":
            _print_all_manual(use_case, rigs)
            return None
        directory = _ask(MODEL_STORE_QUESTION)
        if not directory:
            _print_all_manual(use_case, rigs)
            return None
        model_stores = (directory,)


def _unit_overrides(
    context_size: int | None,
    context_quant: str,
    model: str | None,
    slots: int,
) -> dict[str, Any] | None:
    """The raw branch's per-unit choices, as fleet.yaml field overrides.

    Only a choice that differs from what `initialize` or the recommendation
    already writes is returned, so a default answer changes nothing.
    """
    overrides: dict[str, Any] = {}
    if context_size is not None:
        overrides["window"] = context_size
    if model is not None:
        overrides["model"] = model
    if slots != 1:
        overrides["width"] = slots
    if context_quant != "f16":
        overrides["launch"] = {
            "kv_cache_dtype_k": context_quant,
            "kv_cache_dtype_v": context_quant,
        }
    return overrides or None


def _apply_setup_choices(
    path: Path,
    *,
    detection: Detection,
    fanout: str | None = None,
    enable_sleep_wake: bool | None = None,
    ruff: bool | None = None,
    users: int | None = None,
    unit_overrides: Mapping[str, Any] | None = None,
) -> None:
    """Write the wizard's choices back into the staged config, over the files
    `initialize` wrote.

    Each choice is an existing schema field, never a new one: `fanout`,
    `users`, the `serving` block and the `gate`/`cleanup` switches in
    policy.yaml, and per-unit `window`, `width`, `model` and the KV cache
    launch keys in fleet.yaml. A choice of None leaves the field as
    `initialize` wrote it. `ruff` writes both `gate.enabled` and
    `cleanup.enabled` explicitly, because an unset field reads as on.
    """
    import yaml

    from mcgyvr.initialize import _policy_notes, render_fleet, render_policy

    fleet_path = path / FLEET_FILENAME
    policy_path = path / POLICY_FILENAME
    fleet = yaml.safe_load(fleet_path.read_text(encoding="utf-8"))
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    changed_policy = fanout is not None or users is not None
    if fanout is not None:
        policy["fanout"] = fanout
    if users is not None:
        policy["users"] = users
    if enable_sleep_wake is not None:
        policy.setdefault("serving", {})["enable_sleep_wake"] = enable_sleep_wake
        changed_policy = True
    if ruff is not None:
        policy.setdefault("gate", {})["enabled"] = ruff
        policy.setdefault("cleanup", {})["enabled"] = ruff
        changed_policy = True
    if unit_overrides:
        units = fleet.get("units") or {}
        for name in units:
            block = units[name]
            for key, value in unit_overrides.items():
                if value is None:
                    continue
                if key == "launch":
                    block.setdefault("launch", {}).update(value)
                else:
                    block[key] = value
        fleet_path.write_text(render_fleet(fleet), encoding="utf-8")
    if changed_policy:
        notes = _policy_notes(detection, policy)
        policy_path.write_text(render_policy(policy, notes), encoding="utf-8")


_PATH_EXPORT = hostos.PATH_EXPORT
_PATH_POWERSHELL = hostos.PATH_POWERSHELL
#: How long setup waits for PowerShell to name its profile.
_PROFILE_ASK_S = 15.0


def _shell_rc(shell: str | None, home: Path | None = None) -> Path | None:
    """Answer the file a shell reads at startup, or None for no or unknown shell.

    bash, zsh, sh/dash and fish each have their rc file under `home`, which
    defaults to the user's home directory, and PowerShell its profile
    (:func:`mcgyvr.hostos.shell_rc_file`, which names zsh's on macOS when no
    shell is named). A profile takes :data:`_PATH_POWERSHELL`, an rc file
    :data:`_PATH_EXPORT` (:func:`mcgyvr.hostos.path_line`).
    """
    return hostos.shell_rc_file(shell, home)


#: Where PowerShell 7's MSI installs it, "$Env:ProgramFiles\PowerShell\7", for
#: when it is not on PATH
#: (https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows).
_PWSH_DIRS = (("ProgramFiles", "C:\\Program Files", ("PowerShell", "7")),)
#: Windows PowerShell, which every Windows has, under the system folder.
_WINDOWS_POWERSHELL = ("System32", "WindowsPowerShell", "v1.0", "powershell.exe")
#: The execution policies under which an unsigned profile does not run
#: (https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies):
#: `Restricted` runs no script, profiles included, and is a Windows client's
#: policy when none is set; `AllSigned` runs only signed ones.
_NO_PROFILE_POLICIES = ("Restricted", "AllSigned")


def _powershell_exe(shell: str) -> str | None:
    """The PowerShell `shell` names, by its full path, or None.

    On Windows never by bare name, which would find a `pwsh.exe` left in the
    working folder first: Windows PowerShell is the one under
    `%SYSTEMROOT%\\System32`; PowerShell 7 is the one in a PATH folder named
    in full, else under Program Files (:func:`mcgyvr.hostos.program_in`).
    Elsewhere `shell` as `$SHELL` gives it, a path, or found on PATH.
    """
    base = os.path.basename(shell).lower().removesuffix(".exe")
    if hostos.os_name() != "windows":
        return shell if os.path.isabs(shell) else shutil.which(shell)
    if base == "powershell":
        root = os.environ.get("SYSTEMROOT") or "C:\\Windows"
        found = os.path.join(root, *_WINDOWS_POWERSHELL)
        return found if os.path.isfile(found) else None
    if base == "pwsh":
        folders = [
            os.path.join(os.environ.get(variable) or default, *parts)
            for variable, default, parts in _PWSH_DIRS
        ]
        return hostos.program_in("pwsh.exe", folders)
    return None


def _login_shell() -> str | None:
    """The shell whose startup file the PATH offer extends.

    `$SHELL` when it is set, on every system. Unset on Windows, PowerShell:
    PowerShell 7 (`pwsh`) when it is installed, else Windows PowerShell, which
    every Windows has. Unset elsewhere, None, which hostos reads as zsh on
    macOS and as no shell on Linux.
    """
    named = os.environ.get("SHELL")
    if named:
        return named
    if hostos.os_name() == "windows":
        return "pwsh" if _powershell_exe("pwsh") else "powershell"
    return None


#: What setup asks PowerShell: its effective execution policy, then the
#: profile it reads, in UTF-8 whatever the console's code page.
_POWERSHELL_ASK = (
    "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
    "Get-ExecutionPolicy; $PROFILE"
)


def _ask_powershell(shell: str) -> tuple[str | None, Path | None]:
    """PowerShell `shell`'s execution policy and the profile it reads.

    `$PROFILE` follows a Documents folder moved elsewhere (a synced folder,
    say), which the default under the home does not. The profile is taken
    only as an absolute `.ps1` path whose folder's parent exists, so a
    garbled answer makes no folders; anything else, a shell that cannot be
    found by full path, fails or is slow, answers None for both.
    """
    program = _powershell_exe(shell)
    if program is None:
        return None, None
    try:
        done = subprocess.run(
            [
                program,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _POWERSHELL_ASK,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROFILE_ASK_S,
            check=False,
            **hostos.popen_no_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    lines = [line.strip() for line in (done.stdout or "").strip().splitlines()]
    if done.returncode != 0 or len(lines) != 2:
        return None, None
    policy, named = lines[0] or None, Path(lines[1])
    if not (
        named.is_absolute() and named.suffix == ".ps1" and named.parent.parent.is_dir()
    ):
        return policy, None
    return policy, named


def _has_local_bin_path(text: str) -> bool:
    """Answer whether any line of the text already names ~/.local/bin on PATH.

    Either separator counts (`.local/bin`, PowerShell's `.local\\bin`), on a
    line naming `PATH` or PowerShell's `$env:Path` (in any case).
    """
    return any(
        (".local/bin" in line or ".local\\bin" in line)
        and ("PATH" in line or "$env:path" in line.lower())
        for line in text.splitlines()
    )


def _shown(rc: Path, base: Path) -> str:
    """`rc` as the offer names it: under `~` when it is in the home."""
    try:
        inside = rc.relative_to(base)
    except ValueError:
        return str(rc)
    return "~" + os.sep + str(inside)


#: What the PATH offer names when it leaves a startup file alone.
_UV_UPDATE_SHELL = (
    f"`uv tool update-shell` puts ~{os.sep}.local{os.sep}bin on PATH instead."
)


def _offer_path_append(
    prompt: Callable[[str], str] = input,
    shell: str | None = None,
    home: Path | None = None,
) -> Path | None:
    """Offer to put ~/.local/bin on the shell's PATH, answering the file or None.

    The shell defaults to the login shell (:func:`_login_shell`). Nothing is
    asked when the shell is unknown or its startup file already has that
    directory on PATH. A yes appends one line, the export for an rc file and
    PowerShell's for a profile, creating the file's directory when it is
    missing; a file that cannot be written is reported and answered as None.
    A PowerShell profile is the one PowerShell names when `home` is the
    user's own (not given), else the default under `home`; where PowerShell's
    execution policy runs no profile, nothing is asked or written and
    `uv tool update-shell` is named instead.
    """
    if shell is None:
        shell = _login_shell()
    base = home if home is not None else Path.home()
    rc = _shell_rc(shell, base)
    if rc is None:
        return None
    if rc.suffix == ".ps1" and hostos.os_name() != "windows":
        # PowerShell's line names Windows' folder and separator; PowerShell
        # on macOS or Linux is left as it is.
        return None
    if rc.suffix == ".ps1" and home is None and shell:
        policy, named = _ask_powershell(shell)
        if policy in _NO_PROFILE_POLICIES:
            # The profile would never run, and PowerShell would print an error
            # at every start; uv's own command needs no policy change.
            print(
                f"PowerShell's execution policy is {policy}, so it runs no "
                f"profile and none was changed; {_UV_UPDATE_SHELL}"
            )
            return None
        rc = named or rc
    try:
        text = rc.read_text(encoding="utf-8")
    except OSError:
        text = ""
    except UnicodeError:
        # Not UTF-8 (Windows PowerShell writes UTF-16 with `>` and Out-File,
        # the ANSI code page with Set-Content): a UTF-8 line appended there
        # would corrupt it, so it is left as it is.
        print(
            f"{_shown(rc, base)} is not UTF-8, so it was not changed; "
            + _UV_UPDATE_SHELL
        )
        return None
    if _has_local_bin_path(text):
        return None
    shown = _shown(rc, base)
    if rc.suffix == ".ps1":
        question = (
            f"Add ~{os.sep}.local{os.sep}bin to your PATH in your PowerShell "
            f"profile {shown}? [y/n] "
        )
    else:
        question = f"Add ~/.local/bin to your shell PATH in {shown}? [y/n] "
    if not _confirm(question, prompt):
        return None
    try:
        rc.parent.mkdir(parents=True, exist_ok=True)
        with rc.open("a", encoding="utf-8") as stream:
            stream.write(hostos.path_line(rc) + "\n")
    except OSError as exc:
        print(
            f"warning: could not add ~/.local/bin to {shown}: {exc}",
            file=sys.stderr,
        )
        return None
    return rc


def _setup_scan_rigs(
    rigs: Sequence[str],
) -> tuple[dict[str, Scan], dict[str, dict[str, Any]]]:
    """Read each rig once, answering the raw readings and the scans built from them.

    A rig that cannot be read is raised as the step's error, and repeats in
    `rigs` are read once.
    """
    from mcgyvr.fleet.promote import PromoteRefusedError

    scans: dict[str, Scan] = {}
    readings: dict[str, dict[str, Any]] = {}
    for rig in dict.fromkeys(rigs):
        try:
            reading = _read_rig(rig)
        except PromoteRefusedError as exc:
            raise _SetupInteractiveError(str(exc)) from exc
        readings[rig] = reading
        scans[rig] = Scan.from_json(json.dumps(reading))
    return scans, readings


#: What setup says answered a plan's candidates, by the plan's `candidates_from`.
_CANDIDATES_FROM = {
    "live": "the Hugging Face Hub, read now",
    "cache": "the cache of an earlier Hugging Face Hub read",
    "shipped": "the catalog shipped with mcgyvr",
}


def _setup_placements(
    rigs: Sequence[str],
    scans: Mapping[str, Scan],
    use_case: str,
    *,
    users: int = 1,
    model_stores: Sequence[str] = (),
) -> dict[str, Mapping[str, Any]]:
    """Plan a placement for each rig from its own scan, print it, and answer the plans.

    Each rig is planned alone, as one user of the use case asked, so what it can
    serve is read off its own machine; `users` is the slot count the agent
    branch asks, and `model_stores` the directories a skipped recommendation
    plans a local checkpoint from. Setup says where each plan's candidates
    came from: the Hub now, the cache of an earlier read, or the shipped
    catalog. A use case recommend does not place, a plan that recommends
    nothing, or one that carries no placement to serve, fails the step naming
    the rig.
    """
    profile = recommend_module.PROFILE_OF_USE_CASE.get(use_case)
    if profile not in recommend_module.PLACEMENT_PROFILES:
        raise _SetupInteractiveError(
            f"recommend places {', '.join(recommend_module.PROFILE_OF_USE_CASE)}, "
            f"not {use_case!r}"
        )
    plans: dict[str, Mapping[str, Any]] = {}
    for rig in dict.fromkeys(rigs):
        try:
            plan = recommend_module.plan(
                profile=profile,
                users=users,
                hosts=(rig,),
                premeasured={rig: scans[rig]},
                model_stores=model_stores,
            )
        except (recommend_module.RecommendError, recommend_module.CatalogError) as exc:
            raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        sys.stdout.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        answered = _CANDIDATES_FROM.get(str(plan.get("candidates_from")))
        if answered is not None:
            read_at = plan.get("candidates_read_at")
            print(
                f"{rig}: the {profile} candidates came from {answered}"
                f"{f' (read {read_at})' if read_at else ''}"
            )
        if not isinstance(plan.get("placement"), Mapping):
            raise _SetupInteractiveError(
                f"{rig}: recommend produced no placement to serve"
            )
        plans[rig] = plan
    return plans


def _setup_on_disk_match(
    scan: Scan | None, model_id: str, quant: str, size_bytes: int
) -> ModelOnDisk | None:
    """Answer the on-disk model that would serve this model id, quant and size.

    A model matches on its name, its full id or the id with `/` read as `_`,
    case aside. A quant or a size the caller names must agree too; a model whose
    quant the scan did not read matches any quant asked for.
    """
    if scan is None:
        return None
    basename = model_id.lower().rsplit("/", 1)[-1]
    canonical = model_id.replace("/", "_").lower()
    wanted_quant = (quant or "").lower()
    for model in scan.models_on_disk:
        if model.name.lower() not in (basename, model_id.lower(), canonical):
            continue
        if model.quant is not None and model.quant.lower() != wanted_quant:
            continue
        if size_bytes and model.size_bytes != size_bytes:
            continue
        return model
    return None


def _setup_downloads(
    plans: Mapping[str, Mapping[str, Any]],
    scans: Mapping[str, Scan],
    prompt: Callable[[str], str] = input,
) -> tuple[tuple[str, ModelRecord], ...]:
    """Ask, rig by rig, whether to fetch that rig's placement model and answer what.

    A model already on the rig's disk is offered for reuse first, and a yes
    there skips the fetch. A model that is not on disk is asked as a download,
    defaulting to no. A chosen model must have a known download record carrying
    weights, or the step fails.
    """
    from mcgyvr.knowledge import store as knowledge_store

    known = {record.key: record for record in knowledge_store.offline().records}
    downloads: list[tuple[str, ModelRecord]] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            # Nothing is named to fetch for a placement that serves no model.
            continue
        quant = str(placement.get("quant") or "")
        size_bytes = int(placement.get("size_bytes") or 0)
        scan = scans.get(rig)
        hit = _setup_on_disk_match(scan, model_id, quant, size_bytes)
        if hit is not None:
            answer = prompt(
                f"{rig}: {model_id} {quant} ({hit.size_bytes} bytes) is already "
                f"on disk. Reuse it instead of downloading? [y/n, Enter reuses] "
            )
            if str(answer).strip().lower() not in {"n", "no"}:
                print(f"{rig}: reusing {model_id} {quant} already on disk")
                continue
            chosen = True
        else:
            answer = prompt(
                f"Download {model_id}{' ' + quant if quant else ''} for {rig}? [y/n] "
            )
            chosen = str(answer).strip().lower() in {"y", "yes"}
        if not chosen:
            continue
        record = known.get((model_id, quant))
        if record is None or record.weights is None:
            raise _SetupInteractiveError(
                f"{model_id} {quant}: no download record is known for this model"
            )
        downloads.append((rig, record))
    return tuple(downloads)


def _setup_suffix() -> str:
    """Answer a suffix naming this wizard run: process id plus a millisecond stamp."""
    import os
    import time

    return f"setup-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


def _setup_fetch(rig: str, record: ModelRecord, path: Path) -> None:
    """Fetch one model onto one rig via the door's fetch, keeping its list in the setup.

    The fetch list is written beside the staged setup as `fetch-<host>.json`;
    a door run that exits non-zero fails the step.
    """
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import fetchlist, safe_host
    from mcgyvr.serving.gatelib import DOOR_MODULE

    wants = fetchlist.from_records([record])
    path.mkdir(parents=True, exist_ok=True)
    fetch_file = path / f"fetch-{safe_host(rig)}.json"
    fetch_file.write_text(fetchlist.dump(wants), encoding="utf-8")
    code = wakelib.spawn_door(
        [
            sys.executable,
            "-m",
            DOOR_MODULE,
            "serve",
            "fetch",
            "--host",
            rig,
            "--weights",
            str(fetch_file),
            "--suffix",
            _setup_suffix(),
        ]
    )
    if code != 0:
        raise _SetupInteractiveError(f"{rig}: serve fetch exited {code}")
    print(f"{rig}: fetched {record.model_id} {record.quant}")


def _setup_synthetic_detection(
    plans: Mapping[str, Mapping[str, Any]], window: int | None = None
) -> Detection:
    """Build the detection setup stages from its plans, probing no running server.

    Each placement becomes one openai-shaped backend on its rig: vllm on the
    stock vLLM server's port, which the detect sweep already records in
    ``PORT_CONVENTIONS``; anything else as llama-server on the one unit default
    (``DEFAULT_PORT``, 8080 for every engine). The backend is named after the rig
    once there is more than one. A placement with no model fails the step,
    because a local checkpoint is not bootstrapped here.
    """
    from mcgyvr.detect import PORT_CONVENTIONS, Backend, Detection
    from mcgyvr.serving import DEFAULT_PORT

    # The sweep's list of stock ports, read here so vLLM's 8000 is stated once,
    # in detect, rather than spelled a second time in setup.
    stock_ports = {kind: port for kind, port, _ in PORT_CONVENTIONS}

    backends: list[Backend] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            raise _SetupInteractiveError(
                f"{rig}: its placement is a local checkpoint, and setup "
                "does not bootstrap from a local store yet"
            )
        engine = str(placement.get("engine") or DEFAULT_ENGINE)
        kind = "vllm" if engine == "vllm" else "llama-server"
        port = stock_ports["vllm"] if engine == "vllm" else DEFAULT_PORT
        name = f"{rig}_{kind}" if len(plans) > 1 else kind
        backends.append(
            Backend(
                name=name,
                base_url=f"http://{rig}:{port}/v1",
                api="openai",
                models=(model_id,),
                how="setup placement",
                host=rig,
                kind=kind,
                window=window,
            )
        )
    return Detection(
        backends=tuple(backends), provenance={"backends": "setup placement"}
    )


def _setup_context_window(plans: Mapping[str, Mapping[str, Any]]) -> int:
    """Answer the smallest context window the plans declare; slots are sized to it.

    A placement that declares no positive window fails the step naming its rig.
    """
    windows: list[int] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        ctx = placement.get("context_length")
        if not isinstance(ctx, int) or isinstance(ctx, bool) or ctx <= 0:
            raise _SetupInteractiveError(
                f"{rig}: its placement declares no context window to size at"
            )
        windows.append(ctx)
    return min(windows)


def _setup_emit(path: Path, ctx_per_slot: int) -> None:
    """Write the staged setup's launch specs via `mcgyvr emit` over the config in place.

    The config is both read and written at `path`, and an emit that exits
    non-zero fails the step.
    """
    from mcgyvr.cli.dispatcher import main

    code = main(
        [
            "emit",
            "--config",
            str(path),
            "--out",
            str(path),
            "--ctx-per-slot",
            str(ctx_per_slot),
        ]
    )
    if code != 0:
        raise _SetupInteractiveError(f"mcgyvr emit exited {code}")


def _setup_start(rigs: Sequence[str], scans: Mapping[str, Scan], path: Path) -> None:
    """Start every rig's containers from the launch spec emitted for it, at once.

    A rig with one whole-host spec is started from that file; a rig with
    several per-model alternatives is refused, since the wizard cannot choose
    between them, and every rig is checked before any is started. The rigs'
    doors then run at the same time, one each, so a rig's units load while
    another's do rather than after them. The door is told where the setup
    lives, and an up that exits non-zero on any rig fails the step, naming
    each rig that failed.
    """
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import spec_files, spec_name

    starts: list[tuple[str, Path]] = []
    for rig in dict.fromkeys(rigs):
        scan = scans[rig]
        host = scan.machine.host
        try:
            whole = path / spec_name(host)
        except UnitError as exc:
            raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        if whole.is_file():
            compose = whole
        else:
            files = spec_files(path, host)
            if not files:
                # One unit per model means a rig serves only the model placed
                # on it, so emit writes no spec for a rig that hosts none. That
                # is a rig of this setup left idle rather than a failure: its
                # units are hosted, and the rig that does serve the model is
                # started on its own turn.
                print(
                    f"{rig}: no launch spec was emitted for {host} — its model "
                    "is served from another rig (one unit per model); leaving "
                    "it idle"
                )
                continue
            if len(files) > 1:
                raise _SetupInteractiveError(
                    f"{rig}: mcgyvr emit wrote alternatives for {host}; "
                    "start one by hand"
                )
            compose = files[0]
        starts.append((rig, compose))
    env = {
        **os.environ,
        # The door reads the setup to bring up from this variable, so it
        # finds the same config this run staged and emitted.
        CONFIG_PATH_ENV: str(path),
    }
    # One suffix names this start on every rig; each door's run id also
    # carries its rig, so the runs stay apart.
    suffix = _setup_suffix()

    def up(start: tuple[str, Path]) -> int:
        rig, compose = start
        return wakelib.spawn_door(
            wakelib.door_argv(direction="up", host=rig, compose=compose, suffix=suffix),
            env=env,
        )

    if not starts:
        return
    # One worker per rig, as `availability` probes its sources: each door
    # waits on its own rig, so the step lasts as long as the slowest rig.
    with ThreadPoolExecutor(max_workers=len(starts)) as pool:
        codes = list(pool.map(up, starts))
    failed = [
        f"{rig}: serve up exited {code}"
        for (rig, _), code in zip(starts, codes, strict=True)
        if code != 0
    ]
    if failed:
        raise _SetupInteractiveError("; ".join(failed))


def _native_rigs(rigs: Sequence[str]) -> tuple[str, ...]:
    """The rigs among `rigs` whose units run natively: this machine, on macOS
    or Windows (:func:`mcgyvr.config.default_launcher`). Remote rigs are
    containers."""
    from mcgyvr.detect import is_local_host

    if hostos.os_name() not in NATIVE_BY_DEFAULT:
        return ()
    return tuple(rig for rig in dict.fromkeys(rigs) if is_local_host(rig))


def _start_question(rigs: Sequence[str]) -> str:
    """The start step's question, naming what it starts.

    The serving containers, as on Linux; native llama.cpp servers when every
    rig is this Mac or Windows machine; both, said apart, when remote rigs
    serve beside it.
    """
    named = ", ".join(rigs)
    here = _native_rigs(rigs)
    if not here:
        return f"Start the serving containers on {named}? [y/n] "
    remote = [rig for rig in dict.fromkeys(rigs) if rig not in here]
    if not remote:
        return f"Start the native llama.cpp servers on {named}? [y/n] "
    return (
        f"Start the servers (native here, containers on {', '.join(remote)}) "
        f"on {named}? [y/n] "
    )


def _native_notes(rigs: Sequence[str]) -> tuple[str, ...]:
    """What starting this machine's native units does, said before the question.

    Nothing when no rig of `rigs` runs natively. Otherwise: the first start
    fetches the pinned llama.cpp build into the mcgyvr home and checks its
    sha256 (and, on macOS, clears the quarantine flag the fetch would leave);
    and a native server listens on 127.0.0.1 alone, so no firewall is
    expected to ask, the rig agent relaying a hub's requests to it on macOS.
    """
    if not _native_rigs(rigs):
        return ()
    from mcgyvr.serving import llamacpp, native

    cleared = (
        ", and clears macOS's quarantine flag from it"
        if hostos.os_name() == "darwin"
        else ""
    )
    return (
        "This machine's units run natively, with no container: the first start "
        f"fetches the pinned llama.cpp {llamacpp.TAG} build into "
        f"{native.bin_root()} and checks its sha256{cleared}.",
        "A native server listens on 127.0.0.1 only, so the firewall is not "
        "expected to ask; "
        + (
            "the rig agent (`mcgyvr rig run`) relays a hub's requests to it."
            if hostos.os_name() == "darwin"
            else "it serves this machine, since the rig agent that relays a "
            "hub's requests does not run on Windows yet."
        ),
    )


def _setup_interactive(
    path: Path,
    run_id: str = "",
    *,
    auto: bool = False,
    stop: Stop | None = None,
    deployment: str | None = None,
) -> int:
    """Run the wizard end to end, walking the ordered decision tree in
    :data:`mcgyvr.cli.setup_stages.DECISION_TREE`, and answer the exit code.

    The tree: rigs, then the use case. The coding branch asks deployment,
    Jev, fan-out, sleep/wake and ruff (the lint/format gate and its
    repair); the chat branch asks context size, context quant and model,
    and the agent branch adds slots. The scan and
    recommendation run next, and the placement they print is committed only
    on the consent gate; a skipped recommendation asks for a model path or
    leaves the setup all-manual. Downloads, then start, sample and lock run
    as before. With `auto` the placement, the start and the lock run without
    asking; with `stop` one of :data:`~mcgyvr.cli.setup_stages.Stop` the
    pipeline stops after that stage, so a manual run can write only the
    config, only the launch specs, or bring the servers up without sampling
    or locking. What was decided and what was left unconfigured are printed
    at the end, along with the offer to put ~/.local/bin on PATH and, once
    the servers are up, the endpoint and key a custom provider points at. A
    step's error, or a refused init, config or capability table, is printed
    and answered with 1.
    """
    run_id = run_id or _setup_run_id()
    try:
        path.mkdir(parents=True, exist_ok=True)
        print("mcgyvr setup")
        print(
            "Read each rig, plan a model per rig, then start and sample a "
            "fleet and lock it live on your yes."
        )
        _rule("Step 1 of 4 — where it runs")
        rigs = _ask_setup_rigs()
        print(f"Serving on: {', '.join(rigs)}")
        _rule("Step 2 of 4 — what it serves")
        use_case = _ask_setup_use_case()

        # The use-case branch: coding asks deployment, Jev, fan-out,
        # sleep/wake and ruff; the raw use cases ask context size, quant and
        # model, and agent adds the slot count.
        wants_jev = False
        fanout: str | None = None
        enable_sleep_wake: bool | None = None
        ruff_on: bool | None = None
        context_size: int | None = None
        context_quant = "f16"
        model: str | None = None
        slots = 1
        if use_case == MCGYVR_CODE:
            deployment = _ask_deployment(deployment)
            wants_jev = _confirm(JEV_QUESTION)
            fanout = _ask_fanout()
            enable_sleep_wake = _ask_sleep_wake()
            ruff_on = _ask_ruff()
        elif use_case == AGENT:
            context_size, context_quant, model = _ask_raw_model()
            slots = _ask_slots()
        else:  # code and chat: raw, one model, no slot question
            context_size, context_quant, model = _ask_raw_model()

        _rule("Step 3 of 4 — read and plan")
        scans, readings = _setup_scan_rigs(rigs)
        _ask_rig_addresses(rigs)
        plans = _recommend_consented(rigs, scans, use_case, users=slots, auto=auto)
        if plans is None:
            return 0
        ctx_per_slot = context_size or _setup_context_window(plans)
        downloads = _setup_downloads(plans, scans)
        for rig, record in downloads:
            _setup_fetch(rig, record, path)

        detection = _setup_synthetic_detection(plans, window=ctx_per_slot)
        units = unit_names(detection) if wants_jev else ()
        jev = _setup_pick_unit("Jev", units) if wants_jev else None
        staged = initialize(
            path,
            force=True,
            detection=detection,
            use_case=use_case,
            jev=jev,
            deployment=deployment,
            # The launch specs are emitted beside the config it stages.
            compose_dir=path,
        )
        if not staged.written:
            raise _SetupInteractiveError("the staged setup was not written")
        _apply_setup_choices(
            path,
            detection=detection,
            fanout=fanout,
            enable_sleep_wake=enable_sleep_wake,
            ruff=ruff_on,
            users=slots if slots != 1 else None,
            unit_overrides=_unit_overrides(context_size, context_quant, model, slots),
        )
        if ruff_on:
            _install_ruff()
        print(f"Staged the setup at {staged.path}\n")
        if stop is Stop.CONFIG:
            print(
                f"Wrote the config and stopped: nothing was emitted, started "
                f"or sampled. The setup is at {path}.\n"
            )
            return 0
        rooms = _setup_rooms(path, ctx_per_slot)
        _setup_emit(path, ctx_per_slot)
        if stop is Stop.EMIT:
            print(
                f"Emitted the launch specs and stopped: nothing was started "
                f"or sampled. The setup and its specs are at {path}.\n"
            )
            return 0

        _rule("Step 4 of 4 — start and lock")
        for note in _native_notes(rigs):
            _note(note)
        if stop is Stop.START:
            _setup_start(rigs, scans, path)
            print(
                f"Started the servers and stopped: nothing was sampled or "
                f"locked. The setup is at {path}.\n"
            )
            _handoff(path)
            return 0
        serving = False
        if auto or _confirm(_start_question(rigs)):
            _setup_start(rigs, scans, path)
            serving = True
            approved, unapproved = _setup_sample(
                path, run_id, readings, rooms, auto=auto
            )
        else:
            started = "Servers" if _native_rigs(rigs) else "Containers"
            print(
                f"{started} were not started. The staged setup and its launch "
                f"specs are at {path}.\n"
            )
            approved, unapproved = _setup_unsampled(
                path, NOT_STARTED, acknowledged=None, readings=readings
            )
        decisions = staged.decisions + approved
        if decisions:
            print("What was decided, and why:")
            for decision in decisions:
                print(f"  - {decision}")
            print()
        limits = staged.limits + unapproved
        not_live = _report_limits(limits)
        if not not_live:
            _offer_path_append()
        if serving:
            _handoff(path)
        return 0
    except _SetupInteractiveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except InitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, CapabilityTableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handoff(path: Path) -> None:
    """Print and write the endpoint, key and model a custom provider points at.

    Nothing is written when the setup holds no ladder to serve. The key is the
    one mcgyvr already keeps for the unit (:mod:`mcgyvr.unitkey`), read the way
    `mcgyvr fleet key <unit>` reads it, never a second key.
    """
    from mcgyvr import handoff

    try:
        config = load_config(path)
    except ConfigError:
        return
    provider = handoff.from_config(config)
    if provider is None:
        return
    exported = handoff.write(path, provider)
    handoff.print_provider(provider, exported)


def run_menu_setup(*, auto: bool, stop: str | None) -> int:
    """The no-args menu's way into `setup`: the wizard, auto or stopped at `stop`.

    The prologue is the wizard's own (`_setup`'s retired-keys mend, then the
    wizard), so the menu's setup is the same command, not a second path. The
    menu speaks the :class:`~mcgyvr.cli.setup_stages.Stop` words as strings;
    they are read back into the enum here.
    """
    run_id = _setup_run_id()
    try:
        path = _setup_path(argparse.Namespace(path=None), run_id)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    mended = _setup_retired(path, False)
    if mended is not None:
        return mended
    return _setup_interactive(
        path,
        run_id,
        auto=auto,
        stop=Stop(stop) if stop is not None else None,
    )


NOT_STARTED = "its containers were not started, so nothing of it runs to sample"


ALL_HOSTED = "every unit in it is hosted, so there is no machine of yours to sample"


FLAGS_START_NOTHING = (
    "`mcgyvr setup` with flags stages a config from a scan and recommendation "
    "and starts no server, so nothing mcgyvr launched runs to sample (the "
    "interactive `mcgyvr setup` starts and samples them)"
)


FLAGS_STARTED_NOT_SAMPLED = (
    "`mcgyvr setup --host ... --start` started its servers, but no sample ran "
    "on them, so nothing mcgyvr measured runs to sample"
)


NO_EVIDENCE_MEANS = (
    "A lock on no evidence approves the fleet as it is written: no reading of "
    "its units' speed, card use or restarts stands behind it, so live admission "
    "holds a run only to its layout and to the rigs it was read on, and nothing "
    "alerts when a unit is slower or larger than it should be."
)


ACCEPT_UNSAMPLED = "Lock it approved on no evidence? [y/n] "


def _setup_unsampled(
    path: Path,
    why: str,
    *,
    acknowledged: bool | None,
    readings: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Report why the fleet could not be sampled, and lock it live only on an
    acknowledgement.

    The cost of a lock on no evidence is printed before the question is asked,
    and `acknowledged` skips the question when the flag already answered it. An
    unacknowledged fleet is neither locked nor made live, which is answered as a
    limit saying so.
    """
    print(f"The fleet could not be sampled: {why}.")
    print(NO_EVIDENCE_MEANS)
    print()
    if acknowledged is None:
        acknowledged = _confirm(ACCEPT_UNSAMPLED)
    if not acknowledged:
        return (), (
            "The fleet was not locked or made live: it could not be sampled "
            f"({why}), and a fleet no sample ran on is locked on no evidence "
            "only once you acknowledge that. Re-run `mcgyvr setup` with "
            "`--accept-unsampled` to lock it.",
        )
    return _own_fleet_live(path, readings)


def _setup_rooms(path: Path, ctx_per_slot: int) -> dict[str, int]:
    """Size the room each rung gets in MiB, from the staged config's own unit fits.

    The config is loaded and sized against fresh scans of its hosts at the
    context window given. A load, sizing or capability failure is raised as the
    step's error, since a fleet that cannot be sized cannot be laid out.
    """
    import math

    try:
        config = load_config(path)
        scans = resolve_hosts(recorded_scans(), _hosts_wanted(config).values())
        units = units_for(
            config, scans, specs=_model_specs(), ctx_per_slot=ctx_per_slot
        )
    except (ConfigError, UnitError, CapabilityTableError) as exc:
        raise _SetupInteractiveError(
            f"the staged setup cannot be sized: {exc}"
        ) from exc
    rooms: dict[str, int] = {}
    for unit in units:
        mib = math.ceil((unit.fit.vram_gb + unit.fit.headroom_gb) * 1024)
        for rung in unit.rungs:
            rooms[rung] = mib
    return rooms


def _setup_run_contract(argv: list[str]) -> int:
    """Run a mcgyvr command line on the sampler's behalf and answer its exit code."""
    from mcgyvr.cli.dispatcher import main

    return main(argv)


def _setup_sample(
    path: Path,
    run_id: str,
    readings: Mapping[str, Mapping[str, Any]],
    rooms: Mapping[str, int],
    *,
    auto: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Lay out each rig, sample the staged fleet, stamp it, and lock a green one.

    Each rig is identified from the reading already taken, so a fleet is laid
    out only over rigs that were read. A sample that fails to run, or a stamp
    that comes back red, is answered as a limit and nothing is locked. A green
    stamp is kept in its folder, and is locked and named live only on the user's
    yes.
    """
    from mcgyvr.fleet import sampler
    from mcgyvr.fleet.lock import OWN_FLEET, write_from_stamp
    from mcgyvr.fleet.promote import PromoteRefusedError, promote
    from mcgyvr.fleet.stamp import SETUP_DIR, stamp

    try:
        rig_ids = {
            rig: _rig_id(rig, readings[rig] if rig in readings else _read_rig(rig))
            for rig in _rigs(path)
        }
        sampler.lay_out(path, rig_ids, rooms)
        ran = sampler.run(path, run_contract=_setup_run_contract)
    except (sampler.SamplerError, PromoteRefusedError) as exc:
        return (), (f"The fleet was not sampled, so nothing was locked: {exc}.",)
    for failed in ran.failed:
        print(f"warning: the door's {failed}", file=sys.stderr)
    stamped = stamp(ran.sample, run_id=run_id)
    for line in stamped.lines():
        print(line)
    print()
    if stamped.folder is None:
        return (), (
            "The sample was red, so the fleet was not locked or made live: "
            + "; ".join(stamped.why),
        )
    folder = stamped.folder
    if not auto and not _confirm("Lock the fleet and name it live? [y/n] "):
        return (), (
            f"The fleet was stamped and not locked: the stamp is kept at "
            f"{folder}, and a later `mcgyvr setup` samples and locks again.",
        )

    def lock_and_promote() -> Path:
        write_from_stamp(folder)
        return promote(folder, folder / SETUP_DIR, OWN_FLEET)

    return _own_fleet_switch(lock_and_promote, tuple(rig_ids), sampled=True)


def _setup_run_id() -> str:
    """Answer an id for this run: the UTC time it started, then four random bytes."""
    import secrets
    from datetime import UTC, datetime

    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(4)}"


def _setup_path(args: argparse.Namespace, run_id: str) -> Path:
    """Answer where this run writes its config.

    A named path is made absolute so the door, emit and the sampler all reach
    one location, and it is read through `named_config_path` when no path is
    given. With no path at all the run gets a staging folder of its own, never
    the working directory and never a live fleet folder.
    """
    from mcgyvr.fleet.roots import staging_dir

    named = Path(args.path) if args.path else named_config_path()
    # An absolute path is what every later step is handed: the door's env, emit's
    # in-place write and the sampler all name this same file.
    return named.absolute() if named is not None else staging_dir(run_id)


def _setup_retired(path: Path, force: bool) -> int | None:
    """Delete or name the retired keys a setup from before carries, or None.

    A `policy.yaml` that `mcgyvr setup` wrote before the ladder manager and
    chat/agent sessions were removed carries keys the loader now refuses
    (`fleet.files.RETIRED_POLICY_KEYS`), so the setup no longer loads. At a
    terminal their lines are shown and deleted on a yes; without one they are
    printed with their line numbers for a person to delete, and the run fails.
    None means there is nothing to mend here: no setup, none of those keys, or
    `--force`, which rewrites the whole setup anyway.
    """
    if force:
        return None
    policy = path / POLICY_FILENAME if path.is_dir() else path
    try:
        text = policy.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # No setup here, or none this can read: the steps after say which.
        return None
    spans = retired_policy_lines(text)
    if not spans:
        return None
    shown = "\n".join(
        f"  lines {span.first}-{span.last} (`{span.key}`):\n"
        + "\n".join(
            f"    {span.first + offset:>4} | {line}"
            for offset, line in enumerate(span.text)
        )
        for span in spans
    )
    said = f"{policy} carries keys this version of mcgyvr no longer reads:\n{shown}"
    if not _stdin_isatty():
        print(
            f"error: {said}\nDelete these lines, or run `mcgyvr setup` at a "
            f"terminal to have them deleted.",
            file=sys.stderr,
        )
        return 1
    print(said)
    if not _confirm(f"Delete these lines from {policy}? [y/n] "):
        print(
            f"Left {policy} as it is: the setup does not load until they are deleted.",
            file=sys.stderr,
        )
        return 1
    policy.write_text(without_retired_lines(text), encoding="utf-8")
    print(f"Deleted them from {policy}.")
    return 0


def _setup(args: argparse.Namespace) -> int:
    run_id = _setup_run_id()
    try:
        path = _setup_path(args, run_id)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    mended = _setup_retired(path, args.force)
    if mended is not None:
        return mended
    stated = _setup_rig_addresses(args.rig_address)
    if stated is not None:
        return stated
    if _setup_is_interactive(args):
        return _setup_interactive(path, run_id, deployment=args.deployment)
    refused = _use_case_refused(args.use_case)
    if refused is not None:
        print(f"error: --use-case `{args.use_case}` {refused}", file=sys.stderr)
        return 1
    if args.jev is not None and args.use_case in RAW_USE_CASES:
        print(
            f"error: --jev dedicates a unit to the typed decisions inside "
            f"mcgyvr-code's stages; use case `{args.use_case}` serves its model raw "
            f"and asks none.",
            file=sys.stderr,
        )
        return 1
    if args.start and not args.host:
        print(
            "error: --start starts the servers the scan + recommendation path "
            "wrote; pass --host to name the rig(s) to start. Without --host "
            "setup binds servers already answering, so there is nothing mcgyvr "
            "launched to start.",
            file=sys.stderr,
        )
        return 1
    # The flag path parses each --api spec before anything is written, so a
    # malformed spec is reported first. With --host it then scans the named rigs
    # and recommends a model and engine from their hardware, folding the backend
    # into the recommendation; without --host it hands the local sweep, the
    # priority and the named use case to initialize as before.
    try:
        api_units = tuple(parse_api_unit(spec) for spec in (args.api or ()))
    except ApiSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    use_case = args.use_case or MCGYVR_CODE
    readings: Mapping[str, Mapping[str, Any]] | None = None
    scans: Mapping[str, Scan] | None = None
    ctx_per_slot: int | None = None
    try:
        if args.host:
            if args.priority is not None:
                raise _SetupInteractiveError(
                    "--priority cannot be combined with --host: the scan + "
                    "recommendation path has no running backend for the Jev "
                    "decision to run on. Drop --priority, or run `mcgyvr "
                    "setup` at a terminal."
                )
            scans, readings = _setup_scan_rigs(tuple(args.host))
            plans = _setup_placements(tuple(args.host), scans, use_case)
            ctx_per_slot = _setup_context_window(plans)
            detection = _setup_synthetic_detection(plans, window=ctx_per_slot)
            result = initialize(
                path,
                force=args.force,
                detection=detection,
                api_units=api_units,
                use_case=use_case,
                deployment=args.deployment,
                jev=args.jev,
                compose_dir=path,
            )
        else:
            result = initialize(
                path,
                force=args.force,
                hosts=(),
                api_units=api_units,
                priority=args.priority,
                use_case=use_case,
                deployment=args.deployment,
                jev=args.jev,
                compose_dir=path,
            )
    except _SetupInteractiveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except InitError as exc:
        # initialize refuses a setup its loader would reject, and says why.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, CapabilityTableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.created:
        print(f"Staged the setup at {result.path}\n")
    elif result.written:
        print(f"Overwrote {result.path} (--force)\n")
    else:
        print(f"{result.path} already exists — nothing was changed.\n")

    # With --start the written setup is emitted and its servers are started
    # through the door, which is the flag's consent; without it nothing is
    # started, so nothing runs to sample. Either way a flag-run setup samples
    # nothing, and a config that was written is locked on no evidence only once
    # it is acknowledged. A config left untouched binds nothing new, so it goes
    # through neither.
    started = False
    if result.written and args.start and scans is not None and ctx_per_slot is not None:
        _setup_emit(result.path, ctx_per_slot)
        _setup_start(tuple(args.host), scans, result.path)
        started = True
    approved, unapproved = (
        _setup_unsampled(
            result.path,
            _why_unsampled(result.path, started=started),
            acknowledged=args.accept_unsampled,
            readings=readings,
        )
        if result.written
        else ((), ())
    )
    decisions = result.decisions + approved
    if decisions:
        print("What was decided, and why:")
        for decision in decisions:
            print(f"  - {decision}")
        print()

    if not result.written:
        if result.deltas:
            print("Re-running with --force would change:")
            for delta in result.deltas:
                print(f"  - {delta}")
            print(
                "\nYour edits are kept. Pass --force to accept the proposal "
                "above, or leave the file as it is."
            )
        else:
            print("The proposal matches the file on disk exactly.")
        print()

    limits = result.limits + unapproved
    _report_limits(limits)
    return 0


def _use_case_refused(name: str | None) -> str | None:
    """Answer why `--use-case` refuses `name`, or None when setup offers it.

    The parser takes any name, so a name the offered ones do not hold is refused
    here, naming them.
    """
    offered = _setup_use_cases()
    if name is None or name in offered:
        return None
    retired = RETIRED_USE_CASES.get(name)
    if retired is not None:
        return f"is refused: {retired}."
    return f"is not a use case; setup offers {_spoken_or(offered)}."


def _why_unsampled(setup: Path, *, started: bool = False) -> str:
    """Answer why the flag-run setup was not sampled, in the words the user is shown.

    A setup that names rigs was never started, or was started by `--start` and
    not sampled; one with no rigs has no machine of the user's to sample.
    """
    if not _rigs(setup):
        return ALL_HOSTED
    return FLAGS_STARTED_NOT_SAMPLED if started else FLAGS_START_NOTHING


def _own_fleet_live(
    setup: Path, readings: Mapping[str, Mapping[str, Any]] | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Lock the setup on no evidence and make it live, answering decisions and limits.

    Rigs without a reading handed in are read here. The lock is written into a
    scratch folder, acknowledged on the caller's behalf, and promoted from that
    folder; a lock or promotion that is refused is answered as a limit.
    """
    import tempfile

    from mcgyvr.fleet.lock import OWN_FLEET, LockRefusedError, write_unsampled
    from mcgyvr.fleet.promote import PromoteRefusedError, promote
    from mcgyvr.fleet.stamp import SETUP_DIR

    rigs = _rigs(setup)
    try:
        held = readings or {}
        rig_ids = {
            rig: _rig_id(rig, held[rig] if rig in held else _read_rig(rig))
            for rig in rigs
        }
    except (LockRefusedError, PromoteRefusedError) as exc:
        return (), (f"No fleet was made live: {exc}.",)

    def lock_and_promote() -> Path:
        with tempfile.TemporaryDirectory(prefix="mcgyvr-own-") as scratch:
            dev = Path(scratch)
            write_unsampled(dev, setup, rigs=rig_ids, acknowledged=True)
            return promote(dev, dev / SETUP_DIR, OWN_FLEET)

    return _own_fleet_switch(lock_and_promote, rigs, sampled=False)


def _own_fleet_switch(
    lock_and_promote: Callable[[], Path], rigs: Sequence[str], *, sampled: bool
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Make the locked fleet live, unless another fleet holds live and is not mcgyvr's.

    A fleet that is live and not mcgyvr's is left live, and the decisions say it
    stays so. A lock or promotion refused when no fleet is live is answered as a
    limit that also names what a run needs; refused while an earlier own fleet is
    live, that fleet stays live and the limit says so. Otherwise the switch is
    answered as a decision naming the folder, the pointer naming it live, and
    where its rig units sit.
    """
    from mcgyvr.fleet.lock import LockRefusedError, is_own
    from mcgyvr.fleet.promote import PromoteRefusedError, use
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet

    refused = "A live run is refused until a fleet is live (`mcgyvr fleet use`)."
    try:
        current = live_fleet()
    except LiveFleetError as exc:
        return (), (f"No fleet was made live: {exc}. {refused}",)
    if current is not None and not is_own(current):
        return (
            f"{current} is live, and stays so: your own fleet was not approved "
            "over it (`mcgyvr fleet use` switches).",
        ), ()
    try:
        folder = lock_and_promote()
        switch = use(folder.name)
    except (LockRefusedError, PromoteRefusedError) as exc:
        if current is None:
            return (), (f"No fleet was made live: {exc}. {refused}",)
        return (), (
            f"Your own fleet was not approved again: {exc}. {current}, approved "
            "before, stays live, and a run that dispatches to an unapproved "
            "machine is refused.",
        )
    how = "on its sample's evidence" if sampled else "on no evidence"
    if rigs:
        where = (
            ". Its rig units sit on "
            + ", ".join(rigs)
            + ", laid out and approved by a read of each."
        )
    else:
        where = (
            ". Every unit in it is hosted, so it lays out no rig and live "
            "admission reads none."
        )
    return (
        f"Approved your own fleet for live runs {how}: {folder}, named in "
        f"{switch.pointer}"
        + (f" in place of {current}" if current is not None else "")
        + where,
    ), ()


def _rigs(setup: Path) -> tuple[str, ...]:
    """Answer the rigs the setup's fleet file names, sorted and without repeats.

    A missing or malformed fleet file answers nothing, since a setup that names
    no rig binds no machine.
    """

    try:
        fleet = load_fleet((setup / FLEET_FILENAME).read_text(encoding="utf-8"))
    except (OSError, FleetFileError):
        return ()
    rigs = {
        str(body.get("rig"))
        for body in (fleet.get("units") or {}).values()
        if "rig" in body
    }
    return tuple(sorted(rigs))


def _read_rig(rig: str) -> dict[str, Any]:
    """Read one rig over local or ssh reach, save its rig file, and answer the reading.

    A rig that does not answer, or that answers but cannot run the reader, and a
    rig file that cannot be written, are each raised as a promote refusal
    naming the rig.
    """
    from mcgyvr.detect import is_local_host
    from mcgyvr.fleet.promote import PromoteRefusedError
    from mcgyvr.serving import rigfile

    reach = (
        scan_module.Reach.local() if is_local_host(rig) else scan_module.Reach.ssh(rig)
    )
    try:
        reading = scan_module.read_over(reach)
    except scan_module.Unreachable as exc:
        raise PromoteRefusedError(f"{rig}: did not answer ssh ({exc})") from exc
    except (scan_module.ScannerMissing, scan_module.ScanFailed) as exc:
        raise PromoteRefusedError(
            f"{rig}: answered ssh but the reader did not run there (it needs "
            f"python3): {exc}"
        ) from exc
    try:
        rigfile.save(rig, reading)
    except (OSError, rigfile.RigFileError) as exc:
        raise PromoteRefusedError(
            f"{rig}: its rig file could not be written: {exc}"
        ) from exc
    return reading


def _rig_id(rig: str, reading: Mapping[str, Any]) -> str:
    """Answer the id a reading yields, or a promote refusal naming the rig when none."""
    from mcgyvr.fleet import ids
    from mcgyvr.fleet.promote import PromoteRefusedError

    try:
        return ids.rig_id(reading)
    except ValueError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the `setup` subcommand and its flags to the CLI's parser."""
    setup = sub.add_parser(
        "setup",
        help=(
            "read each rig, plan, stage, start and sample a fleet, and lock it "
            "live on your yes"
        ),
    )
    setup.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="RIG",
        help=(
            "scan a rig over ssh (or this machine for localhost) and recommend "
            "a model and engine from its hardware (repeatable); setup writes "
            "the recommended config and starts nothing unless --start"
        ),
    )
    setup.add_argument(
        "--rig-address",
        action="append",
        default=[],
        metavar="RIG=ADDRESS",
        help=(
            "state the IPv4 address a rig's units are reached at, recorded in "
            "its rig file beside the scan (repeatable; for a rig whose scan "
            "recorded no address, so a unit addressed by it still finds the rig)"
        ),
    )
    setup.add_argument(
        "--api",
        action="append",
        default=[],
        metavar="SPEC",
        help=(
            "bind a hosted API unit, which needs no GPU and no local backend, "
            "as `model=<id>,address=<url>,api_key_env=<VAR>` (repeatable), "
            "optionally `,output_tokens=<N>` for the room its replies are "
            f"given (default {API_OUTPUT_TOKENS}: a reasoning model spends it "
            "thinking before it writes). api_key_env is the NAME of the environment "
            "variable holding your key, never the key itself"
        ),
    )
    setup.add_argument(
        "path",
        nargs="?",
        default=None,
        action=_OneSetup,
        help=f"where to write (default: {INIT_DEFAULT_HELP})",
    )
    # --config writes to the same destination as the positional PATH, spelled
    # the way the other subcommands spell it; _OneSetup refuses both at once.
    setup.add_argument(
        "--config",
        dest="path",
        default=argparse.SUPPRESS,
        type=_named_path,
        metavar="PATH",
        action=_OneSetup,
        help="the same as PATH: the setup to write",
    )
    setup.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config, discarding hand edits",
    )
    setup.add_argument(
        "--priority",
        default=None,
        choices=PRIORITIES,
        metavar="PRIORITY",
        help=(
            "compose the ladder for this priority (throughput, quality or "
            "cost) instead of writing the default ladder. The decision runs on "
            "the first detected backend; every number in the file stays "
            "measured or the schema's, never the model's"
        ),
    )
    setup.add_argument(
        "--use-case",
        default=None,
        metavar="USE_CASE",
        help=(
            "which use case this install serves: mcgyvr-code (mcgyvr between "
            "the model and you: the gate, repair, verifier, ladder and the "
            "rest, each switchable), or code, chat or agent (the model served "
            "raw); default: mcgyvr-code"
        ),
    )
    setup.add_argument(
        "--deployment",
        default=None,
        choices=DEPLOYMENT_FIELD.choices,
        metavar="MODEL",
        help=(
            "how mcgyvr is run: hybrid (an API-tier session agent drives it) or "
            "local-only (mcgyvr is the backend and provisions a local "
            f"proposer for mcgyvr-code); default: {DEPLOYMENT_FIELD.default}"
        ),
    )
    setup.add_argument(
        "--jev",
        default=None,
        metavar="UNIT",
        help=(
            "dedicate VRAM to a Jev unit: the written unit every typed decision "
            "asks, never slept or woken (an opt-in; no model is picked for you)"
        ),
    )
    setup.add_argument(
        "--start",
        action="store_true",
        help=(
            "after --host scans and recommends a config, emit its launch "
            "specs and start the recommended servers through the door; the "
            "flag is your consent to start. Without it nothing is started"
        ),
    )
    setup.add_argument(
        "--accept-unsampled",
        action="store_true",
        help=(
            "lock the fleet setup stages approved on no evidence, and name it "
            "live: a flag-run setup samples nothing (with or without --start), "
            "so nothing measured stands behind the lock. Without it nothing "
            "is locked, and the limits say why"
        ),
    )
    setup.set_defaults(func=_setup)
