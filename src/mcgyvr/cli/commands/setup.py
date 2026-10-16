"""The `mcgyvr setup` command: interactive rig selection and fleet writing.

Only what is built is exposed.
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
    ConfigError,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.fleet.files import FleetFileError, load_fleet
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
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs, _resolve_hosts, _scans


def _setup_priority(args: argparse.Namespace) -> str | None:
    """The priority ``setup`` composes for, reading the old ``--profile``.

    ``--profile`` is deprecated: a word naming a priority maps onto it, any
    other text is ignored, and ``--priority`` wins when both are given. Each
    case says so on stderr.
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
    """The interactive wizard stopped; the message says why."""


def _stdin_isatty() -> bool:
    """Whether setup's stdin is a terminal, as a seam a test can state."""
    return sys.stdin.isatty()


def _setup_is_interactive(args: argparse.Namespace) -> bool:
    """Whether ``mcgyvr setup`` should prompt rather than write from flags.

    Interactive only with a person at the keyboard and no flag already given:
    any flag names a decision already made, and a pipe is an agent driving the
    command.
    """
    if not _stdin_isatty():
        return False
    return not (
        bool(args.host)
        or bool(args.api)
        or args.force
        or args.priority is not None
        or args.profile is not None
        or args.use_case is not None
        or args.deployment is not None
        or args.jev is not None
        or args.mcorch is not None
        or args.window is not None
        or args.session_sandbox is not None
        or args.accept_unsampled
    )


def _parse_setup_rigs(answer: str) -> tuple[str, ...]:
    """Rigs from one prompt answer: comma/space list, with ``--host`` stripped."""
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


def _ask_setup_rigs(prompt: Callable[[str], str] = input) -> tuple[str, ...]:
    """Step 1: which rigs serve this setup, defaulting to this machine."""
    answer = prompt("Which rig(s) should serve this setup? [this machine only] ")
    return _parse_setup_rigs(answer) or ("localhost",)


def _confirm(question: str, prompt: Callable[[str], str] = input) -> bool:
    """An explicit yes to one irreversible step; anything else is no."""
    return str(prompt(question)).strip().lower() in {"y", "yes"}


def _ask(question: str, prompt: Callable[[str], str] = input) -> str:
    """One typed answer, stripped; Enter is the empty answer."""
    return str(prompt(question)).strip()


_SETUP_TRIES = 3


def _setup_choose(question: str, choices: Sequence[str], what: str) -> str:
    """One of ``choices``, asked by ``question``; Enter is the first.

    An answer that is none of them is asked again, :data:`_SETUP_TRIES` times
    in all, and then setup stops naming them: nothing has been read or
    written yet, so stopping costs the user only the retype.
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
    """``a, b or c``."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def _setup_use_cases() -> tuple[str, ...]:
    """The use cases setup offers, coding (the default) first: the catalog's,
    as ``--use-case`` offers them."""
    from mcgyvr.catalog import catalog
    from mcgyvr.fleet.sample import CODING_USE_CASE

    names = tuple(u.name for u in catalog().use_cases)
    return (CODING_USE_CASE, *(n for n in names if n != CODING_USE_CASE))


def _ask_setup_use_case() -> str:
    """Which use case the setup serves (``--use-case``); Enter is coding."""
    names = _setup_use_cases()
    return _setup_choose(
        f"What is this setup for: {_spoken_or(names)}? [{names[0]}] ",
        names,
        "a use case",
    )


JEV_QUESTION = "Dedicate a unit to Jev, which answers typed decisions? [y/N] "


MCORCH_QUESTION = "Run mcorch, the local orchestrator, on a unit? [y/N] "


def _setup_pick_unit(role: str, units: Sequence[str]) -> str:
    """The unit ``role`` (``Jev`` or ``mcorch``) runs on; one unit is not asked,
    and Enter is the first of several."""
    if len(units) == 1:
        return units[0]
    verb = "is" if role == "Jev" else "runs"
    return _setup_choose(
        f"Which unit {verb} {role}: {', '.join(units)}? [{units[0]}] ",
        units,
        "a unit of this setup",
    )


def _setup_scan_rigs(
    rigs: Sequence[str],
) -> tuple[dict[str, Scan], dict[str, dict[str, Any]]]:
    """Step 2: read each rig once and record it as its rig file, so ``emit``
    sizes from it and the door's gate 2 holds ``serve up`` to it.

    Returns each rig's scan and the reading it was parsed from: the fleet is
    approved later from that same reading (:func:`_own_fleet_live`), so a rig
    is read once per setup.
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


def _setup_placements(
    rigs: Sequence[str], scans: Mapping[str, Scan]
) -> dict[str, Mapping[str, Any]]:
    """Step 3: one coding/single placement per rig, printed as JSON."""
    plans: dict[str, Mapping[str, Any]] = {}
    for rig in dict.fromkeys(rigs):
        try:
            plan = recommend_module.plan(
                profile="coding",
                users=1,
                hosts=(rig,),
                premeasured={rig: scans[rig]},
            )
        except (recommend_module.RecommendError, recommend_module.CatalogError) as exc:
            raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        sys.stdout.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        if not isinstance(plan.get("placement"), Mapping):
            raise _SetupInteractiveError(
                f"{rig}: recommend produced no placement to serve"
            )
        plans[rig] = plan
    return plans


def _setup_on_disk_match(
    scan: Scan | None, model_id: str, quant: str, size_bytes: int
) -> ModelOnDisk | None:
    """The first model already on the rig's disk matching id + quant + size.

    The scan collected the rig's own inventory, so this holds for a remote rig
    (its weights live on the rig, not on the machine running ``setup``). The id
    is matched by its last segment, its canonical local name, or the id itself
    — a GGUF's name carries no org — and the size only when it is known (a size
    of 0 is not known). The quant is enforced only when the file tags one: the
    canonical local name omits the quant, so an untagged GGUF (quant ``None``)
    is reused on the strength of its name and size rather than refused for a
    quant the file name does not state.
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
    """Step 4: ask reuse or download for every placement, gated on the answer."""
    from mcgyvr.knowledge import store as knowledge_store

    known = {record.key: record for record in knowledge_store.offline().records}
    downloads: list[tuple[str, ModelRecord]] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            # A local-store pick is already on disk; nothing is downloaded.
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
    """A RUN_ID suffix unique to this setup step (gate 5 claims the id)."""
    import os
    import time

    return f"setup-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


def _setup_fetch(rig: str, record: ModelRecord, path: Path) -> None:
    """Step 5: download one chosen model through the door's ``serve fetch``."""
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
    """The planned servers as if they were already answering.

    ``initialize`` binds only models a server lists, so the wizard writes the
    staged setup once from this detection of the plan: each planned server at
    the address its launch spec will answer on, serving ``window`` tokens per
    slot (the window ``emit`` sizes it at, which the sample reads back).
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
    """The window ``emit`` sizes the bootstrap config at, across the rigs.

    Each placement was priced at its own ``context_length``; the window handed
    to ``emit`` is the smallest of them, the one every placed model fits at.
    A placement without a readable window is refused, never guessed.
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
    """Step 6a: ``mcgyvr emit`` the launch specs for the bootstrap config."""
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
    """Step 6b: start each emitted launch spec through the door's ``serve up``."""
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
                # The product holds one unit per model: two rigs asked to
                # serve the same model collapse to one backend, and the rig
                # left out gets no launch spec. That is expected, not an
                # emit failure, so skip it rather than abort the whole
                # ``serve up``.
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
                # The config directory, not its fleet.yaml: the loader reads
                # both fleet.yaml and policy.yaml (the ladder) from it.
                CONFIG_PATH_ENV: str(path),
            },
        )
        if code != 0:
            raise _SetupInteractiveError(f"{rig}: serve up exited {code}")


def _setup_interactive(path: Path, run_id: str = "") -> int:
    """The guided ``mcgyvr setup``: prompt, then perform each step.

    ASK the rigs, the use case (:func:`_ask_setup_use_case`), and the two
    opt-ins ``--jev`` and ``--mcorch`` give (:data:`JEV_QUESTION`, and for
    ``coding`` with Jev on :data:`MCORCH_QUESTION`), all before the plan.
    READ each rig once, PLAN, then STAGE at ``path``: the setup written once
    from the plan and its launch specs emitted once, both there. START its
    units through the door on a yes, SAMPLE them (:func:`_setup_sample`), and
    lock the stamped fleet and name it live on a second yes. ``media-gen``
    has no sample yet, so nothing is started and it goes to the
    acknowledgment (:func:`_setup_unsampled`). Nothing is written anywhere
    else.
    """
    from mcgyvr.fleet.sample import CODING_USE_CASE, MEDIA_GEN, MEDIA_NOT_BUILT

    run_id = run_id or _setup_run_id()
    try:
        path.mkdir(parents=True, exist_ok=True)
        rigs = _ask_setup_rigs()
        print(f"Serving on: {', '.join(rigs)}")
        use_case = _ask_setup_use_case()
        if use_case == MEDIA_GEN:
            print(
                f"{MEDIA_GEN} cannot be sampled yet: {MEDIA_NOT_BUILT}. Setup "
                "stages it and asks before it locks it on no evidence."
            )
        wants_jev = _confirm(JEV_QUESTION)
        # mcorch asks the Jev unit every bounded question (`--mcorch` needs
        # `--jev`), so it is offered only with Jev on.
        wants_mcorch = (
            use_case == CODING_USE_CASE and wants_jev and _confirm(MCORCH_QUESTION)
        )
        scans, readings = _setup_scan_rigs(rigs)
        plans = _setup_placements(rigs, scans)
        ctx_per_slot = _setup_context_window(plans)
        downloads = _setup_downloads(plans, scans)
        for rig, record in downloads:
            _setup_fetch(rig, record, path)

        detection = _setup_synthetic_detection(plans, window=ctx_per_slot)
        units = unit_names(detection) if wants_jev else ()
        jev = _setup_pick_unit("Jev", units) if wants_jev else None
        mcorch = _setup_pick_unit("mcorch", units) if wants_mcorch else None
        staged = initialize(
            path,
            force=True,
            detection=detection,
            use_case=use_case,
            jev=jev,
            mcorch=mcorch,
            # The window each slot is launched at, which the sample reads back.
            window=ctx_per_slot if mcorch is not None else None,
            # Auto-wake on: the launch specs are emitted here and kept.
            compose_dir=path,
        )
        if not staged.written:
            raise _SetupInteractiveError("the staged setup was not written")
        print(f"Staged the setup at {staged.path}\n")
        rooms = _setup_rooms(path, ctx_per_slot)
        _setup_emit(path, ctx_per_slot)

        if use_case == MEDIA_GEN:
            approved, unapproved = _setup_unsampled(
                path, MEDIA_NOT_BUILT, acknowledged=None, readings=readings
            )
        elif _confirm(f"Start the serving containers on {', '.join(rigs)}? [y/N] "):
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
        if limits:
            print("What is NOT configured, and what that costs:")
            for limit in limits:
                print(f"  - {limit}")
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
    """Lock the staged setup at ``path``, which could not be sampled for
    ``why``, on no evidence -- only once the user acknowledges it.

    Says why it could not be sampled and what a lock on no evidence means.
    ``acknowledged`` is the flag path's ``--accept-unsampled``; ``None`` asks
    (:data:`ACCEPT_UNSAMPLED`). Unacknowledged, nothing is locked and the
    limit says how to lock it.
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
    """The card room, MiB, each unit of the staged setup at ``path`` is sized at.

    Sized as ``emit`` sizes it, from the same rig files and table: the card
    figure its fit was judged on, and the headroom held back beside it. The
    lock holds each unit's card peak in the sample to this room.
    """
    import math

    try:
        config = load_config(path)
        scans = _resolve_hosts(_scans(), _hosts_wanted(config).values())
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
    """``mcgyvr run`` with ``argv``, in this process: the sample task's run."""
    from mcgyvr.cli.dispatcher import main

    return main(argv)


def _setup_sample(
    path: Path,
    run_id: str,
    readings: Mapping[str, Mapping[str, Any]],
    rooms: Mapping[str, int],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """SAMPLE the started staged setup at ``path``, STAMP it, and LOCK it live
    on the user's yes; ``(decisions, limits)`` saying what was done, or why not.

    The setup is laid out as the user's own fleet, each rig pinned to the id
    the read step named (:func:`mcgyvr.fleet.sampler.lay_out`), sampled through
    the door (:func:`mcgyvr.fleet.sampler.run`) and judged and stamped
    (:func:`mcgyvr.fleet.stamp.stamp`, under ``run_id``). A red sample is never
    locked: its reasons are printed. A green one is locked from its stamp
    (:func:`mcgyvr.fleet.lock.write_from_stamp`), promoted and named live
    (:func:`_own_fleet_switch`).
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
    """A name for one setup run: when it started, and 8 hex digits of its own."""
    import secrets
    from datetime import UTC, datetime

    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(4)}"


def _setup_path(args: argparse.Namespace, run_id: str) -> Path:
    """Where this setup run stages: ``PATH`` (or ``--config``) when named, else
    ``$MCGYVR_CONFIG`` when set, else ``<data folder>/setup/<run_id>/``.

    Never the working directory, and never a live fleet folder: those are
    written only when a fleet is promoted
    (:func:`mcgyvr.fleet.promote.promote`).
    """
    from mcgyvr.fleet.roots import staging_dir

    named = Path(args.path) if args.path else named_config_path()
    # Absolute: the staged folder is written into the setup as the folder its
    # launch specs are kept in (`serving.compose_dir`), read from anywhere.
    return named.absolute() if named is not None else staging_dir(run_id)


def _setup(args: argparse.Namespace) -> int:
    run_id = _setup_run_id()
    try:
        path = _setup_path(args, run_id)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if _setup_is_interactive(args):
        return _setup_interactive(path, run_id)
    # Parsed before anything is detected: a mistyped `--api` is the operator's
    # to fix, and making them wait out a network sweep to hear about it is
    # spending their time to tell them something already known.
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
            mcorch=args.mcorch,
            window=args.window,
            session_sandbox=args.session_sandbox,
            compose_dir=path,
        )
    except InitError as exc:
        # Loud on purpose: nothing was written, and the message says why.
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

    # What setup wrote is the user's own fleet. The flags start nothing, so
    # nothing of it is sampled: it is locked on no evidence, and only with
    # `--accept-unsampled`. A setup run that did not write is not one it
    # bound, so it locks nothing.
    approved, unapproved = (
        _setup_unsampled(
            result.path,
            _why_unsampled(result.path, args.use_case or "coding"),
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
    if limits:
        print("What is NOT configured, and what that costs:")
        for limit in limits:
            print(f"  - {limit}")
    return 0


def _why_unsampled(setup: Path, use_case: str) -> str:
    """Why the flag path's staged setup at ``setup`` is not sampled."""
    from mcgyvr.fleet.sample import MEDIA_GEN, MEDIA_NOT_BUILT

    if use_case == MEDIA_GEN:
        return MEDIA_NOT_BUILT
    return FLAGS_START_NOTHING if _rigs(setup) else ALL_HOSTED


def _own_fleet_live(
    setup: Path, readings: Mapping[str, Mapping[str, Any]] | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Lock the setup at ``setup`` as the user's own fleet on no evidence and
    name it live; ``(decisions, limits)`` saying what was done, or why not.

    For a fleet no sample ran on, once the user has acknowledged that: locked
    on no evidence (:func:`mcgyvr.fleet.lock.write_unsampled`), promoted and
    named live (:func:`_own_fleet_switch`). Every rig the setup lays a unit on
    is read first -- the local machine without ssh, a remote one over ssh, or
    by the reading ``readings`` already holds for it -- and the fleet is laid
    out with each of them, named by the rig id its reading names. The lock is
    written into a dev root of its own that is removed once the folder is
    promoted: the folder holds all of it.
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
    """Lock and promote the user's own fleet with ``lock_and_promote``, and name
    the folder it promoted live; ``(decisions, limits)``.

    With the user's own fleet already live, the new folder is named in its
    place, and the old one is kept. Any other live fleet is never replaced
    (``mcgyvr fleet use`` switches), and then nothing is locked.
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
    """The rigs the setup init wrote lays units on, in sorted order.

    A machine of the user's is approved only by a read of it (:func:`_read_rig`):
    the local machine without ssh, a remote one over ssh. A hosted unit lays
    out no rig, so it names none.
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
    """Read ``rig`` once with the one reader and write its rig file; return the
    reading.

    The machine mcgyvr runs on is read directly, no ssh; a remote one over the
    one sanctioned read of a rig from outside the door,
    :func:`mcgyvr.serving.gatelib.ssh_read_only`, which ships the reader as
    one read-only line (``echo <base64> | base64 -d | python3 -I -B -``). Either
    way the reading is the door's own, so the rig file it writes reads the same
    when the door's gate 2 reads the rig again — which is why ``serve up`` on a
    rig set up here finds the rig file it asks for. A rig that cannot be read,
    or whose rig file will not write, is a refusal, not a traceback.
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
    """The rig id ``rig``'s reading names (:func:`mcgyvr.fleet.ids.rig_id`), the
    one the lock pins, or a refusal naming what was not read."""
    from mcgyvr.fleet import ids
    from mcgyvr.fleet.promote import PromoteRefusedError

    try:
        return ids.rig_id(reading)
    except ValueError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `setup` command."""
    use_case_names = _setup_use_cases()

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
    # The setup it writes, and the one it reads first to keep hand edits. Its
    # default chain is its own (INIT_DEFAULT_HELP): never the live fleet.
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
        choices=use_case_names,
        metavar="USE_CASE",
        help=(
            "which use case this install serves: coding (the deterministic "
            "gate), chat (raw endpoint), agent (un-gated, from its sources) or "
            "media-gen (media_valid + safety + ASR-WER); default: coding"
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
        "--mcorch",
        default=None,
        metavar="UNIT",
        help=(
            "enable mcorch on a written unit: the conversational agent a harness "
            "points at (`mcgyvr mcorch serve`); needs --jev and --window, and "
            "writes orchestrator.type mcorch, authoring direct, deployment "
            "local-only"
        ),
    )
    setup.add_argument(
        "--window",
        default=None,
        type=int,
        metavar="TOKENS",
        help=(
            "with --mcorch: the tokens the agent's unit serves in one request, "
            "read back off the running process"
        ),
    )
    setup.add_argument(
        "--session-sandbox",
        default=None,
        choices=("tempdir", "docker"),
        metavar="MODE",
        help=(
            "the sandbox a chat or agent run gets when it runs no command, "
            "written as `sandbox.sessions`: tempdir (the default: no container "
            "is built or started, and Docker is not needed) or docker (opt in "
            "to a task container, as code and media get)"
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
