"""Who typed the command: the session a run is filed under, and its transcript.

Every journal row names the orchestrator that produced it (§9), and a name
that is only a string is a name a reader cannot follow. The orchestrators
that actually type ``mcgyvr run`` are coding agents in a session — Claude
Code, Pi — and each keeps a transcript of the whole conversation on disk. So
the orchestrator id *is* the session, and the row carries the transcript's
path: an attempt can be traced back to the exact exchange that produced it.

Three sources, one rule each:

* ``--orchestrator ID`` on the command line wins, verbatim. An id shaped
  ``claude-<id>`` or ``pi-<id>`` is a claim about a transcript, and a claim
  nobody can check is refused rather than recorded — a row naming a session
  that does not exist is worse than a row naming none. Any other id names no
  transcript and carries none.
* ``CLAUDE_CODE_SESSION_ID`` is what Claude Code exports to every child
  process. The transcript lives at ``<config dir>/projects/<cwd-slug>/<id>.jsonl``
  where the config dir is ``$CLAUDE_CONFIG_DIR`` or ``~/.claude``; the slug is
  Claude Code's, so it is found by glob rather than rebuilt.
* ``PI_SESSION_FILE`` is the transcript's path itself, exported by a Pi
  extension on session start (Pi exports nothing on its own). The id is the
  uuid Pi puts after the timestamp in the file name.

None of the three is a refusal, not a default: a hostname or a pid would be
exactly the single-orchestrator assumption §9 names, and the flag is one word
away. Both environment sessions at once is a refusal too. Claude Code can
launch Pi and Pi can launch Claude Code, and the environment does not say
which is nearer; a guess would file a whole conversation under the wrong
agent, silently.

The id joins with a dash, never a colon: it is the journal's file name
(``DIR/<ID>.jsonl``) and the prefix of every ``attempt_id``, which is
colon-separated already.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CLAUDE_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"
CLAUDE_CONFIG_VAR = "CLAUDE_CONFIG_DIR"
PI_SESSION_VAR = "PI_SESSION_FILE"

CLAUDE = "claude"
PI = "pi"

#: What a session id may look like. It is spliced into a file-system glob, a
#: journal file name and every attempt id, so a metacharacter in it would
#: match someone else's transcript or name a file nobody can open.
_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SessionError(Exception):
    """No session could be named, or the one named cannot be checked."""


@dataclass(frozen=True)
class Session:
    """The writer of a journal, and the transcript behind it when there is one."""

    orchestrator: str
    session_file: Path | None = None


def resolve(explicit: str | None, env: Mapping[str, str] | None = None) -> Session:
    """The session a run is filed under, from the flag or the environment.

    Raises :class:`SessionError` with a message that names the flag and both
    variables, so the operator is told how to be named rather than that they
    were not.
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
        f"Code, {PI_SESSION_VAR} from Pi's mcgyvr-session extension). A run "
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
    """The directory name Claude Code files a cwd's transcripts under."""
    return os.getcwd().replace("/", "-")


def _claude_transcript(session_id: str, environment: Mapping[str, str]) -> Path:
    root = _claude_root(environment)
    if not _ID.match(session_id):
        raise SessionError(f"{session_id!r} is not a Claude Code session id")
    # The transcript of the session that typed this command is filed under
    # this cwd; a session resumed elsewhere can leave a copy under another
    # slug, and the cwd's is the one to prefer before falling back to any.
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
    """The uuid Pi writes after the timestamp: ``<stamp>_<uuid>.jsonl``."""
    stem = path.stem
    _, sep, uuid = stem.rpartition("_")
    return uuid if sep else stem
