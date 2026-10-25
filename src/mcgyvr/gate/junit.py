"""Pytest's JUnit XML report: asked for at the gate, and read as data.

A failing test suite prints prose, and a finding that only quotes it leaves a
reader to parse test ids and exception names back out of that prose. So when
an acceptance or demonstrating command is pytest, :func:`reporting` gives the
argv that also asks pytest for its own machine-readable report —
``--junitxml`` into the workspace root, under the ``xunit1`` family, the one
that keeps each test's ``file`` and ``line`` — and :func:`collect` reads that
report back and removes it, so it is never taken for something the command
left behind.

The flags are added only where they cannot change what the command means:
pytest run as a program, as ``python -m pytest``, or under a project runner's
``run``; with no ``--`` after which a flag would be read as a file; and with no
JUnit option of the command's own. A command that took the flags and still
wrote no report is the caller's to run again as written
(:mod:`mcgyvr.gate.acceptance`), so the verdict never rests on the flags.

What is read is what the report holds as data: per failing or erroring
testcase its ``classname``, ``name``, ``file`` and ``line``, the ``message``
pytest recorded for the failure, and its text. The node id is put back
together from those fields exactly as pytest took them apart, and is left
unset when they do not fit together. The one thing read out of text is the
exception line pytest writes for the error it caught (``E   Type: message``),
and from that line only :func:`symbol_of` takes a name, and only when the
whole line is one of the interpreter's own fixed wordings for a missing name.

The report is written by code the change controls, so it is read as untrusted
input: only a regular file, never through a link, of bounded size, and never a
document that declares entities.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Where the report is written, relative to the workspace root the gate runs
#: commands in. A dot-file, so a listing of the tree does not show it.
REPORT = ".mcgyvr-acceptance-junit.xml"

#: The flags that ask for the report. ``xunit1`` is the family that keeps the
#: ``file`` and ``line`` attributes on a testcase; pytest's default since 6.0,
#: ``xunit2``, drops them.
_FLAGS = (f"--junitxml={REPORT}", "-o", "junit_family=xunit1")

#: The programs that are pytest itself.
_PYTEST = frozenset({"pytest", "py.test"})

#: A Python interpreter's program name: ``python``, ``python3``, ``python3.12``.
_PYTHON = re.compile(r"python(?:\d+(?:\.\d+)?)?")

#: Project runners whose ``run`` subcommand runs the program that follows its
#: own options in the project's environment.
_RUNNERS = frozenset({"uv", "poetry", "pdm", "pipenv", "rye"})

#: The runner options that take no value, so the token after one of them is
#: still the runner's: any other option might take the next token as its value
#: (`uv run --with pytest python check.py`), and is only passed over when it
#: carries its value in itself (`--python=3.12`).
_RUNNER_SWITCHES = frozenset(
    {
        "--",
        "-q",
        "--quiet",
        "-v",
        "--verbose",
        "--frozen",
        "--locked",
        "--no-sync",
        "--offline",
        "--isolated",
        "--active",
        "--exact",
        "--no-dev",
        "--all-extras",
        "--all-groups",
        "--no-project",
    }
)

#: The largest report read. Far above what a suite of thousands of tests
#: writes, and small enough that a report written to exhaust the reader is not
#: read at all.
_MAX_REPORT_BYTES = 8 * 1024 * 1024

#: The message pytest gives the error element of a module it could not collect
#: (``append_collect_error`` in ``_pytest/junitxml.py``).
_COLLECTION_FAILURE = "collection failure"

#: The exception line pytest writes for the error it caught: ``E``, the
#: indent, then ``Type: message``.
_EXCEPTION_LINE = re.compile(r"E\s+(?P<line>[A-Za-z_][\w.]*: .*)")

#: The interpreter's own fixed wordings for a missing name, each matched
#: against a whole exception line. CPython 3.10 and later may add a
#: ``. Did you mean: 'x'?`` suggestion, which is allowed and not read.
_SUGGESTION = r"(?:\. Did you mean: '[\w.]+'\?)?"
_MISSING_NAME = (
    re.compile(rf"NameError: name '(?P<name>\w+)' is not defined{_SUGGESTION}"),
    re.compile(r"ModuleNotFoundError: No module named '(?P<name>[\w.]+)'"),
    re.compile(
        r"ImportError: cannot import name '(?P<name>\w+)' from "
        r"(?:partially initialized module )?'[\w.]+'(?: \(.*\))?"
    ),
    re.compile(
        r"AttributeError: (?:module '[\w.]+'|'\w+' object|type object '\w+') "
        rf"has no attribute '(?P<name>\w+)'{_SUGGESTION}"
    ),
)


@dataclass(frozen=True)
class FailingTest:
    """One testcase the report holds a failure or an error for.

    `outcome` is ``failed`` (a failure element), ``error`` (an error element:
    a setup or teardown that raised) or ``collection-error`` (the module could
    not be collected). `test_id` is pytest's node id and `line` the 1-based
    line the test's definition starts on; both are ``None`` for a module that
    could not be collected, which is not a test and has no line of its own.
    `path` is the ``file`` the report gives, as pytest wrote it. `exception`
    is the one line naming what was raised, `detail` the report's text for it,
    and `symbol` the missing name :func:`symbol_of` reads from `exception`.
    """

    outcome: str
    name: str
    test_id: str | None
    path: str | None
    line: int | None
    exception: str
    detail: str
    symbol: str | None


def reporting(command: Sequence[str]) -> tuple[str, ...] | None:
    """`command` with the report flags appended, or None when it is not pytest
    or a flag could change what it means."""
    at = _pytest_at(command)
    if at is None:
        return None
    own = command[at + 1 :]
    if "--" in own or any(_names_a_report(arg) for arg in own):
        return None
    if any(a == "no:junitxml" or a == "-pno:junitxml" for a in own):
        return None
    return (*command, *_FLAGS)


def collect(workspace: Path) -> tuple[FailingTest, ...] | None:
    """Read the report out of `workspace` and remove it.

    None when there is none — the command did not write it — and an empty
    tuple when there is one that is not a report this module reads, so a
    caller can tell a command that ignored the flags from one that wrote a
    report with nothing in it.
    """
    path = workspace / REPORT
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    try:
        if not stat.S_ISREG(mode):
            return ()
        try:
            return parse(_read_bounded(path))
        except ValueError:
            # A report written to break the reader is not a report.
            return ()
    finally:
        _remove(path)


def present(workspace: Path) -> bool:
    """Whether anything stands at the report's path already, link or not."""
    return os.path.lexists(workspace / REPORT)


def parse(text: str | None) -> tuple[FailingTest, ...]:
    """The failing testcases of one JUnit XML document, in its order.

    Empty for a document that is not one: unreadable, too large, declaring a
    document type, or with a root that is not a test suite.
    """
    if text is None or "<!DOCTYPE" in text or "<!ENTITY" in text:
        return ()
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ()
    if root.tag not in ("testsuites", "testsuite"):
        return ()
    failing: list[FailingTest] = []
    for case in root.iter("testcase"):
        for child in case:
            if child.tag in ("failure", "error"):
                failing.append(_failing(case, child))
                break
    return tuple(failing)


def symbol_of(exception: str) -> str | None:
    """The missing name in an exception line, when the whole line is one of the
    interpreter's fixed wordings for one, else None."""
    for wording in _MISSING_NAME:
        matched = wording.fullmatch(exception.strip())
        if matched is not None:
            return matched["name"]
    return None


# --- one testcase ------------------------------------------------------------


def _failing(case: ET.Element, child: ET.Element) -> FailingTest:
    message = child.get("message") or ""
    detail = child.text or ""
    file = case.get("file") or None
    if child.tag == "error" and message == _COLLECTION_FAILURE:
        outcome = "collection-error"
        test_id, line = None, None
        name = file or case.get("name") or "a test module"
    else:
        outcome = "failed" if child.tag == "failure" else "error"
        test_id = _node_id(file, case.get("classname") or "", case.get("name") or "")
        line = _line(case.get("line"))
        name = test_id or _joined(case.get("classname"), case.get("name"))
    exception = _exception(message, detail, outcome)
    return FailingTest(
        outcome=outcome,
        name=name,
        test_id=test_id,
        path=file,
        line=line,
        exception=exception,
        detail=detail,
        symbol=symbol_of(exception),
    )


def _node_id(file: str | None, classname: str, name: str) -> str | None:
    """pytest's node id, put back together the way ``mangle_test_address`` took
    it apart: the module path with ``/`` and ``.py`` turned into a dotted
    classname, classes appended to it, the test's name with its parameters
    kept apart. None when the classname does not start with the file's module,
    as when the test is defined in another file than the one it runs from."""
    if not file or not name or not file.endswith(".py"):
        return None
    module = file[: -len(".py")].replace("/", ".")
    if classname == module:
        classes: list[str] = []
    elif classname.startswith(module + "."):
        classes = classname[len(module) + 1 :].split(".")
    else:
        return None
    return "::".join((file, *classes, name))


def _line(raw: str | None) -> int | None:
    # The report's line is 0-based (pytest's item location); a note's is 1-based.
    # Only plain ASCII digits of a sane length: `isdigit` alone also passes
    # `²`, and a long enough run of digits is more than `int` will convert.
    if raw is None or not (raw.isascii() and raw.isdigit()) or len(raw) > 9:
        return None
    return int(raw) + 1


def _joined(classname: str | None, name: str | None) -> str:
    return "::".join(part for part in (classname, name) if part) or "a test"


def _exception(message: str, detail: str, outcome: str) -> str:
    """The one line naming what was raised.

    For a failure, the first line of the message pytest recorded, which is the
    exception as it was raised. For an error, whose message is pytest's own
    sentence ("failed on setup with ..."), the last exception line of the text
    — the error it caught — or that sentence when there is no such line.
    """
    first = message.split("\n", 1)[0].strip()
    if outcome == "failed" and first:
        return first
    for raw in reversed(detail.splitlines()):
        matched = _EXCEPTION_LINE.fullmatch(raw.rstrip())
        if matched is not None:
            return matched["line"]
    return "" if first == _COLLECTION_FAILURE else first


def _names_a_report(arg: str) -> bool:
    # `--junitxml`, `--junit-xml`, `--junit-prefix` and any abbreviation pytest
    # would accept for them.
    return arg.startswith("--junit")


def _pytest_at(command: Sequence[str]) -> int | None:
    """The index of the token that is pytest in `command`, whose own arguments
    follow it, or None when `command` is not pytest."""
    if not command:
        return None
    at = 0
    if PurePosixPath(command[0]).name in _RUNNERS:
        if len(command) < 2 or command[1] != "run":
            return None
        at = 2
        while at < len(command) and command[at].startswith("-"):
            if command[at] not in _RUNNER_SWITCHES and "=" not in command[at]:
                return None
            at += 1
        if at >= len(command):
            return None
    program = PurePosixPath(command[at]).name
    if program in _PYTEST:
        return at
    if _PYTHON.fullmatch(program) and list(command[at + 1 : at + 3]) == [
        "-m",
        "pytest",
    ]:
        return at + 2
    return None


def _read_bounded(path: Path) -> str | None:
    """The file's text, opened without following a link, or None when it is
    larger than :data:`_MAX_REPORT_BYTES` or cannot be read."""
    # Non-blocking, and checked again once open, so a FIFO swapped in after the
    # caller's look at the path can neither block the read nor be read.
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            return None
        raw = handle.read(_MAX_REPORT_BYTES + 1)
    if len(raw) > _MAX_REPORT_BYTES:
        return None
    return raw.decode("utf-8", errors="replace")


def _remove(path: Path) -> None:
    # What cannot be removed here (a directory standing at the path) is left
    # for the restore after the run, which takes away whatever the run added.
    with contextlib.suppress(OSError):
        path.unlink()
