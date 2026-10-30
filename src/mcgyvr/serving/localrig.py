"""The door's transport to this machine: its rig steps run here, with no ssh.

`gatelib.ssh` hands a command here instead of to ssh when the rig is this
machine and the door reaches it without ssh
(:func:`mcgyvr.serving.gatelib.local_transport`): macOS and Windows, which run
no sshd unless asked to, and Linux without one. What is run is held to the
shapes the gates build, and nothing goes through a shell of this module's
making:

- ``echo <base64> | base64 -d | python3 <args>``, a shipped reader (the
  machine reader, the header reader): the source is decoded and run on this
  interpreter with the same arguments, read from stdin as the rig's python3
  would read it;
- ``python3 <args>`` with its source on stdin (the fetcher, the link timer,
  the harness): the same, on this interpreter;
- ``curl`` against this machine's own port (``localhost`` or ``127.0.0.1``),
  with the flags the serve steps use (``-s``, ``-f``, ``-w '\\n%{http_code}'``,
  ``-X``, ``-H``, ``-d``, ``-m``): the request is made with urllib, and the
  answer and status are those curl gives (22 for an HTTP error under ``-f``,
  7 for no connection);
- ``find '<dir>' -maxdepth 1 -name '*.gguf' -print``: the folder is listed;
- ``bash -s ...`` with its script on stdin (the runtime reader, the lease
  scripts): run by this machine's bash, which macOS and Linux have; Windows
  has none, and the command is refused there.

Any other command is refused with status 126 and the reason on stderr, as a
command a rig would not run. A timeout raises :class:`subprocess.TimeoutExpired`
as the ssh call does.
"""

from __future__ import annotations

import base64
import binascii
import http.client
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mcgyvr import hostos
from mcgyvr.serving.gatelib import LOCAL_RIGS

#: The statuses curl answers with: an HTTP error under ``-f``, no connection,
#: a timeout; and the status of a command this transport does not run.
CURL_HTTP_ERROR = 22
CURL_NO_CONNECTION = 7
CURL_TIMEOUT = 28
REFUSED = 126
#: How long a curl with no ``-m`` waits.
CURL_S = 60.0
#: The only ``-w`` format the serve steps use.
STATUS_FORMAT = "\\n%{http_code}"
#: The reader shapes' fixed parts.
ECHO = "echo "
DECODE = " | base64 -d | python3 "
FIND_TAIL = " -maxdepth 1 -name '*.gguf' -print"
#: The interpreter flags a shipped source is run with, before its ``-``.
PYTHON_FLAGS = frozenset({"-I", "-B"})


def run(
    command: str, *, input: str | None, timeout: float | None
) -> subprocess.CompletedProcess[str]:
    """Run one rig command on this machine, as the rig would answer it."""
    if command.startswith(ECHO) and DECODE in command:
        blob, _sep, tail = command[len(ECHO) :].partition(DECODE)
        try:
            source = base64.b64decode(blob, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return _refused(command, "its base64 does not decode")
        return _python(shlex.split(tail), source, timeout)
    words = _split(command)
    if words is None:
        return _refused(command, "it does not parse as one command")
    if words[:1] == ["python3"]:
        return _python(words[1:], input, timeout)
    if words[:1] == ["curl"]:
        return _curl(command, words[1:])
    if command.startswith("find ") and command.endswith(FIND_TAIL):
        return _find(command, words)
    if words[:2] == ["bash", "-s"]:
        bash = shutil.which("bash")
        if bash is None or hostos.os_name() == "windows":
            return _refused(command, "this machine has no bash to read the script")
        return subprocess.run(
            [bash, *words[1:]],
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    return _refused(command, "it is not one of the steps a rig runs")


def _split(command: str) -> list[str] | None:
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _refused(command: str, why: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        [command],
        REFUSED,
        "",
        f"local rig: refused {command[:80]!r}: {why}\n",
    )


def _python(
    args: list[str], source: str | None, timeout: float | None
) -> subprocess.CompletedProcess[str]:
    """`python3 ARGS` with `source` on stdin, on this interpreter."""
    if "-" not in args or any(
        flag not in PYTHON_FLAGS for flag in args[: args.index("-")]
    ):
        return _refused(
            f"python3 {shlex.join(args)}", "it is not a source read from stdin"
        )
    return subprocess.run(
        [sys.executable, *args],
        input=source,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _find(command: str, words: list[str]) -> subprocess.CompletedProcess[str]:
    """The `*.gguf` files one level down the named folder, one per line."""
    if len(words) != 7:
        return _refused(command, "it is not the *.gguf discovery")
    folder = Path(words[1])
    try:
        found = sorted(
            str(folder / entry.name)
            for entry in folder.iterdir()
            if entry.name.endswith(".gguf")
        )
    except OSError as exc:
        return subprocess.CompletedProcess([command], 1, "", f"find: {exc}\n")
    return subprocess.CompletedProcess(
        [command], 0, "".join(f"{line}\n" for line in found), ""
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand a 3xx back as it is, as curl without ``-L`` does: never followed."""

    def redirect_request(self, *_args: object, **_kw: object) -> None:
        return None


#: The opener every request to this machine's ports goes through: no proxy
#: from the environment, and no redirect followed, so a request for a local
#: port reaches that port and nothing else.
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
#: What :func:`ask` answers for a request that got no answer, and for one that
#: ran out of time.
NO_ANSWER = 0
CURL_TIMEOUT_CODE = -1


def ask(
    url: str,
    *,
    timeout: float,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str = "GET",
) -> tuple[int, bytes]:
    """One request to this machine's `url`: its status and body.

    No proxy and no redirect (:data:`_LOCAL`); a host that is not this
    machine's is not asked. The status is :data:`NO_ANSWER` when nothing
    answered and :data:`CURL_TIMEOUT_CODE` when the answer was too late.
    """
    if (urllib.parse.urlsplit(url).hostname or "") not in LOCAL_RIGS:
        return NO_ANSWER, b""
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method
    )
    try:
        with _LOCAL.open(request, timeout=timeout) as answer:
            return int(answer.status), answer.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()
    except TimeoutError:
        return CURL_TIMEOUT_CODE, b""
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            return CURL_TIMEOUT_CODE, b""
        return NO_ANSWER, b""
    except (OSError, http.client.HTTPException, ValueError):
        return NO_ANSWER, b""


def _curl(command: str, words: list[str]) -> subprocess.CompletedProcess[str]:
    """A curl the serve steps make of this machine's own port, made with urllib."""
    fail = False
    write_out: str | None = None
    method: str | None = None
    headers: dict[str, str] = {}
    data: bytes | None = None
    budget = CURL_S
    urls: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        takes = word in ("-w", "-X", "-H", "-d", "-m")
        if takes and index + 1 >= len(words):
            return _refused(command, f"{word} has no value")
        value = words[index + 1] if takes else ""
        if word in ("-s", "-sf", "-fs", "-f"):
            fail = fail or "f" in word
        elif word == "-w":
            if value != STATUS_FORMAT:
                return _refused(command, "only -w '\\n%{http_code}' is spoken here")
            write_out = value
        elif word == "-X":
            method = value.upper()
        elif word == "-H":
            name, _sep, said = value.partition(":")
            headers[name.strip()] = said.strip()
        elif word == "-d":
            data = value.encode("utf-8")
        elif word == "-m":
            try:
                budget = float(value)
            except ValueError:
                return _refused(command, "-m is not a number of seconds")
        elif word.startswith("-"):
            return _refused(command, f"curl's {word} is not spoken here")
        else:
            urls.append(word)
        index += 2 if takes else 1
    if len(urls) != 1:
        return _refused(command, "it names no single address")
    target = urllib.parse.urlsplit(urls[0])
    if target.scheme != "http" or (target.hostname or "") not in LOCAL_RIGS:
        return _refused(command, "a local rig's curl reaches this machine's ports only")
    code, body = ask(
        urls[0],
        timeout=budget,
        data=data,
        headers=headers,
        method=method or ("POST" if data else "GET"),
    )
    if code == CURL_TIMEOUT_CODE:
        return subprocess.CompletedProcess([command], CURL_TIMEOUT, "", "")
    if code == NO_ANSWER:
        return subprocess.CompletedProcess([command], CURL_NO_CONNECTION, "", "")
    if fail and code >= 400:
        return subprocess.CompletedProcess([command], CURL_HTTP_ERROR, "", "")
    text = body.decode("utf-8", "replace")
    if write_out is not None:
        text += f"\n{code}"
    return subprocess.CompletedProcess([command], 0, text, "")
