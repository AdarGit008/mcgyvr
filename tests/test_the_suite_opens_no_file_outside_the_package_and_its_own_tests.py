"""The test suite opens no file outside the package and its own tests.

Promise: what every test shares — ``tests/conftest.py`` and whatever it
registers — opens nothing under ``tools/``, ``records/``, ``okf/``,
``fleet-setup/`` or ``archive/``, neither when the suite is collected nor
around a test that runs. Those folders are not part of what a user installs,
so a test that needed them to start would fail for anyone who has only the
package and its tests.

Watched, not read: pytest runs in a subprocess with an audit hook installed
before the conftest is imported, and every open or listing of a path under
those folders is logged against what pytest was doing at that moment
(starting up, collecting a given file, or running a given test).

What "the suite" means here, while the tests of those folders' own code still
sit in this tree: a test module that itself imports from one of those folders
is that module's own business and leaves the tree with the folder. So the
suite is (1) what happens before and between test modules — the shared
conftest and what it pulls in — checked over the whole tree, and (2) staying
tests chosen because they run under every shared fixture (the fresh home, the
``home`` fixture, the offline status reads of the runner), checked from
collection to teardown.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The folders a user of the package does not have.
OUTSIDE = ("tools", "records", "okf", "fleet-setup", "archive")

#: Staying tests that ask the shared fixtures for everything they give and
#: open nothing under :data:`OUTSIDE` themselves.
STAYING = (
    "tests/test_per_rung_width.py",
    "tests/test_a_run_without_a_session_is_refused_before_anything_is_dispatched.py",
)

#: A pytest plugin loaded with ``-p`` — before any conftest — that logs every
#: open and listing under the watched folders, tagged with what pytest was doing.
AUDIT_PLUGIN = """
import json
import os
import sys

_ROOT = os.environ["SUITE_AUDIT_ROOT"]
_WATCHED = tuple(
    os.path.join(_ROOT, name) for name in json.loads(os.environ["SUITE_AUDIT_WATCHED"])
)
_LOG = os.environ["SUITE_AUDIT_LOG"]
_doing = ["starting up"]
_seen = []


def _hook(event, args):
    if event not in ("open", "os.listdir", "os.scandir") or not args:
        return
    path = args[0]
    if hasattr(path, "__fspath__"):
        path = path.__fspath__()
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, str):
        return
    full = os.path.abspath(path)
    for folder in _WATCHED:
        if full == folder or full.startswith(folder + os.sep):
            _seen.append([_doing[0], os.path.relpath(full, _ROOT)])
            return


sys.addaudithook(_hook)


def pytest_collectstart(collector):
    _doing[0] = "collecting " + (collector.nodeid or "<session>")


def pytest_runtest_logstart(nodeid, location):
    _doing[0] = "running " + nodeid


def pytest_unconfigure(config):
    with open(_LOG, "w", encoding="utf-8") as handle:
        json.dump(_seen, handle)
"""


def _audited_pytest(tmp_path: Path, *args: str) -> list[list[str]]:
    """Run pytest over this checkout under the audit plugin; return its log."""
    (tmp_path / "suite_audit.py").write_text(AUDIT_PLUGIN, encoding="utf-8")
    log = tmp_path / "opened.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(tmp_path), env.get("PYTHONPATH", "")) if p
    )
    env["SUITE_AUDIT_ROOT"] = str(REPO)
    env["SUITE_AUDIT_WATCHED"] = json.dumps(OUTSIDE)
    env["SUITE_AUDIT_LOG"] = str(log)
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "suite_audit",
            "-p",
            "no:cacheprovider",
            "-n",
            "0",
            "-q",
            *args,
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert log.is_file(), (
        f"pytest ended before the audit could write its log:\n"
        f"{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    )
    assert done.returncode == 0, f"{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    seen: list[list[str]] = json.loads(log.read_text(encoding="utf-8"))
    return seen


def test_what_every_test_shares_opens_nothing_outside_the_package(
    tmp_path: Path,
) -> None:
    """Collecting the whole tree, nothing under the watched folders is opened
    except while a test module that reaches for them itself is being imported."""
    seen = _audited_pytest(tmp_path, "--collect-only", "tests")
    shared = sorted(
        {
            f"{doing}: {path}"
            for doing, path in seen
            if not (doing.startswith("collecting ") and doing.endswith(".py"))
        }
    )
    assert shared == [], (
        "the shared conftest opened files a user of the package does not have:\n"
        + "\n".join(shared)
    )


def test_a_staying_test_opens_nothing_outside_the_package_from_collection_to_teardown(
    tmp_path: Path,
) -> None:
    """Staying tests, run under every shared fixture, open nothing under the
    watched folders at any point."""
    seen = _audited_pytest(tmp_path, *STAYING)
    opened = sorted({f"{doing}: {path}" for doing, path in seen})
    assert opened == [], (
        "a staying test opened files a user of the package does not have:\n"
        + "\n".join(opened)
    )
