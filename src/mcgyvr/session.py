"""Settle which orchestrator typed this command, and where its transcript is.

A journal row names the orchestrator that produced it, and a name is only worth
writing if a reader can follow it to a transcript. `resolve` takes the
`--orchestrator` value when there is one, and otherwise reads the session the
command was typed from: Claude Code's `CLAUDE_CODE_SESSION_ID`, or a Pi
transcript's path in `PI_SESSION_FILE`. Either way the tool's own session id is
looked up on disk — under `CLAUDE_CONFIG_DIR` or `~/.claude` for Claude Code,
under `~/.pi/agent/sessions` for Pi — and a run whose transcript cannot be found
is refused with `SessionError` rather than filed under a transcript that does
not exist or under a default. An mcorch server's transcript is not on disk when
the name is settled, so `with_mcorch_transcript` attaches it later, once the
journal directory is known.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.config import MCORCH

CLAUDE_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"
CLAUDE_CONFIG_VAR = "CLAUDE_CONFIG_DIR"
PI_SESSION_VAR = "PI_SESSION_FILE"

CLAUDE = "claude"
PI = "pi"
# An orchestrator is named `<tool>-<id>`, and the id is the journal's file name:
# `claude-<session id>`, `pi-<session id>`, or `mcorch-<stamp>`. The first two
# are traced back to the tool's own transcript on disk; an mcorch writer's
# transcript lives under the journal directory and is attached by
# `with_mcorch_transcript` once that directory is known. Claude Code exports its
# session id and config root; a Pi transcript path has to be exported by
# something, and nothing shipped here does.

# Every id this module accepts, and every file name it composes one into: a set
# with no `.`/`..` and no path separator, so an id can never reach outside the
# transcript directory it is looked up in.
_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SessionError(Exception):
    """No session was named, or the one named has no transcript to trace to."""


@dataclass(frozen=True)
class Session:
    """The orchestrator named for a run, and the transcript to file it under.

    `orchestrator` is the name a journal row and a result carry. `session_file`
    is that name's transcript as an absolute path, or None for a name this host
    cannot trace yet: an mcorch writer whose transcript does not exist, and any
    id passed to `--orchestrator` that does not carry a known tool's prefix.
    """

    orchestrator: str
    session_file: Path | None = None


def resolve(explicit: str | None, env: Mapping[str, str] | None = None) -> Session:
    """Settle the session named by `explicit`, or else by the environment.

    An `explicit` value — a `--orchestrator` id — wins outright. Without one the
    environment decides: `CLAUDE_CODE_SESSION_ID` names a Claude Code session and
    `PI_SESSION_FILE` points at a Pi transcript, and both at once is refused
    because nothing says which one typed this command. No session at all is
    refused too, so a run nobody can be traced to never starts. `SessionError`
    carries the reason; `env` replaces `os.environ` when given.
    """
    environment = os.environ if env is None else env
    if explicit is not None:
        return _explicit(explicit, environment)

    claude_id = environment.get(CLAUDE_SESSION_VAR, "").strip()
    pi_file = environment.get(PI_SESSION_VAR, "").strip()
    if claude_id and pi_file:
        raise SessionError(
            f"two sessions are in the environment ({CLAUDE_SESSION_VAR} and "
            f"{PI_SESSION_VAR}) and nothing says which one typed this command; "
            f"pass --orchestrator ID to say."
        )
    if claude_id:
        return Session(
            f"{CLAUDE}-{claude_id}", _claude_transcript(claude_id, environment)
        )
    if pi_file:
        path = Path(pi_file).expanduser()
        if not path.is_file():
            raise SessionError(
                f"{PI_SESSION_VAR}={pi_file!r} names no file; the Pi session "
                f"cannot be traced, so this run is refused rather than filed "
                f"under a transcript that does not exist."
            )
        pi_id = _pi_id(path)
        if not _ID.match(pi_id):
            raise SessionError(
                f"{PI_SESSION_VAR}={pi_file!r} does not name a Pi session id "
                f"in its file name (<stamp>_<id>.jsonl)"
            )
        return Session(f"{PI}-{pi_id}", path.resolve())
    raise SessionError(
        f"nobody is named to write the journal: pass --orchestrator ID, or run "
        f"from a session that exports one ({CLAUDE_SESSION_VAR} from Claude "
        f"Code; {PI_SESSION_VAR} is honoured when something sets it to a Pi "
        f"transcript's path, and nothing shipped here does). A run "
        f"nobody can be traced to is refused, not filed under a default."
    )


def _explicit(orchestrator: str, environment: Mapping[str, str]) -> Session:
    try:
        if orchestrator.startswith(f"{CLAUDE}-"):
            claude_id = orchestrator.removeprefix(f"{CLAUDE}-")
            return Session(orchestrator, _claude_transcript(claude_id, environment))
        if orchestrator.startswith(f"{PI}-"):
            pi_id = orchestrator.removeprefix(f"{PI}-")
            return Session(orchestrator, _pi_transcript(pi_id, environment))
    except SessionError as exc:
        raise SessionError(f"--orchestrator {orchestrator!r}: {exc}") from exc
    return Session(orchestrator)


def _claude_root(environment: Mapping[str, str]) -> Path:
    configured = environment.get(CLAUDE_CONFIG_VAR, "").strip()
    if configured:
        return Path(configured).expanduser()
    return _home(environment) / ".claude"


def _home(environment: Mapping[str, str]) -> Path:
    home = environment.get("HOME", "").strip()
    return Path(home) if home else Path.home()


def _cwd_slug() -> str:
    """The current directory as Claude Code names its project folder.

    Claude Code files a transcript under `projects/<cwd>`, with each `/` of the
    absolute path replaced by a dash, so `_cwd_slug` reproduces that name.
    """
    return os.getcwd().replace("/", "-")


def _claude_transcript(session_id: str, environment: Mapping[str, str]) -> Path:
    root = _claude_root(environment)
    if not _ID.match(session_id):
        raise SessionError(f"{session_id!r} is not a Claude Code session id")
    # This directory's own project folder is tried first; a resumed or copied
    # session can sit under another one, so a miss there falls back to every
    # folder under `projects`. The first path in sorted order is taken.
    here = root / "projects" / _cwd_slug() / f"{session_id}.jsonl"
    found = (
        [here]
        if here.is_file()
        else sorted((root / "projects").glob(f"*/{session_id}.jsonl"))
    )
    if not found:
        raise SessionError(
            f"no Claude Code transcript for session {session_id!r} under "
            f"{root / 'projects'}; the run is refused rather than filed under "
            f"a session that cannot be traced. Set {CLAUDE_CONFIG_VAR} if Claude "
            f"Code keeps its transcripts elsewhere."
        )
    return found[0].resolve()


def _pi_transcript(session_id: str, environment: Mapping[str, str]) -> Path:
    root = _home(environment) / ".pi" / "agent" / "sessions"
    if not _ID.match(session_id):
        raise SessionError(f"{session_id!r} is not a Pi session id")
    found = sorted(root.glob(f"*/*_{session_id}.jsonl"))
    if not found:
        raise SessionError(
            f"no Pi transcript for session {session_id!r} under {root}; the run "
            f"is refused rather than filed under a session that cannot be traced."
        )
    return found[0].resolve()


def _pi_id(path: Path) -> str:
    """The session id in a Pi transcript's file name, `<stamp>_<id>.jsonl`.

    The stem is split at its last underscore, so a stamp that holds one still
    yields the id; a stem with no underscore is taken as the id whole.
    """
    stem = path.stem
    _, sep, uuid = stem.rpartition("_")
    return uuid if sep else stem


def with_mcorch_transcript(named: Session, journal_dir: Path) -> Session:
    """Attach an mcorch writer's transcript under `journal_dir`, when it is there.

    An mcorch server is named `mcorch-<stamp>` and writes one JSON row per
    request to `journal_dir/mcorch/<name>.jsonl`, but its id is minted before the
    run knows the journal directory, so the file is looked up here instead. A
    session that already has a transcript, or that is not an mcorch writer, is
    returned unchanged; so is an mcorch writer whose transcript does not exist
    yet, since a writer that has not written is still a name, not a refusal.
    """
    if named.session_file is not None or not named.orchestrator.startswith(
        f"{MCORCH}-"
    ):
        return named
    path = journal_dir / MCORCH / f"{named.orchestrator}.jsonl"
    if not path.is_file():
        return named
    return Session(named.orchestrator, path.resolve())
