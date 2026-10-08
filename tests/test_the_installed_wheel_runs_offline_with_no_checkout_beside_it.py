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
* none of them writes inside the installed environment.

One thing that should be true is not yet, and is a strict, dated xfail: a
fresh ``init`` writes ``profile: live``, and a live run is refused until a
fleet is locked from dev evidence that only the development repository
produces. ``mcgyvr init`` approving the user's own fleet (borders plan, step
2c) turns it green, and the marker comes off then.

A command that reaches a model needs a model, so ``run`` is driven only as far
as the refusal; nothing here dispatches.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

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

#: A model contract, valid and never dispatched.
CONTRACT = """\
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

#: A hosted unit bound by hand: ``init`` writes it without reaching it, and its
#: address routes nowhere by standard. The key variable is one nobody sets.
HOSTED_UNIT = (
    "model=claude-opus-5,address=https://api.example.invalid,"
    "api_key_env=MCGYVR_TEST_KEY_NOBODY_SETS"
)


@dataclass(frozen=True)
class Installed:
    """A wheel installed into an environment of its own, and a place to run it."""

    venv: Path
    site: Path
    work: Path
    env: dict[str, str]

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def mcgyvr(self) -> Path:
        return self.venv / "bin" / "mcgyvr"

    def run(self, *argv: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(a) for a in argv],
            cwd=self.work,
            env=self.env,
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


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Installed:
    root = tmp_path_factory.mktemp("installed")
    assert _outside_the_checkout(str(root)), root
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

    home = root / "home"
    work = root / "work"
    home.mkdir()
    work.mkdir()
    path = [str(venv / "bin")]
    path += [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    env = {
        "PATH": os.pathsep.join(p for p in path if _outside_the_checkout(p)),
        "HOME": str(home),
        "LANG": "C.UTF-8",
    }
    return Installed(venv=venv, site=site, work=work, env=env)


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


def test_the_installed_wheel_answers_every_offline_command(
    installed: Installed,
) -> None:
    before = _installed_files(installed.site)
    work = installed.work / "offline"
    work.mkdir()
    installed = replace(installed, work=work)
    (work / "impl.yaml").write_text(CONTRACT, encoding="utf-8")
    repo = _a_repository(work)

    which = installed.run(
        installed.python, "-I", "-c", "import mcgyvr; print(mcgyvr.__file__)"
    )
    assert which.returncode == 0, _ran(which)
    assert installed.site in Path(which.stdout.strip()).resolve().parents, _ran(which)

    walked = installed.run(installed.python, "-I", "-c", _IMPORT_ALL)
    assert walked.returncode == 0 and _WALK_ENDED in walked.stdout, _ran(walked)

    # Each command, and a word its answer holds. In order: `init` writes the
    # config the three after it read.
    expected: list[tuple[tuple[str | Path, ...], str]] = [
        (("--help",), "usage: mcgyvr"),
        (("--version",), "mcgyvr "),
        (("capabilities",), "Shipped models"),
        (("catalog",), "Task types"),
        (("contract", "impl.yaml"), "valid"),
        (("init", "--api", HOSTED_UNIT), "Wrote"),
        (("config",), "valid"),
        (("pool",), "usable rung"),
        (("index", repo), "Indexed"),
    ]
    failed = []
    for argv, word in expected:
        done = installed.run(installed.mcgyvr, *argv)
        if done.returncode != 0 or word not in done.stdout:
            failed.append(_ran(done))
    assert not failed, "\n\n".join(failed)
    assert (work / "fleet.yaml").is_file()

    wrote = sorted(_installed_files(installed.site) - before)
    assert not wrote, f"a command wrote inside the installed package: {wrote}"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "2026-10-08: owed — borders plan step 2c. A fresh `init` writes "
        "`profile: live`, and live admission refuses every run until a fleet "
        "is locked from dev evidence only the development repository "
        "produces. `mcgyvr init` approving the user's own fleet turns this "
        "green; then the marker comes off."
    ),
)
def test_a_fresh_init_runs_a_contract_without_evidence_from_the_dev_repo(
    installed: Installed,
) -> None:
    work = installed.work / "fresh"
    work.mkdir()
    installed = replace(installed, work=work)
    (work / "impl.yaml").write_text(CONTRACT, encoding="utf-8")
    repo = _a_repository(work)
    init = installed.run(installed.mcgyvr, "init", "--api", HOSTED_UNIT)
    assert init.returncode == 0, _ran(init)

    done = installed.run(
        installed.mcgyvr,
        "run",
        "impl.yaml",
        "--repo",
        repo,
        "--orchestrator",
        "t",
        "--sandbox",
        "tempdir",
    )
    assert "live admission" not in done.stderr, _ran(done)
