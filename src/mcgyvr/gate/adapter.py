"""The adapter seam: what a language answers about a change, and where its tools
are run.

`LanguageAdapter` is the interface a language backend implements — one file's
syntax and structure, the whole change's lint and format rungs, and where the
repository says its tests and its type check live. Every rung answers in the
same `Finding` shape, so the gate can mix rungs from different languages.

`ToolRunner` is the other half: the tool invocations those rungs make, run
either on this host or inside the task's sandbox, with the paths a tool prints
read back through the same runner so that a finding names a file in the change
and not a path on some machine.

A rung that cannot reach a verdict because the tooling rather than the change
is at fault raises an `EnvironmentFaultError`, which the gate records as an
environment issue or an inconclusive rung, never as a finding.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from mcgyvr.gate.acceptance import DID_NOT_RUN
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.sandbox.base import Sandbox, safe_env


class EnvironmentFaultError(Exception):
    """A rung could not be judged, because the environment it runs in failed.

    The change is not implicated: a caller reports the fault as an environment
    issue, so the run is inconclusive rather than rejected.
    """


class ToolUnavailableError(EnvironmentFaultError):
    """A tool a rung needs is not on PATH, so the rung cannot run at all."""

    def __init__(self, tool: str) -> None:
        super().__init__(f"required tool not found on PATH: {tool}")
        self.tool = tool


class ToolFailedError(EnvironmentFaultError):
    """A tool ran, but exited in a way that leaves its output unreadable.

    `exit_code` is outside the set the caller expected for a report — a crash, a
    usage error, a missing argument — so stdout is not a verdict and `detail`
    carries whatever the tool said about it.
    """

    def __init__(self, tool: str, exit_code: int, detail: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        super().__init__(
            f"{tool} exited {exit_code} and its output cannot be read{suffix}"
        )
        self.tool = tool
        self.exit_code = exit_code
        self.detail = detail


class LanguageAdapter(ABC):
    """What one language has to say about a change.

    `owns` picks the paths this adapter answers for and `name` labels it in a
    report; the rungs then run over those files alone. Syntax and structure are
    asked per file, so a file that does not parse is reported and dropped from
    the rungs that would parse it again; lint and format are asked of the whole
    change, once its files are known to parse. Each rung returns findings
    attributed to the paths and lines the change added, so a worker is never
    charged for code it did not touch. An adapter that shells out does so
    through the `ToolRunner` it was given in `running_in`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The label this adapter's findings and environment issues carry."""

    @abstractmethod
    def owns(self, path: str) -> bool:
        """Whether this adapter is responsible for `path`."""

    @abstractmethod
    def check_syntax(self, change: FileChange, repo: Path) -> list[Finding]:
        """Parse `change`'s file in `repo` and report what does not parse.

        A finding here means the file cannot be read as this language at all,
        so the caller leaves it out of the rungs that would parse it again.
        """

    @abstractmethod
    def structural_checks(
        self, change: FileChange, repo: Path, *, contract_text: str = ""
    ) -> list[Finding]:
        """Report this language's hazards on the lines `change` added.

        `contract_text` is the contract's own prose. It reaches the checks that
        read the worker's stated intent — a function that mutates a parameter it
        was handed is not reported where the contract asks for an in-place
        change.
        """

    @abstractmethod
    def lint(
        self, changes: Sequence[FileChange], repo: Path, *, base: str | None = None
    ) -> list[Finding]:
        """Run the linter over the owned files in `changes`.

        `base` names the revision the change is diffed against; when it is
        given, diagnostics the base tree already produced are dropped, so the
        rung reports only what this change brought in.
        """

    @abstractmethod
    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        """Report where the formatter would reflow a line the change added.

        The formatter is asked for a diff rather than for a rewrite, so the
        check never alters the tree it reads.
        """

    @abstractmethod
    def locate_test_command(self, repo: Path) -> list[str] | None:
        """The argv the repo declares for its tests, or None when it declares none."""

    @abstractmethod
    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        """The type checker the repo declares, as an argv prefix, or None."""

    def running_in(self, runner: ToolRunner) -> LanguageAdapter:
        """Return this adapter with its tool invocations going to `runner`.

        The default returns the adapter unchanged, which suits an adapter that
        does not shell out. One that does returns a copy bound to the runner, so
        a single adapter definition serves both the host and the sandbox.
        """
        return self

    def loads_as_code(self, path: str) -> Mapping[str, str]:
        """Map each rung that loads `path` as code to the tool that does it.

        Empty means no rung executes the file as anything but data, which is the
        answer for most paths. A linter or format config module is the case that
        matters: a caller drops the named rungs rather than hand the worker's
        bytes to a tool that would import them.
        """
        return {}

    def owned(self, changes: Sequence[FileChange]) -> list[FileChange]:
        """The changes this adapter can check.

        That is the paths it owns, minus everything that is not a file to read:
        a deletion, binary content, and a symlink, which the checkers would
        follow out of the tree.
        """
        return [
            c
            for c in changes
            if self.owns(c.path)
            and not c.is_deletion
            and not c.is_binary
            and not c.is_link
        ]


def require_tool(tool: str) -> str:
    """Return the path of `tool` on PATH, or raise `ToolUnavailableError`."""
    found = shutil.which(tool)
    if found is None:
        raise ToolUnavailableError(tool)
    return found


def trusted_stdout(
    tool: str,
    proc: subprocess.CompletedProcess[str],
    *,
    expected: Sequence[int],
) -> str:
    """Return a tool's stdout, or raise instead of reading a verdict out of it.

    `expected` lists the exit codes that mean the tool ran and printed its
    report — 0 for clean, 1 for "I found something". Any other code is a broken
    invocation, so its first complaint on stderr becomes the error and stdout is
    never parsed.
    """
    if proc.returncode in expected:
        return proc.stdout
    raise ToolFailedError(tool, proc.returncode, _first_complaint(proc.stderr))


#: How much of a tool's own complaint is kept when it is attached to an error:
#: enough for a message a reader can act on, short enough to sit in a report or
#: in a line of a model's context.
_DETAIL_LIMIT = 200


def added_by_resolved_path(
    changes: Sequence[FileChange], repo: Path
) -> dict[Path, tuple[str, frozenset[int]]]:
    """Index `changes` by resolved path, for matching what a checker printed.

    A checker reports the absolute path it walked, which is not the path the
    change names — the repository may be reached through a symlink, and a
    sandbox reports its own view. Resolution is what both sides can agree on.
    Each value is the repo-relative path the finding should carry, beside the
    added line numbers that decide whether a diagnostic belongs to the change.
    """
    return {(repo / c.path).resolve(): (c.path, c.added_lines) for c in changes}


def _first_complaint(stderr: str) -> str:
    """Return the first non-blank line of `stderr`, capped at `_DETAIL_LIMIT`.

    A tool states what went wrong before the context that follows it, and the
    surrounding blank lines say nothing, so the first line with content in it is
    the one worth quoting.
    """
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_DETAIL_LIMIT]
    return ""


#: Variables that ask a tool for colour whatever its output is attached to. They
#: are removed from a checker's environment rather than set to "0" — some tools
#: read any value as wanting colour — and `NO_COLOR` is set in their place, so
#: nothing a checker prints carries ANSI escapes into a finding's message.
_COLOUR_FORCING = ("FORCE_COLOR", "CLICOLOR_FORCE")


def plain_env() -> dict[str, str]:
    """The environment a checker is run in: no colour, no caches, no secrets.

    The inherited environment is filtered through `safe_env`, so a credential
    never reaches a tool. Colour-forcing variables are dropped and `NO_COLOR`
    set, because escapes would otherwise land in parsed diagnostics. Ruff's and
    mypy's caches are sent to the null device, so no run inherits the results of
    the last one.
    """
    env = safe_env({k: v for k, v in os.environ.items() if k not in _COLOUR_FORCING})
    env["NO_COLOR"] = "1"
    env["RUFF_NO_CACHE"] = "true"
    env["MYPY_CACHE_DIR"] = os.devnull
    return env


# Where a check runs. Every rung that shells out does so through a runner, so
# the same adapter serves the host and the sandbox: `HostRunner` runs a tool
# over the tree in place, and `SandboxRunner` runs it inside the task's
# workspace, where the change lives. The seam covers the three things that
# differ between them — running a tool, reading back a path a tool printed, and
# handing out a directory a checker may write into. A reported path needs
# translating because a sandbox prints its own view of the filesystem, and a
# finding carrying one would name no file in the change; a scratch directory
# has to sit inside that view for the same reason, or the tool cannot see it.
# A tool that is missing, or that exits in a way its output cannot be read
# from, raises an `EnvironmentFaultError` through either runner, so a caller
# handles the environment the same way wherever the check happened.


class ToolRunner(ABC):
    """Where a rung's tool invocations happen.

    A rung asks its runner rather than `subprocess` directly, which is what lets
    the same adapter read a tree here and read the change in a sandbox there:
    `run` executes a tool, `host_path` reads a printed path back into this
    filesystem, and `scratch` hands out a directory a checker may write into.
    """

    @abstractmethod
    def run(
        self,
        tool: str,
        args: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run `tool` with `args` in `cwd` and capture its text output.

        `timeout` bounds the run and a tool that outlives it raises
        `subprocess.TimeoutExpired`. A non-zero exit code is a result rather
        than an exception here: only the caller knows which codes it can read.
        """

    def host_path(self, reported: str) -> Path:
        """Where a path a tool printed lives, as this side of the runner has it.

        The base answer is the path itself, which is right for a tool run on the
        host. A sandbox overrides this to map its own view back onto this host.
        """
        return Path(reported)

    @contextmanager
    def scratch(self) -> Iterator[Path]:
        """Yield a temporary directory a checker may write into.

        The base version sits in the system temporary directory and is removed
        on exit: nothing outside this process needs to see it.
        """
        with tempfile.TemporaryDirectory(prefix="mcgyvr-check-") as name:
            yield Path(name)


class HostRunner(ToolRunner):
    """A runner that executes tools on this host, over the tree as it stands.

    The tool is resolved on PATH through `require_tool`, so a checker that is
    not installed fails as an environment fault before anything is spawned, and
    the child gets `plain_env` rather than the caller's environment.
    """

    def run(
        self,
        tool: str,
        args: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [require_tool(tool), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=plain_env(),
            timeout=timeout,
            check=False,
        )


class SandboxRunner(ToolRunner):
    """A runner that executes tools inside a sandbox's workspace.

    The command runs through the sandbox's own `run`, with `cwd` expressed
    relative to the workspace root. Paths the tools print are the workspace's
    own, so `host_path` translates them before a finding quotes one.
    """

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def run(
        self,
        tool: str,
        args: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        sandbox = self._sandbox
        within = cwd.resolve().relative_to(sandbox.workspace.resolve()).as_posix()
        argv = [tool, *args]
        env = _checker_env(sandbox)
        if within == ".":
            result = sandbox.run(argv, timeout=timeout, env=env)
        else:
            result = sandbox.run(argv, timeout=timeout, env=env, cwd=within)
        if result.timed_out:
            raise subprocess.TimeoutExpired(
                argv, timeout or 0.0, output=result.stdout, stderr=result.stderr
            )
        # A sandbox that cannot find the program reports it the way a shell
        # does — 126 or 127 with nothing on stdout — so the tool is missing
        # rather than having said something about the change.
        if result.exit_code in DID_NOT_RUN and not result.stdout:
            raise ToolUnavailableError(tool)
        return subprocess.CompletedProcess(
            argv, result.exit_code, result.stdout, result.stderr
        )

    def host_path(self, reported: str) -> Path:
        return self._sandbox.host_path(reported)

    @contextmanager
    def scratch(self) -> Iterator[Path]:
        # The workspace is all a sandboxed tool can see, so the directory has to
        # be made inside it; the dot prefix keeps it out of the way of a listing
        # of the tree, and `TemporaryDirectory` removes it on exit so it cannot
        # end up inside a diff of the workspace.
        with tempfile.TemporaryDirectory(
            prefix=".mcgyvr-check-", dir=self._sandbox.workspace
        ) as name:
            yield Path(name)


def _checker_env(sandbox: Sandbox) -> dict[str, str]:
    """The whole environment a checker is given inside the sandbox.

    `Sandbox.run` passes `env` through as the complete environment, so only what
    a checker reads is set here: colour is turned off in both the spellings a
    tool might test, and the type checker's cache goes to a null device. A
    container has `/dev/null` at that path; a checker running against a host
    directory uses the host's own null device.
    """
    devnull = "/dev/null" if sandbox.isolation == "container" else os.devnull
    return {
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "CLICOLOR_FORCE": "0",
        "MYPY_CACHE_DIR": devnull,
    }
