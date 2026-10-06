"""What every test shares opens nothing outside the package and the tests.

Promise: ``tests/conftest.py`` and whatever it pulls in open nothing under
``tools/``, ``records/``, ``fleet-setup/`` or ``archive/``, neither
when the tests are collected nor around a test that runs, nor when a test asks
for any fixture the conftest offers. Those folders are not part of what a user
installs, so a shared fixture that needed them would fail for anyone who has
only the package and its tests.

Watched, not read: pytest runs in a subprocess with a Python audit hook
installed before the conftest is imported. The hook sees the ``open``,
``os.listdir`` and ``os.scandir`` audit events of that process. A path given
relative to a directory descriptor (``os.open(name, dir_fd=...)``, which is
how ``shutil.rmtree`` walks a tree) is resolved against that directory, not
against the working directory, and a path through a symbolic link is also
resolved to where the link points. Each hit is logged with what pytest was
doing at that moment: starting up, collecting a given file, or running a given
test.

What it does not see, stated so nobody reads it as more: a child process
(the hook lives in one interpreter, and a program a fixture starts reads
without it); a check that only asks whether a path exists or for its metadata
(``os.stat`` and ``os.path.exists`` raise no audit event); and, where
``/proc`` is absent, the target of a ``dir_fd`` open, which is then not
attributed at all; and the builtin ``open(name, opener=...)`` whose opener
opens relative to a directory descriptor, whose audit event is raised before
the wrapper runs, so a relative name opened that way is taken as relative to
the working directory. Nothing in the package or its tests passed an
``opener`` when this was written.

What is checked, while tests of those folders' own code still sit in this
tree: a test module that itself imports from one of those folders is that
module's own business and leaves with the folder. So the checks are (1) what
happens outside the import of any test module, over the whole tree; (2) staying
tests chosen because they run under every autouse fixture and the ``home``
fixture, from collection to teardown; (3) one generated test that asks for
every fixture the loaded conftest module offers.

Every inner run gets its own ``--basetemp`` under the outer test's
``tmp_path``, so pytest's clean-up of old numbered temp folders elsewhere on
the machine never runs inside the audit. Time: how long the
inner runs take depends on the machine and its load; collecting the whole tree
is the slowest, since it imports every test module once. Each inner run is
capped at :data:`INNER_TIMEOUT_S` seconds, and a run over the cap fails the
test with ``subprocess.TimeoutExpired``, whose message says the command timed
out after that many seconds.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from _pytest.fixtures import getfixturemarker

REPO = Path(__file__).resolve().parent.parent
CONFTEST = REPO / "tests" / "conftest.py"

#: The folders a user of the package does not have.
OUTSIDE = ("tools", "records", "fleet-setup", "archive")

#: The longest one inner run may take before the test fails.
INNER_TIMEOUT_S = 600

#: Staying tests that run under every autouse fixture and the ``home`` fixture
#: and open nothing under :data:`OUTSIDE` themselves.
STAYING = (
    "tests/test_per_rung_width.py",
    "tests/test_a_run_without_a_session_is_refused_before_anything_is_dispatched.py",
)

#: A pytest plugin loaded with ``-p`` — before any conftest — that logs every
#: audited open and listing under the watched folders, tagged with what pytest
#: was doing. Importing it installs the hook; ``pytest_unconfigure`` writes the
#: log, and a caller outside pytest may call it itself.
AUDIT_PLUGIN = """
import json
import os
import sys
import threading

_ROOT = os.environ["SUITE_AUDIT_ROOT"]
_WATCHED = []
for _name in json.loads(os.environ["SUITE_AUDIT_WATCHED"]):
    for _form in (os.path.abspath, os.path.realpath):
        _folder = _form(os.path.join(_ROOT, _name))
        if _folder not in _WATCHED:
            _WATCHED.append(_folder)
_LOG = os.environ["SUITE_AUDIT_LOG"]
_doing = ["starting up"]
_seen = []
_resolved = threading.local()
_real_open = os.open


def _directory_of(fd):
    try:
        return os.readlink("/proc/self/fd/%d" % fd)
    except OSError:
        return None


def _open(path, flags, mode=0o777, *, dir_fd=None):
    # The audit event carries the bare name and not the directory it is
    # relative to, so the full path is worked out here and handed to the hook.
    if dir_fd is not None:
        name = os.fsdecode(os.fspath(path))
        if not os.path.isabs(name):
            base = _directory_of(dir_fd)
            _resolved.path = os.path.join(base, name) if base is not None else False
    try:
        return _real_open(path, flags, mode, dir_fd=dir_fd)
    finally:
        _resolved.path = None


os.open = _open


def _watched_form(full):
    for form in (full, os.path.realpath(full)):
        for folder in _WATCHED:
            if form == folder or form.startswith(folder + os.sep):
                return form
    return None


def _hook(event, args):
    if event not in ("open", "os.listdir", "os.scandir") or not args:
        return
    override = getattr(_resolved, "path", None)
    if override is False:
        return
    path = override if override is not None else args[0]
    if hasattr(path, "__fspath__"):
        path = path.__fspath__()
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, str):
        return
    hit = _watched_form(os.path.abspath(path))
    if hit is not None:
        _seen.append([_doing[0], os.path.relpath(hit, os.path.realpath(_ROOT))])


sys.addaudithook(_hook)


def pytest_collectstart(collector):
    _doing[0] = "collecting " + (collector.nodeid or "<session>")


def pytest_runtest_logstart(nodeid, location):
    _doing[0] = "running " + nodeid


def pytest_unconfigure(config):
    with open(_LOG, "w", encoding="utf-8") as handle:
        json.dump(_seen, handle)
"""


def _audit_env(tmp_path: Path, root: Path) -> tuple[dict[str, str], Path]:
    (tmp_path / "suite_audit.py").write_text(AUDIT_PLUGIN, encoding="utf-8")
    log = tmp_path / "opened.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(tmp_path), env.get("PYTHONPATH", "")) if p
    )
    env["SUITE_AUDIT_ROOT"] = str(root)
    env["SUITE_AUDIT_WATCHED"] = json.dumps(OUTSIDE)
    env["SUITE_AUDIT_LOG"] = str(log)
    return env, log


def _logged(log: Path, done: subprocess.CompletedProcess[str]) -> list[list[str]]:
    assert log.is_file(), (
        f"the run ended before the audit could write its log:\n"
        f"{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    )
    assert done.returncode == 0, f"{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    seen: list[list[str]] = json.loads(log.read_text(encoding="utf-8"))
    return seen


def _audited_pytest(tmp_path: Path, *args: str) -> list[list[str]]:
    """Run pytest over this checkout under the audit plugin; return its log."""
    env, log = _audit_env(tmp_path, REPO)
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
            "--basetemp",
            str(tmp_path / "inner-basetemp"),
            *args,
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=INNER_TIMEOUT_S,
        check=False,
    )
    return _logged(log, done)


def _run_the_hook(
    tmp_path: Path, root: Path, script: str, before: str = ""
) -> list[list[str]]:
    """Run ``before``, then install the audit hook, then run ``script``, in a
    fresh interpreter with ``root`` standing for the repository; return what
    the hook logged."""
    env, log = _audit_env(tmp_path, root)
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            f"{before}\nimport suite_audit\n{script}\n"
            "suite_audit.pytest_unconfigure(None)",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=INNER_TIMEOUT_S,
        check=False,
    )
    return _logged(log, done)


def _fixtures_the_conftest_defines() -> list[str]:
    """Every fixture the loaded conftest offers, under the name a test asks for
    it by: defined there, imported into it, or decorated however it was
    spelled. A ``pytest_plugins`` line would offer fixtures this cannot list,
    so it is refused by name."""
    conftest = importlib.import_module("tests.conftest")
    assert not hasattr(conftest, "pytest_plugins"), (
        f"{CONFTEST} names pytest_plugins {conftest.pytest_plugins!r}; the "
        "fixtures those plugins offer are not read by this test"
    )
    names = []
    for attribute, value in vars(conftest).items():
        if getfixturemarker(value) is None:
            continue
        names.append(str(getattr(value, "name", None) or attribute))
    return sorted(set(names))


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
    """Staying tests, run under every autouse fixture, open nothing under the
    watched folders at any point."""
    seen = _audited_pytest(tmp_path, *STAYING)
    opened = sorted({f"{doing}: {path}" for doing, path in seen})
    assert opened == [], (
        "a staying test opened files a user of the package does not have:\n"
        + "\n".join(opened)
    )


def test_asking_for_every_fixture_the_conftest_defines_opens_nothing_outside(
    tmp_path: Path,
) -> None:
    """A test that asks for every fixture of the conftest, the ones a test must
    request as well as the autouse ones, opens nothing under the watched
    folders."""
    fixtures = _fixtures_the_conftest_defines()
    assert fixtures, "no fixture was found in the conftest; the reader is wrong"
    generated = tmp_path / "generated" / "test_asks_for_every_fixture.py"
    generated.parent.mkdir()
    generated.write_text(
        f"def test_asks_for_every_fixture({', '.join(fixtures)}):\n    pass\n",
        encoding="utf-8",
    )
    seen = _audited_pytest(tmp_path, "-p", "tests.conftest", str(generated))
    opened = sorted({f"{doing}: {path}" for doing, path in seen})
    assert opened == [], (
        f"asking for {fixtures} opened files a user of the package does not "
        "have:\n" + "\n".join(opened)
    )


def test_removing_an_old_temp_tree_with_folders_named_like_the_watched_ones_is_no_hit(
    tmp_path: Path,
) -> None:
    """Removing an old temp tree elsewhere that holds folders named like the
    watched ones, with the repository as the working directory, logs nothing:
    the names ``shutil.rmtree`` opens relative to a directory descriptor are
    not taken for the repository's folders. ``shutil`` is imported before the
    hook, as it is under pytest. Whether the platform lets ``rmtree`` walk by
    descriptor is read before the hook replaces ``os.open``; where it does, the
    script asserts that ``rmtree`` walks by descriptor, so this cannot pass by
    never opening a name relative to one."""
    root = tmp_path / "root"
    for name in OUTSIDE:
        (root / name).mkdir(parents=True)
    stale = tmp_path / "stale" / "pytest-1" / "checkout"
    for name in OUTSIDE:
        (stale / name).mkdir(parents=True)
        (stale / name / "file.txt").write_text("old\n", encoding="utf-8")
    seen = _run_the_hook(
        tmp_path,
        root,
        "\n".join(
            [
                "if BY_FD:",
                "    assert shutil._use_fd_functions, 'rmtree walks by full path'",
                f"shutil.rmtree({str(tmp_path / 'stale')!r})",
            ]
        ),
        before=(
            "import os\n"
            "BY_FD = os.open in os.supports_dir_fd and os.scandir in os.supports_fd\n"
            "import shutil"
        ),
    )
    assert seen == []


def test_the_hook_sees_each_way_a_file_under_a_watched_folder_is_reached(
    tmp_path: Path,
) -> None:
    """The hook is no no-op: a plain open, an open relative to a directory
    descriptor after changing directory, a listing, and an open through a
    symbolic link each log the watched file."""
    root = tmp_path / "root"
    (root / "tools").mkdir(parents=True)
    held = root / "tools" / "held.txt"
    held.write_text("held\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(held)
    seen = _run_the_hook(
        tmp_path,
        root,
        "\n".join(
            [
                "import os",
                f"open({str(held)!r}).close()",
                f"fd = os.open({str(root / 'tools')!r}, os.O_RDONLY)",
                f"os.chdir({str(tmp_path)!r})",
                "os.close(os.open('held.txt', os.O_RDONLY, dir_fd=fd))",
                "os.close(fd)",
                f"os.listdir({str(root / 'tools')!r})",
                f"open({str(link)!r}).close()",
            ]
        ),
    )
    # Plain open, the folder's own open, the dir_fd open, the listing, the link.
    assert sorted(path for _, path in seen) == sorted(
        ["tools/held.txt", "tools", "tools/held.txt", "tools", "tools/held.txt"]
    )
