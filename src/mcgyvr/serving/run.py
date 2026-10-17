#
""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.fleet.roots import RIGS_SHOWN
from mcgyvr.serving import gatelib
from mcgyvr.serving.gatelib import DOOR_MODULE

#
#
#
HERE = Path(__file__).resolve().parent
GATE_SCRIPTS = HERE / "gate-scripts"
#
BIN = GATE_SCRIPTS / "bin"
SHIMS = ("docker", "ssh")
#
#
#
#es
#
#
#
#
#
#
#
#
READERS = (
    HERE / "rigscan.py",
    GATE_SCRIPTS / "rig-units.sh",
    HERE / "linktime.py",
    HERE / "fetcher.py",
)
#
#
#
#
#
#
#
SERVE_STEPS = {
    "up": GATE_SCRIPTS / "serve-up.py",
    "down": GATE_SCRIPTS / "serve-down.py",
    "sleep": GATE_SCRIPTS / "serve-sleep.py",
    "wake": GATE_SCRIPTS / "serve-wake.py",
    "fetch": GATE_SCRIPTS / "serve-fetch.py",
}
#
MINTED_PREFIXES = ("RUN_", "DOCKER_")
#
#
#
#
ROOT = HERE.parents[2]


class RefusedError(Exception):
    ""

    def __init__(self, status: int, rule: str) -> None:
        super().__init__(rule)
        self.status = status
        self.rule = rule


@dataclass(frozen=True)
class Entry:
    ""

    script: str
    why: str
    status: int = 2
    exports: tuple[str, ...] = ()


#
#
#
SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "01-config.py",
        "gate 1: the run knows which config it is under, and a `serve up` "
        "held to the live fleet's lock starts only units it names",
        exports=("RUN_CONFIG",),
    ),
    Entry(
        "02-rig.py",
        "gate 2: the rig is leased to this run — refused, untouched, if "
        "another live run holds it; a dead run's lease is reclaimed — and read "
        f"again, and held to your rig file ({RIGS_SHOWN}/<rig>.json, written "
        "by `mcgyvr scan --rig`): what moved is said, and the run is refused "
        "only when the fleet no longer fits",
        exports=("RUN_LEASE", "RUN_PRE_RIG"),
    ),
    Entry(
        "03-image.py",
        "gate 3: the daemon `docker` reaches answers now and is the machine "
        "gate 2 read",
    ),
    Entry(
        "05-envelope.py",
        "gate 5: the run's folder in the door's log is made, the step's "
        "declared artifacts are write-once, and RUN_ID is minted",
        exports=(
            "RUN_ID",
            "RUN_OUT_DIR",
            "RUN_DATE",
            "RUN_STEP",
            "RUN_HOST",
            "RUN_DECLARED",
            "RUN_SUPERSEDED",
        ),
    ),
    Entry(
        "06-step.py",
        "gate 6: the step, with the run exported to it. Its stdout and stderr "
        "are the operator's; the door adds nothing",
        status=1,
    ),
)

#rd
#
#
#
ALWAYS: tuple[Entry, ...] = (
    Entry(
        "07-teardown.py",
        "gate 7: no container named for this run is left, and the rig reads as "
        "it did before. A leftover container is NAMED and not removed — the "
        "kill is the operator's, with the name in hand",
        status=1,
    ),
    Entry(
        "08-parse.py",
        "gate 8: every declared artifact exists and parses, and an appended "
        "file kept its prefix and grew",
        status=1,
    ),
)

#
#
#
#
LEASE_RELEASE = Entry(
    "lease-release.py",
    "the rig's lease is released if it is still this run's; a rig that "
    "cannot be reached is said, and the lease reads as stale to the next run "
    "on this machine",
    status=1,
)

#
#
#
#
#
#
SERVE_SEQUENCE: tuple[Entry, ...] = SEQUENCE

#
#
#
#
#
#
READ_SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "read-01-config.py",
        "read, config: the read knows which config it is under, as gate 1 settles it",
        exports=("RUN_CONFIG",),
    ),
    Entry(
        "read-02-rig.py",
        "read, rig: one reader on the rig, its facts held to the user's rig "
        "file and the rest filed under the read fleet's journal; nothing "
        "leased, nothing torn down, and a busy rig read as it is",
    ),
)
#
#
#
#
#
#
#
LINK_SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "link-01-time.py",
        "link, time: one bounded timer on the rig, its source on stdin and its "
        "reading on stdout; nothing leased, nothing filed, nothing left behind",
    ),
)
#
LINK_MODES = {
    "--peer": ("GPU_A", "GPU_B"),
    "--sink": ("ADDR", "PORT"),
    "--send": ("ADDR", "PORT"),
}
#
READ_ID = re.compile(r"^run-(\d{8}T\d{6})-([0-9a-f]{8})$")
#
#
LOAD_SPEC = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$")


def mint_read_id(now: datetime | None = None) -> str:
    ""
    moment = now if now is not None else datetime.now(UTC)
    return f"run-{moment:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}"


#
#
EXPORTED = (
    #
    #
    #
    #
    "RUN_ROOT",
    "RUN_BIN",
    "RUN_STEP_FILE",
    "RUN_HOST",
    "RUN_SUFFIX",
    #
    #
    "RUN_SERVE",
    "RUN_COMPOSE",
    "RUN_SERVE_EXPECTED",
    #
    #
    "RUN_SERVE_ONLY",
    #
    #
    "RUN_SERVE_ASLEEP",
    #
    #
    "RUN_FETCH",
    "RUN_FETCH_TOKEN_ENV",
    #
    #
    #
    "RUN_READ_ID",
    "RUN_READ_PROBE",
    "RUN_READ_LOAD",
    "RUN_READ_FLEET",
    #
    "RUN_LINK",
    #
    #
    "RUN_COMMAND",
    "RUN_STEP_EXIT",
    *(name for entry in (*SEQUENCE, *ALWAYS) for name in entry.exports),
)


#
#
#
EXPORT_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _refuse(status: int, rule: str) -> NoReturn:
    raise RefusedError(status, rule)


def pin_config(env: dict[str, str]) -> None:
    ""
    named = env.get(CONFIG_PATH_ENV)
    if not named:
        return
    try:
        path = Path(named).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    except (OSError, RuntimeError) as escape:
        _refuse(
            2,
            f"{CONFIG_PATH_ENV}={named!r} cannot be read as a path "
            f"({escape!r}); name the config file by an absolute path",
        )
    env[CONFIG_PATH_ENV] = str(path)


def _command(verb: str, argv: list[str]) -> str:
    ""
    return shlex.join(["python", "-m", DOOR_MODULE, *([verb] if verb else []), *argv])


#
HOST_HELP = f"the rig, as your ssh names it: its name in {RIGS_SHOWN}/"


def check_manifest() -> None:
    ""
    missing = [
        e.script
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, *LINK_SEQUENCE, LEASE_RELEASE)
        if not (GATE_SCRIPTS / e.script).is_file()
    ] + [path.name for path in (*SERVE_STEPS.values(), *READERS) if not path.is_file()]
    if missing:
        _refuse(
            2,
            f"the door is incomplete: {', '.join(missing)} not under "
            f"{_rel(GATE_SCRIPTS)}. Every entry in SEQUENCE runs on "
            "every run; a missing one is a refusal and never a skip, because "
            "'the file was gone' is how a check stops running without anyone "
            "deciding it should",
        )
    unrunnable = [
        e.script
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, *LINK_SEQUENCE, LEASE_RELEASE)
        if not os.access(GATE_SCRIPTS / e.script, os.X_OK)
    ] + [step.name for step in SERVE_STEPS.values() if not os.access(step, os.X_OK)]
    if unrunnable:
        _refuse(
            2,
            f"not executable: {', '.join(unrunnable)}. chmod +x, or the door "
            "cannot run a gate it is holding you to",
        )
    #
    #
    #
    shims_gone = [
        name
        for name in SHIMS
        if not ((BIN / name).is_file() and os.access(BIN / name, os.X_OK))
    ]
    if shims_gone:
        _refuse(
            2,
            f"the door is incomplete: {', '.join(shims_gone)} not executable "
            f"under {_rel(BIN)}. Under the door every rig connection and every "
            "docker call goes through these shims; without one, PATH falls "
            "through to the operator's binary and nothing admits the host",
        )


def run_entry(entry: Entry, env: dict[str, str]) -> int:
    ""
    script = GATE_SCRIPTS / entry.script
    read_fd, write_fd = os.pipe()
    try:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=ROOT,
                env=dict(env, RUN_EXPORT_FD=str(write_fd)),
                pass_fds=(write_fd,),
            )
        except (OSError, ValueError) as escape:
            _refuse(2, f"{entry.script} could not be started: {escape}")
        os.close(write_fd)
        write_fd = -1
        with os.fdopen(read_fd, "r", encoding="utf-8", errors="replace") as pipe:
            read_fd = -1
            try:
                reported = pipe.read()
                status = proc.wait()
            except KeyboardInterrupt:
                #
                #
                #
                #
                _end(proc)
                raise
    finally:
        for fd in (read_fd, write_fd):
            if fd >= 0:
                os.close(fd)

    for line in reported.splitlines():
        if not line.strip():
            continue
        match = EXPORT_LINE.match(line)
        if match is None:
            _refuse(
                2,
                f"{entry.script} wrote {line!r} on RUN_EXPORT_FD, which is not "
                "KEY=VALUE; the door passes named facts between gates and "
                "nothing else",
            )
        key, value = match.group(1), match.group(2)
        if "\x00" in value:
            _refuse(
                2,
                f"{entry.script} exported {key} with a NUL byte in its value; no "
                "process can start with it in its environment",
            )
        if key not in entry.exports:
            _refuse(
                2,
                f"{entry.script} exported {key}, which it does not declare in "
                "SEQUENCE. The door knows the whole vocabulary before anything "
                "runs, so a gate cannot introduce a variable a later gate reads",
            )
        env[key] = value

    missing = [k for k in entry.exports if k not in env]
    if status == 0 and missing:
        _refuse(
            2,
            f"{entry.script} exited 0 without exporting {', '.join(missing)}; "
            "an entry that admits the run must produce what it declares, or a "
            "later gate reads an empty value as a fact",
        )
    return status


def _end(proc: subprocess.Popen[bytes]) -> None:
    ""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _ambient() -> str | None:
    ""
    for name in sorted(os.environ):
        if name.startswith(MINTED_PREFIXES):
            return name
    return None


def _rel(path: Path, base: Path = ROOT) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _serve_parse(argv: list[str]) -> argparse.Namespace:
    ""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run serve",
        description=(
            "start a live ladder on a rig and leave it running, or stop it; put "
            "its units to sleep or wake them; or fetch weights onto it. One run "
            "holds a rig at a time (its lease, ~/.mcgyvr/lease on the rig): a "
            "rig another live run holds is refused before anything reaches it, "
            "naming that run, and nothing of that run is touched — wait for it "
            "or end it. A lease whose run died on this machine is reclaimed"
        ),
    )
    parser.add_argument(
        "direction",
        choices=sorted(SERVE_STEPS),
        help="up | down | sleep | wake | fetch",
    )
    parser.add_argument("--host", required=True, help=HOST_HELP)
    parser.add_argument(
        "--compose",
        default=None,
        help=(
            "up, down, sleep and wake: the compose file `mcgyvr emit` wrote for "
            "this host"
        ),
    )
    parser.add_argument(
        "--weights",
        default=None,
        metavar="FILE",
        help=(
            'fetch only: the fetch list (JSON: {"files": [{repo, revision, file, '
            "sha256, bytes}]}), each file pinned to a commit and its sha256 as "
            "the model knowledge records it. The files land in the rig's weights "
            "folder ($MCGYVR_WEIGHTS there, else ~/.cache/mcgyvr/weights) under "
            "their base names; a download resumes from its .part, and one whose "
            "sha256 does not match is deleted. No size cap: the total is said "
            "before a byte moves. The Hub is $HF_ENDPOINT when set (https, or "
            "http on this machine's loopback), else huggingface.co"
        ),
    )
    parser.add_argument(
        "--hf-token-env",
        default=None,
        metavar="VAR",
        help=(
            "fetch only: the variable a Hugging Face token is read from, for a "
            "gated or private repository (default: HF_TOKEN, used when set). "
            "Named and empty is refused. The token goes to the fetch on the rig "
            "inside the ssh connection, never on a command line or into a file"
        ),
    )
    parser.add_argument("--suffix", default="", help="distinguishes a re-run's RUN_ID")
    parser.add_argument("--date", default="", help="YYYY-MM-DD; defaults to today, UTC")
    parser.add_argument(
        "--unit",
        action="append",
        default=[],
        metavar="CONTAINER",
        help=(
            "up, down, sleep and wake: act on this container of the compose file "
            "and leave the file's other units as they are (repeatable). `up` "
            "starts it without its compose neighbours, `down` stops and removes "
            "it, and a card's co-resident vLLM units each sleep at level 2 on "
            "their own"
        ),
    )
    return parser.parse_args(argv)


def _serve_refusal(opts: argparse.Namespace) -> str | None:
    ""
    if opts.direction == "fetch":
        given = [
            flag
            for flag, value in (("--compose", opts.compose), ("--unit", opts.unit))
            if value
        ]
        if given:
            return (
                f"serve fetch takes no {' or '.join(given)}: a fetch downloads "
                "weights and starts nothing; name what it downloads with --weights"
            )
        if opts.weights is None:
            return "serve fetch names what it downloads with --weights FILE"
        return None
    if opts.compose is None:
        return f"serve {opts.direction} needs --compose, the file `mcgyvr emit` wrote"
    if opts.weights is not None or opts.hf_token_env is not None:
        return (
            f"serve {opts.direction} takes no --weights or --hf-token-env; only "
            "serve fetch downloads"
        )
    return None


def serve(argv: list[str]) -> int:
    ""
    opts = _serve_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    mismatched = _serve_refusal(opts)
    if mismatched is not None:
        print(f"run.py: REFUSED — {mismatched}", file=sys.stderr)
        return 2
    compose_file: Path | None = None
    units: tuple[Any, ...] = ()
    fetch: dict[str, str] = {}
    if opts.direction == "fetch":
        #
        #
        #
        from mcgyvr.serving import fetchlist

        listed = Path(opts.weights)
        listed = listed if listed.is_absolute() else Path.cwd() / listed
        try:
            wants = fetchlist.read(listed)
        except fetchlist.FetchListError as escape:
            print(
                f"run.py: REFUSED — --weights {opts.weights}: {escape}", file=sys.stderr
            )
            return 2
        try:
            fetchlist.endpoint(os.environ)
            token_env = fetchlist.token_variable(opts.hf_token_env, os.environ)
        except fetchlist.FetchListError as escape:
            print(f"run.py: REFUSED — {escape}", file=sys.stderr)
            return 2
        fetch = {"RUN_FETCH": fetchlist.dump(wants), "RUN_FETCH_TOKEN_ENV": token_env}
    else:
        assert opts.compose is not None
        compose_file = Path(opts.compose)
        compose_file = (
            compose_file if compose_file.is_absolute() else Path.cwd() / compose_file
        )
        if not compose_file.is_file():
            print(
                f"run.py: REFUSED — --compose {opts.compose} is not a file; "
                "`mcgyvr emit` writes one per host",
                file=sys.stderr,
            )
            return 2
        #
        #
        #
        from mcgyvr.serving import servelib

        try:
            units = servelib.services(compose_file)
        except servelib.ComposeError as escape:
            print(f"run.py: REFUSED — {escape}", file=sys.stderr)
            return 2
        #
        #
        unknown = sorted(set(opts.unit) - {unit.container for unit in units})
        if unknown:
            print(
                f"run.py: REFUSED — the compose file names no container "
                f"{', '.join(unknown)}; --unit names a container the file declares",
                file=sys.stderr,
            )
            return 2

    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env.update(
        RUN_ROOT=str(ROOT),
        RUN_BIN=str(BIN),
        RUN_STEP_FILE=str(SERVE_STEPS[opts.direction].resolve()),
        RUN_HOST=opts.host,
        RUN_SUFFIX=opts.suffix,
        RUN_SERVE=opts.direction,
        RUN_COMPOSE=str(compose_file.resolve()) if compose_file is not None else "",
        RUN_SERVE_EXPECTED=" ".join(unit.container for unit in units),
        RUN_SERVE_ONLY=" ".join(sorted(set(opts.unit))),
        RUN_SERVE_ASLEEP=" ".join(sorted(u.container for u in units if u.asleep)),
        RUN_COMMAND=_command("serve", argv),
        **fetch,
    )
    if opts.date:
        env["RUN_DATE"] = opts.date
    return _serve_run(env)


def _serve_run(env: dict[str, str]) -> int:
    ""
    interrupted = False
    step_status = 0
    try:
        try:
            check_manifest()
            for entry in SERVE_SEQUENCE:
                status = run_entry(entry, env)
                if status != 0:
                    if entry.script != "06-step.py":
                        return _stop(entry, status, env)
                    step_status = status
        except RefusedError as refusal:
            print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
            return refusal.status
        except KeyboardInterrupt:
            interrupted = True
            print(
                "run.py: interrupted — gates 7 and 8 still run; a run whose end "
                "state is unknown is the one that ended silently",
                file=sys.stderr,
            )

        env["RUN_STEP_EXIT"] = "interrupted" if interrupted else str(step_status)
        after = _always(env)
        if interrupted:
            return 130
        return step_status or after
    finally:
        #
        #
        #
        #
        _release_claim(env)
        _release_lease(env)


def _read_parse(argv: list[str]) -> argparse.Namespace:
    ""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run read",
        description=(
            "read a rig: its facts, its containers and its card, filed under "
            "the journal of the fleet read (the live one, or --fleet's); --probe "
            "and --load run the lock's harness on it"
        ),
    )
    parser.add_argument("--host", required=True, help=HOST_HELP)
    parser.add_argument(
        "--probe",
        nargs="+",
        default=[],
        metavar="UNIT",
        help=(
            "awake units of the fleet read on this rig to measure on the rig with "
            "the lock's own harness, each only while it has nothing in flight"
        ),
    )
    parser.add_argument(
        "--load",
        default="",
        metavar="WxN",
        help=(
            "with --probe: W concurrent requests on the rig, each filling the "
            "unit's N-token window, while its container's card peak is sampled "
            "and judged against its room_mib"
        ),
    )
    parser.add_argument(
        "--fleet",
        default="",
        metavar="FLEET",
        help=(
            "read FLEET of the fleet.yaml in the folder of the config the read "
            "loads (MCGYVR_CONFIG, else the live fleet folder) instead of the "
            "live fleet: no lock, rows "
            "filed locked=false, probe figures unjudged, card and load peak "
            "judged against room_mib"
        ),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="the id the read's rows are filed under (default: minted)",
    )
    return parser.parse_args(argv)


def read(argv: list[str]) -> int:
    ""
    opts = _read_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    run_id = opts.run_id or mint_read_id()
    if READ_ID.match(run_id) is None:
        print(
            f"run.py: REFUSED — --run-id {run_id!r} is not "
            "run-YYYYMMDDTHHMMSS-xxxxxxxx",
            file=sys.stderr,
        )
        return 2
    if opts.load and not opts.probe:
        print(
            "run.py: REFUSED — --load needs --probe: a load runs on the units a "
            "probe names, and only while each is idle",
            file=sys.stderr,
        )
        return 2
    if opts.load and LOAD_SPEC.match(opts.load) is None:
        print(
            f"run.py: REFUSED — --load {opts.load!r} is not WxN: W concurrent "
            "requests, each filling an N-token window (e.g. 8x4096)",
            file=sys.stderr,
        )
        return 2
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env.update(
        RUN_ROOT=str(ROOT),
        RUN_BIN=str(BIN),
        RUN_HOST=opts.host,
        RUN_READ_ID=run_id,
        RUN_READ_PROBE=" ".join(opts.probe),
        RUN_READ_LOAD=opts.load,
        RUN_READ_FLEET=opts.fleet,
        RUN_COMMAND=_command("read", argv),
    )
    try:
        check_manifest()
        for entry in READ_SEQUENCE:
            status = run_entry(entry, env)
            if status == 2:
                return _stop(entry, status, env)
            if status != 0:
                return status
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    except KeyboardInterrupt:
        return 130
    return 0


def _link_parse(argv: list[str]) -> argparse.Namespace:
    ""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run link",
        description=(
            "time a link on a rig: copies between two of its cards (--peer), or "
            "the network to another rig (--sink there, --send here); one bounded "
            "timer, its reading printed as one line of JSON and nothing filed"
        ),
    )
    parser.add_argument(
        "--host", required=True, help="the rig the timer runs on, as ssh names it"
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    for flag, names in LINK_MODES.items():
        modes.add_argument(flag, nargs=2, metavar=names)
    return parser.parse_args(argv)


def _link_args(opts: argparse.Namespace) -> list[str]:
    ""
    for flag in LINK_MODES:
        given = getattr(opts, flag[2:])
        if given is None:
            continue
        first, second = given
        if flag == "--peer":
            cards = [first, second]
            if not all(card.isascii() and card.isdigit() for card in cards):
                raise RefusedError(2, f"--peer {first} {second}: a card is its index")
            if first == second:
                raise RefusedError(2, f"--peer {first} {second}: two cards, not one")
            return ["peer", str(int(first)), str(int(second))]
        try:
            ipaddress.IPv4Address(first)
        except ValueError:
            raise RefusedError(
                2, f"{flag} {first!r}: the address is an IPv4 literal, never a name"
            ) from None
        if not (second.isascii() and second.isdigit() and 1024 <= int(second) < 65536):
            raise RefusedError(2, f"{flag} port {second!r}: a port from 1024 to 65535")
        return [flag[2:], first, str(int(second))]
    raise RefusedError(2, "link: no mode given")


def link(argv: list[str]) -> int:
    ""
    opts = _link_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    try:
        timer = _link_args(opts)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    env.update(
        RUN_ROOT=str(ROOT),
        RUN_BIN=str(BIN),
        RUN_HOST=opts.host,
        RUN_LINK=" ".join(timer),
        RUN_COMMAND=_command("link", argv),
    )
    try:
        check_manifest()
        for entry in LINK_SEQUENCE:
            status = run_entry(entry, env)
            if status != 0:
                return status
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    except KeyboardInterrupt:
        return 130
    return 0


def main(argv: list[str] | None = None) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    verbs = {"serve": serve, "read": read, "link": link}
    if given[:1] and given[0] in verbs:
        return verbs[given[0]](given[1:])
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run",
        description="the one access point to the rigs",
        epilog=(
            "The verbs, each with its own --help: `serve "
            "up|down|sleep|wake|fetch` starts, stops, sleeps or wakes a "
            "ladder on a rig, or fetches weights onto it; `read` reads a rig; "
            "and `link` times a link on one. Each runs the door's own fixed "
            "gates; nothing adds, skips or moves one"
        ),
    )
    parser.add_argument("verb", nargs="?", choices=("serve", "read", "link"))
    parser.parse_args(given)
    parser.print_help()
    return 0


#
UNSTOPPABLE = (signal.SIGINT, signal.SIGTERM)


def _always(env: dict[str, str]) -> int:
    ""
    if "RUN_ID" not in env:
        return 0  #
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in UNSTOPPABLE}
    after = 0
    try:
        for entry in ALWAYS:
            try:
                if run_entry(entry, env) != 0:
                    print(f"run.py: {entry.why}", file=sys.stderr)
                    after = entry.status
            except RefusedError as refusal:
                print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
                after = refusal.status
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        _release_claim(env)
    return after


def _release_claim(env: dict[str, str]) -> None:
    ""
    out_dir, run_id = env.get("RUN_OUT_DIR"), env.get("RUN_ID")
    if out_dir and run_id:
        gatelib.release(Path(out_dir), run_id)


def _release_lease(env: dict[str, str]) -> None:
    ""
    if not env.get(gatelib.LEASE_VAR):
        return
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in UNSTOPPABLE}
    try:
        run_entry(LEASE_RELEASE, env)
    except RefusedError as refusal:
        print(f"run.py: {refusal.rule}", file=sys.stderr)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        env.pop(gatelib.LEASE_VAR, None)


def _stop(entry: Entry, status: int, env: dict[str, str]) -> int:
    ""
    print(f"run.py: REFUSED at {entry.script} — {entry.why}", file=sys.stderr)
    return status or entry.status


def _sigterm(_signum: int, _frame: types.FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    #
    #
    #
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)
    sys.exit(main())
