"""The installed wheel runs offline, with no checkout beside it.

A stranger installs the wheel and nothing else: no development repository and
nothing of its trees, no network beyond their own machines. So the wheel
is built here from the product alone (the sources, the data, the metadata;
:func:`tests.test_the_engine_the_gate_runs_is_packaged_and_matches_its_pin_from_the_package_alone._product_alone`),
installed into a fresh virtual environment under a temporary folder, with its
dependencies at the versions ``uv.lock`` pins, and run from a folder outside
any checkout, with a home of its own and no ``MCGYVR_*`` variable and nothing
of this checkout on ``PATH``.

What must be observably true, from that install:

* ``mcgyvr`` is imported from the environment, not from this checkout, and
  every module of it imports;
* the commands that need neither a rig nor the network answer: ``--help``,
  ``--version``, ``capabilities``, ``catalog``, ``contract``, ``init`` with a
  hosted unit bound by hand, then ``config``, ``pool`` and ``index`` against
  what ``init`` wrote;
* none of them writes inside the installed environment;
* a telemetry row written from the install carries ``$MCGYVR_RUN_TAGS`` under
  ``run_tags`` when the variable is set, and neither tags nor a round when it
  is not: the install has no checkout to read a round from. None of the
  commands above writes a row (only ``run`` does, and the run below is judged
  by its attempt, not its row), so this calls
  :func:`mcgyvr.telemetry.observe` from the installed interpreter;
* the hub client's data travels with it: the seccomp profile a pooled
  session's containers run under is read from the installed ``mcgyvr.rig``.

And a fresh ``init`` runs a contract with nothing from the development
repository: ``init`` writes ``profile: live`` and approves the user's own fleet
of what it bound, so live admission lets the run through, and the run gets as
far as an attempt at the unit ``init`` bound, read from the run's result and
from the listener that took it. That unit is hosted at a public name in a
domain reserved for examples, which ``init`` approves as it would a provider's
and does not look up. The run's process alone resolves that one name to a
loopback listener of the test's own (:data:`_RESOLVING_HOSTED_HERE`): the
offline stand-in for the internet, as a substituted detection is for a machine.
The listener answers at once with a server error, so the attempt ends without
waiting on any timeout and nothing leaves the machine. A loopback address bound
as hosted would be refused approval: it is a machine of the user's.

The wheel is built and installed once per test session, also when the session
runs on several workers: the first worker builds it under a lock in the
session's shared temporary folder, the others wait and use it.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.test_a_row_carries_the_run_tags_its_environment_names import (
    _OUTSIDE,
    TAGS,
)
from tests.test_every_module_of_the_package_imports_under_every_supported_python import (  # noqa: E501
    _IMPORT_ALL,
    _WALK_ENDED,
)
from tests.test_the_engine_the_gate_runs_is_packaged_and_matches_its_pin_from_the_package_alone import (  # noqa: E501
    _product_alone,
    _uv,
)

REPO = Path(__file__).resolve().parents[1]

#: The longest one command may take. Nothing here waits on a network; ``init``
#: probes the local ports a backend would answer on, each with a short timeout.
_COMMAND_TIMEOUT_S = 120

#: A model contract, valid and never dispatched to anything that answers.
CONTRACT = """\
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
acceptance: ["sh -c 'exit 0'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

#: The variable that holds the hosted unit's key; set only where a run should
#: find the unit usable.
KEY_ENV = "MCGYVR_TEST_HOSTED_KEY"

#: The unit ``init`` binds, by name as ``init`` names it.
HOSTED_NAME = "api_claude-opus-5"


#: Where the hosted unit is: a public name under a domain reserved for examples
#: (RFC 2606), so no resolver anywhere answers it with a real machine.
HOSTED_HOST = "api.hosted.example"


def _hosted(address: str) -> str:
    """A hosted unit bound by hand at ``address``: ``init`` writes it without
    reaching it."""
    return f"model=claude-opus-5,address={address},api_key_env={KEY_ENV}"


#: The hosted unit of the commands that dispatch nothing.
HOSTED_UNIT = _hosted(f"https://{HOSTED_HOST}/v1")

#: ``mcgyvr`` from the installed package, run as its console script runs it,
#: with :data:`HOSTED_HOST` alone resolved to this machine's loopback: a
#: resolver substituted in the test's own process, nothing of the product's.
_RESOLVING_HOSTED_HERE = f"""\
import socket
import sys

_resolve = socket.getaddrinfo


def _here(host, *args, **kwargs):
    return _resolve("127.0.0.1" if host == {HOSTED_HOST!r} else host, *args, **kwargs)


socket.getaddrinfo = _here
from mcgyvr.cli import main

sys.exit(main(sys.argv[1:]))
"""


class _Listener(ThreadingHTTPServer):
    """A loopback listener that keeps the path of each request it took."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ServerError)
        self.asked: list[str] = []


class _ServerError(BaseHTTPRequestHandler):
    """Answers each dispatch at once with a server error, once its body is read."""

    server: _Listener

    def do_POST(self) -> None:
        self.server.asked.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = b'{"error": {"message": "no model answers here"}}'
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet: the run's result says what was asked."""


@pytest.fixture
def listener() -> Iterator[_Listener]:
    """A loopback listener of this test's own (:class:`_ServerError`).

    A dispatch to it ends at once whatever the unit's request timeout, where a
    closed port could be filtered and wait it out, and a fixed one could be
    held by some other listener."""
    server = _Listener()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@dataclass(frozen=True)
class Installed:
    """A wheel installed into an environment of its own."""

    venv: Path
    site: Path

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def mcgyvr(self) -> Path:
        return self.venv / "bin" / "mcgyvr"

    def env(self, home: Path, **extra: str) -> dict[str, str]:
        """Only what a stranger's shell would have: a home, a locale and a
        ``PATH`` that starts at this environment and holds nothing of the
        checkout. No ``MCGYVR_*`` variable, no session."""
        path = [str(self.venv / "bin")]
        path += [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        return {
            "PATH": os.pathsep.join(p for p in path if _outside_the_checkout(p)),
            "HOME": str(home),
            "LANG": "C.UTF-8",
            **extra,
        }


def _run(
    work: Path, env: dict[str, str], *argv: str | Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(a) for a in argv],
        cwd=work,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_COMMAND_TIMEOUT_S,
        check=False,
    )


def _ran(done: subprocess.CompletedProcess[str]) -> str:
    """What a command was, what it answered and how it exited; a program passed
    with ``-c`` is shown by its first line only."""
    argv = [str(a).strip().splitlines()[0] if a else "" for a in done.args]
    return f"{argv} exited {done.returncode}:\n{done.stdout}{done.stderr}"


def _uv_run(*argv: str | Path, cwd: Path) -> None:
    done = subprocess.run(
        [_uv(), *(str(a) for a in argv)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 0, _ran(done)


def _outside_the_checkout(path: str) -> bool:
    resolved = Path(path).resolve()
    return resolved != REPO and REPO not in resolved.parents


def _install(root: Path) -> Installed:
    """Build the wheel from the product alone and install it under ``root``."""
    tree = _product_alone(root)
    dist = root / "dist"
    _uv_run("build", "--wheel", "--out-dir", dist, cwd=tree)
    (wheel,) = sorted(dist.glob("*.whl"))

    # The dependencies at the versions the lock pins, so the install is the
    # one CI tests and not whatever an index serves today.
    pins = root / "requirements.txt"
    _uv_run(
        "export",
        "--frozen",
        "--no-dev",
        "--no-emit-project",
        "--no-hashes",
        "--output-file",
        pins,
        cwd=REPO,
    )
    venv = root / "venv"
    _uv_run("venv", "--quiet", "--python", sys.executable, venv, cwd=root)
    _uv_run(
        "pip",
        "install",
        "--quiet",
        "--python",
        venv / "bin" / "python",
        "--requirement",
        pins,
        wheel,
        cwd=root,
    )
    (site,) = (venv / "lib").glob("python3*/site-packages")
    return Installed(venv=venv, site=site)


@pytest.fixture(scope="session")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Installed:
    """One install per session. Under xdist every worker's temporary folder
    sits in one folder of the session's; the install goes there, built by the
    first worker to take the lock."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        shared = tmp_path_factory.getbasetemp().parent / "installed-wheel"
    else:
        shared = tmp_path_factory.mktemp("installed-wheel")
    assert _outside_the_checkout(str(shared)), shared
    shared.mkdir(exist_ok=True)
    ready = shared / "ready"
    with (shared.parent / f"{shared.name}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not ready.is_file():
            done = _install(shared)
            ready.write_text(str(done.site), encoding="utf-8")
    return Installed(venv=shared / "venv", site=Path(ready.read_text(encoding="utf-8")))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
    )


def _a_repository(where: Path) -> Path:
    repo = where / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _installed_files(site: Path) -> set[Path]:
    return {p for p in site.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def _a_place(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A home, and a work folder holding the contract and a repository."""
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    (work / "impl.yaml").write_text(CONTRACT, encoding="utf-8")
    return home, work, _a_repository(work)


def test_the_installed_wheel_answers_every_offline_command(
    installed: Installed, tmp_path: Path
) -> None:
    before = _installed_files(installed.site)
    home, work, repo = _a_place(tmp_path)
    env = installed.env(home)

    which = _run(
        work, env, installed.python, "-I", "-c", "import mcgyvr; print(mcgyvr.__file__)"
    )
    assert which.returncode == 0, _ran(which)
    assert installed.site in Path(which.stdout.strip()).resolve().parents, _ran(which)

    walked = _run(work, env, installed.python, "-I", "-c", _IMPORT_ALL)
    assert walked.returncode == 0 and _WALK_ENDED in walked.stdout, _ran(walked)

    # Each command, and a word its answer holds. In order: `init` writes the
    # config the three after it read.
    expected: list[tuple[tuple[str | Path, ...], str]] = [
        (("--help",), "usage: mcgyvr"),
        (("--version",), "mcgyvr "),
        (("capabilities",), "Shipped models"),
        (("catalog",), "Task types"),
        (("contract", "impl.yaml"), "valid"),
        (("setup", "--api", HOSTED_UNIT), "Wrote"),
        (("config",), "valid"),
        (("local_pool",), "usable rung"),
        (("index", repo), "Indexed"),
    ]
    failed = []
    for argv, word in expected:
        done = _run(work, env, installed.mcgyvr, *argv)
        if done.returncode != 0 or word not in done.stdout:
            failed.append(_ran(done))
    assert not failed, "\n\n".join(failed)
    assert (work / "fleet.yaml").is_file()

    wrote = sorted(_installed_files(installed.site) - before)
    assert not wrote, f"a command wrote inside the installed package: {wrote}"


@pytest.mark.parametrize("tagged", [False, True], ids=["no-env", "env"])
def test_a_row_written_from_the_install_carries_only_the_tags_it_was_given(
    installed: Installed, tmp_path: Path, tagged: bool
) -> None:
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    sink = tmp_path / "journal" / "a.jsonl"
    extra = {"MCGYVR_RUN_TAGS": json.dumps(TAGS)} if tagged else {}
    env = installed.env(home, **extra)

    done = _run(
        work,
        env,
        installed.python,
        "-I",
        "-c",
        _OUTSIDE.replace("SINK", repr(str(sink))),
    )

    assert done.returncode == 0, _ran(done)
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert installed.site in Path(out["file"]).resolve().parents, out["file"]
    row = out["row"]
    assert "round" not in row, row
    assert "product_sha256" not in row, row
    if tagged:
        assert row["run_tags"] == TAGS, row
    else:
        assert "run_tags" not in row, row


#: Loads the pooled sessions' seccomp profile the way the hub client does, from
#: the installed package, and prints where it was read and what it allows.
_SECCOMP_PROBE = """
import json
from mcgyvr.rig import pooled
profile = json.loads(pooled.SECCOMP_PROFILE.read_text(encoding="utf-8"))
print(pooled.SECCOMP_PROFILE.resolve())
print(profile["defaultAction"], len(profile["syscalls"]))
"""


def test_the_installed_hub_client_reads_its_seccomp_profile_from_the_package(
    installed: Installed, tmp_path: Path
) -> None:
    home, work, _ = _a_place(tmp_path)
    done = _run(work, installed.env(home), installed.python, "-I", "-c", _SECCOMP_PROBE)
    assert done.returncode == 0, _ran(done)
    where, allows = done.stdout.splitlines()
    rig = (installed.site / "mcgyvr" / "rig").resolve()
    assert Path(where).parent == rig, _ran(done)
    assert allows.startswith("SCMP_ACT_ERRNO "), _ran(done)


def test_a_fresh_init_runs_a_contract_without_evidence_from_the_dev_repo(
    installed: Installed, tmp_path: Path, listener: _Listener
) -> None:
    home, work, repo = _a_place(tmp_path)
    env = installed.env(home, **{KEY_ENV: "unused"})
    address = f"http://{HOSTED_HOST}:{listener.server_address[1]}"
    init = _run(work, env, installed.mcgyvr, "setup", "--api", _hosted(address))
    assert init.returncode == 0 and "Approved your own fleet" in init.stdout, _ran(init)

    done = _run(
        work,
        env,
        installed.python,
        "-I",
        "-c",
        _RESOLVING_HOSTED_HERE,
        "run",
        "impl.yaml",
        "--repo",
        repo,
        "--orchestrator",
        "t",
        "--sandbox",
        "tempdir",
    )
    results = [
        line.removeprefix("result: ")
        for line in done.stdout.splitlines()
        if line.startswith("result: ")
    ]
    assert len(results) == 1, _ran(done)
    result = json.loads(Path(results[0]).read_text(encoding="utf-8"))
    rungs = [attempt.get("rung") for attempt in result.get("attempts") or []]
    assert rungs and rungs[0] == HOSTED_NAME, (
        f"the run made no attempt at {HOSTED_NAME}: {result.get('detail')}\n"
        + _ran(done)
    )
    assert any(path.endswith("/chat/completions") for path in listener.asked), (
        f"the listener took no dispatch: {listener.asked}\n" + _ran(done)
    )
