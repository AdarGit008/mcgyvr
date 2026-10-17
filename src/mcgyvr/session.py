""

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
#
#
#
#er
#
#
#

#
#
#
_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SessionError(Exception):
    ""


@dataclass(frozen=True)
class Session:
    ""

    orchestrator: str
    session_file: Path | None = None


def resolve(explicit: str | None, env: Mapping[str, str] | None = None) -> Session:
    ""
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
    ""
    return os.getcwd().replace("/", "-")


def _claude_transcript(session_id: str, environment: Mapping[str, str]) -> Path:
    root = _claude_root(environment)
    if not _ID.match(session_id):
        raise SessionError(f"{session_id!r} is not a Claude Code session id")
    #
    #
    #
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
    ""
    stem = path.stem
    _, sep, uuid = stem.rpartition("_")
    return uuid if sep else stem


def with_mcorch_transcript(named: Session, journal_dir: Path) -> Session:
    ""
    if named.session_file is not None or not named.orchestrator.startswith(
        f"{MCORCH}-"
    ):
        return named
    path = journal_dir / MCORCH / f"{named.orchestrator}.jsonl"
    if not path.is_file():
        return named
    return Session(named.orchestrator, path.resolve())
