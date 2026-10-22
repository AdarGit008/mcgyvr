"""`mcgyvr setup`: stage a fleet config, then start, sample and lock it live.

Two ways in. With flags the command stages a config from named hosts, hosted API
units and a priority, binds what already answers and starts nothing. Run with no
flags on a terminal, it is the wizard: it asks for the rigs, the use case and
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
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.capability import (
    CapabilityTableError,
)
from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    FLEET_FILENAME,
    POLICY_FILENAME,
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
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs
from mcgyvr.serving.rigfile import recorded_scans, resolve_hosts


def _setup_priority(args: argparse.Namespace) -> str | None:
    """Answer the priority to compose for, mapping a deprecated --profile onto one.

    Answers None when no priority is asked for, which writes the default ladder.
    A --profile given beside --priority is reported and ignored; so is a word
    that names no priority, since it is not a ladder to compose.
    """
    priority: str | None = args.priority
    if args.profile is None:
        return priority
    head = (
        "warning: `mcgyvr setup --profile` is deprecated and will be removed "
        "in the release after next"
    )
    word = str(args.profile).strip().lower()
    names = "|".join(PRIORITIES)
    if priority is not None:
        print(
            f"{head}; --profile {args.profile!r} is ignored because "
            f"`--priority {priority}` was given",
            file=sys.stderr,
        )
        return priority
    if word in PRIORITIES:
        print(
            f"{head}; use `--priority {word}`",
            file=sys.stderr,
        )
        return word
    print(
        f"{head}; --profile {args.profile!r} names no priority ({names}), so it "
        "is ignored and the default ladder is written",
        file=sys.stderr,
    )
    return None


class _SetupInteractiveError(Exception):
    """A wizard step could not finish; its message is the error setup reports."""


def _stdin_isatty() -> bool:
    """Answer whether stdin is a terminal, which the wizard needs to ask anything."""
    return sys.stdin.isatty()


def _setup_is_interactive(args: argparse.Namespace) -> bool:
    """Answer whether this run is the wizard: a terminal, and no flag that
    answers its questions.

    Any flag that names a host, a rig's address, an API unit, a use case or a
    Jev unit, or that forces the write or accepts an unsampled lock, makes the
    run the flag path instead.
    """
    if not _stdin_isatty():
        return False
    return not (
        bool(args.host)
        or bool(args.rig_address)
        or bool(args.api)
        or args.force
        or args.priority is not None
        or args.profile is not None
        or args.use_case is not None
        or args.deployment is not None
        or args.jev is not None
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


def _setup_choose(question: str, choices: Sequence[str], what: str) -> str:
    """Ask for one of `choices`, taking the first as the default on an empty answer.

    An answer outside the choices is reported and asked for again, up to
    `_SETUP_TRIES` times, after which the step fails naming what it offers.
    """
    said = ""
    for _ in range(_SETUP_TRIES):
        said = _ask(question)
        if not said:
            return choices[0]
        if said in choices:
            return said
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
    """Answer the use-case names on offer, coding first because it is the default.

    Only the catalog's use cases a config accepts are offered. The catalog is
    read here rather than imported at module load, so the setup command does not
    pull it in for runs that never ask.
    """
    from mcgyvr.catalog import catalog
    from mcgyvr.fleet.sample import CODING_USE_CASE

    names = tuple(u.name for u in catalog().use_cases if u.name in USE_CASES)
    return (CODING_USE_CASE, *(n for n in names if n != CODING_USE_CASE))


_USE_CASE_LETTERS = ("d", "c", "a")


def _ask_setup_use_case() -> str:
    """Ask for a use case by single letter and answer the name that letter stands for.

    The letters run over the offered names in order, the first marked as the
    default, so the default is an empty answer.
    """
    names = _setup_use_cases()
    letters = _USE_CASE_LETTERS[: len(names)]
    by_letter = dict(zip(letters, names, strict=False))
    options = ", ".join(
        f"[{letter}] {name}" + (" (default)" if index == 0 else "")
        for index, (letter, name) in enumerate(zip(letters, names, strict=False))
    )
    return by_letter[
        _setup_choose(f"Use case — {options}: ", letters, "a use-case letter")
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


_PATH_EXPORT = 'export PATH="$HOME/.local/bin:$PATH"'


def _shell_rc(shell: str | None, home: Path | None = None) -> Path | None:
    """Answer the rc file a shell reads at startup, or None for no or unknown shell.

    bash, zsh, sh/dash and fish each have their file under `home`, which
    defaults to the user's home directory.
    """
    if not shell:
        return None
    base = os.path.basename(shell)
    home = home if home is not None else Path.home()
    if base == "bash":
        return home / ".bashrc"
    if base == "zsh":
        return home / ".zshrc"
    if base in ("sh", "dash"):
        return home / ".profile"
    if base == "fish":
        return home / ".config" / "fish" / "config.fish"
    return None


def _has_local_bin_path(text: str) -> bool:
    """Answer whether any line of the text already names ~/.local/bin on PATH."""
    return any(".local/bin" in line and "PATH" in line for line in text.splitlines())


def _offer_path_append(
    prompt: Callable[[str], str] = input,
    shell: str | None = None,
    home: Path | None = None,
) -> Path | None:
    """Offer to put ~/.local/bin on the shell's PATH, answering the file or None.

    The shell defaults to `$SHELL`. Nothing is asked when the shell is unknown
    or the rc file already has that directory on PATH. A yes appends one export
    line, creating the file's directory when it is missing; a file that cannot
    be written is reported and answered as None.
    """
    if shell is None:
        shell = os.environ.get("SHELL")
    base = home if home is not None else Path.home()
    rc = _shell_rc(shell, base)
    if rc is None:
        return None
    try:
        text = rc.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if _has_local_bin_path(text):
        return None
    shown = "~/" + str(rc.relative_to(base))
    question = f"Add ~/.local/bin to your shell PATH in {shown}? [y/n] "
    if not _confirm(question, prompt):
        return None
    try:
        rc.parent.mkdir(parents=True, exist_ok=True)
        with rc.open("a", encoding="utf-8") as stream:
            stream.write(_PATH_EXPORT + "\n")
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
    rigs: Sequence[str], scans: Mapping[str, Scan], use_case: str
) -> dict[str, Mapping[str, Any]]:
    """Plan a placement for each rig from its own scan, print it, and answer the plans.

    Each rig is planned alone, as one user of the use case asked, so what it can
    serve is read off its own machine. Setup says where each plan's candidates
    came from: the Hub now, the cache of an earlier read, or the shipped
    catalog. A use case recommend does not place, a plan that recommends
    nothing, or one that carries no placement to serve, fails the step naming
    the rig.
    """
    if use_case not in recommend_module.PLACEMENT_PROFILES:
        raise _SetupInteractiveError(
            f"recommend places {', '.join(recommend_module.PLACEMENT_PROFILES)}, "
            f"not {use_case!r}"
        )
    profile = use_case
    plans: dict[str, Mapping[str, Any]] = {}
    for rig in dict.fromkeys(rigs):
        try:
            plan = recommend_module.plan(
                profile=profile,
                users=1,
                hosts=(rig,),
                premeasured={rig: scans[rig]},
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
                f"on disk. Reuse it instead of downloading? [Y/n] "
            )
            if str(answer).strip().lower() not in {"n", "no"}:
                print(f"{rig}: reusing {model_id} {quant} already on disk")
                continue
            chosen = True
        else:
            answer = prompt(
                f"Download {model_id}{' ' + quant if quant else ''} for {rig}? [y/N] "
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
    """Build the detection the wizard stages from its plans, probing no running server.

    Each placement becomes one openai-shaped backend on its rig: vllm on port
    8000, anything else as llama-server on the default port, named after the rig
    once there is more than one. A placement with no model fails the step,
    because a local checkpoint is not bootstrapped here.
    """
    from mcgyvr.detect import Backend, Detection
    from mcgyvr.serving import DEFAULT_PORT

    backends: list[Backend] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            raise _SetupInteractiveError(
                f"{rig}: its placement is a local checkpoint, and the wizard "
                "does not bootstrap from a local store yet"
            )
        engine = str(placement.get("engine") or "llama.cpp")
        kind = "vllm" if engine == "vllm" else "llama-server"
        port = 8000 if engine == "vllm" else DEFAULT_PORT
        name = f"{rig}_{kind}" if len(plans) > 1 else kind
        backends.append(
            Backend(
                name=name,
                base_url=f"http://{rig}:{port}/v1",
                api="openai",
                models=(model_id,),
                how="interactive setup",
                host=rig,
                kind=kind,
                window=window,
            )
        )
    return Detection(
        backends=tuple(backends), provenance={"backends": "interactive setup"}
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
    """Start each rig's containers from the launch spec emitted for it.

    A rig with one whole-host spec is started from that file; a rig with
    several per-model alternatives is refused, since the wizard cannot choose
    between them. The door is told where the setup lives, and an up that exits
    non-zero fails the step.
    """
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import spec_files, spec_name

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
        code = wakelib.spawn_door(
            wakelib.door_argv(
                direction="up", host=rig, compose=compose, suffix=_setup_suffix()
            ),
            env={
                **os.environ,
                # The door reads the setup to bring up from this variable, so
                # it finds the same config this run staged and emitted.
                CONFIG_PATH_ENV: str(path),
            },
        )
        if code != 0:
            raise _SetupInteractiveError(f"{rig}: serve up exited {code}")


def _setup_interactive(path: Path, run_id: str = "") -> int:
    """Run the wizard end to end and answer the exit code.

    It asks its questions, reads and plans the rigs, fetches missed weights,
    stages the config, sizes the rooms, emits launch specs, then starts and
    samples the containers when the user says so. What was decided and what was
    left unconfigured are printed at the end, along with the offer to put
    ~/.local/bin on PATH. A step's error, or a refused init, config or
    capability table, is printed and answered with 1.
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
        wants_jev = _confirm(JEV_QUESTION)
        _rule("Step 3 of 4 — read and plan")
        scans, readings = _setup_scan_rigs(rigs)
        _ask_rig_addresses(rigs)
        plans = _setup_placements(rigs, scans, use_case)
        ctx_per_slot = _setup_context_window(plans)
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
            # The launch specs are emitted beside the config it stages.
            compose_dir=path,
        )
        if not staged.written:
            raise _SetupInteractiveError("the staged setup was not written")
        print(f"Staged the setup at {staged.path}\n")
        rooms = _setup_rooms(path, ctx_per_slot)
        _setup_emit(path, ctx_per_slot)

        _rule("Step 4 of 4 — start and lock")
        if _confirm(f"Start the serving containers on {', '.join(rigs)}? [y/N] "):
            _setup_start(rigs, scans, path)
            approved, unapproved = _setup_sample(path, run_id, readings, rooms)
        else:
            print(
                "Containers were not started. The staged setup and its launch "
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


NOT_STARTED = "its containers were not started, so nothing of it runs to sample"


ALL_HOSTED = "every unit in it is hosted, so there is no machine of yours to sample"


FLAGS_START_NOTHING = (
    "`mcgyvr setup` with flags binds the servers already answering and starts "
    "none, so nothing mcgyvr launched runs to sample (the interactive `mcgyvr "
    "setup` starts and samples them)"
)


NO_EVIDENCE_MEANS = (
    "A lock on no evidence approves the fleet as it is written: no reading of "
    "its units' speed, card use or restarts stands behind it, so live admission "
    "holds a run only to its layout and to the rigs it was read on, and nothing "
    "alerts when a unit is slower or larger than it should be."
)


ACCEPT_UNSAMPLED = "Lock it approved on no evidence? [y/N] "


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
    if not _confirm("Lock the fleet and name it live? [y/N] "):
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
    if not _confirm(f"Delete these lines from {policy}? [y/N] "):
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
        return _setup_interactive(path, run_id)
    refused = _use_case_refused(args.use_case)
    if refused is not None:
        print(f"error: --use-case `{args.use_case}` {refused}", file=sys.stderr)
        return 1
    # The flag path binds what already answers: it parses each --api spec before
    # anything is written, so a malformed spec is reported first, and it hands
    # the hosts, the mapped priority and the named use case to initialize.
    try:
        api_units = tuple(parse_api_unit(spec) for spec in (args.api or ()))
    except ApiSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    priority = _setup_priority(args)
    try:
        result = initialize(
            path,
            force=args.force,
            hosts=tuple(args.host or ()),
            api_units=api_units,
            priority=priority,
            use_case=args.use_case or "coding",
            deployment=args.deployment,
            jev=args.jev,
            compose_dir=path,
        )
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

    # Nothing was started, so nothing runs to sample: a config that was written
    # is locked on no evidence only once it is acknowledged, and is otherwise
    # answered as a limit. A config left untouched binds nothing new, so it
    # goes through neither.
    approved, unapproved = (
        _setup_unsampled(
            result.path,
            _why_unsampled(result.path),
            acknowledged=args.accept_unsampled,
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
    return f"is not a use case; setup offers {_spoken_or(offered)}."


def _why_unsampled(setup: Path) -> str:
    """Answer why the flag-run setup was not sampled, in the words the user is shown.

    A setup that names rigs was never started, and one with no rigs has no
    machine of the user's to sample.
    """
    return FLAGS_START_NOTHING if _rigs(setup) else ALL_HOSTED


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
        metavar="HOST",
        help=(
            "bind backends on this machine too, by name or address "
            "(repeatable; default: localhost only)"
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
        "--profile",
        default=None,
        metavar="TEXT",
        help=(
            "deprecated, removed in the release after next: use --priority. "
            "A word naming a priority maps onto it; other text is ignored"
        ),
    )
    setup.add_argument(
        "--use-case",
        default=None,
        metavar="USE_CASE",
        help=(
            "which use case this install serves: coding (the deterministic "
            "gate), chat (raw endpoint) or agent (un-gated, from its sources); "
            "default: coding"
        ),
    )
    setup.add_argument(
        "--deployment",
        default=None,
        choices=("hybrid", "local-only"),
        metavar="MODEL",
        help=(
            "how mcgyvr is run: hybrid (an API-tier orchestrator drives it) or "
            "local-only (mcgyvr is the backend and provisions a local "
            "orchestrator for a non-chat use case); default: hybrid"
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
        "--accept-unsampled",
        action="store_true",
        help=(
            "lock the fleet setup binds approved on no evidence, and name it "
            "live: setup with flags starts no container, so no sample runs on "
            "what it binds. Without it nothing is locked, and the limits say "
            "why. Nothing measured stands behind such a lock"
        ),
    )
    setup.set_defaults(func=_setup)
