"""There is a product: a wheel built once from a tag, that carries the whole door.

``pyproject.toml`` says ``version = "0.0.0"``, there are no release tags, and
prod is a git checkout on srv1 updated with ``git pull``. Dev and prod are
therefore one tree on two hosts: no version stamp, no rollback, no way to say
which code produced a result. The target shape is four buckets — source,
product, declared config, live state — with arrows one way: source is built
into a product, once, on a ``v*`` tag, and the product is installed; config
joins at install time, never at build time.

What must be observably true:

* the version is the tag's: a tree tagged ``v9.9.9`` builds
  ``mcgyvr-9.9.9``, and nothing in ``pyproject.toml`` spells a version;
* the product says which version it is: ``mcgyvr.__version__`` is what is
  installed, not a literal;
* the wheel carries the door whole — every gate the door runs, its own
  steps, the readers a gate reads, the two shims and the lease release,
  executable — and the data files and the vendored engine, so an install
  missing any of them cannot be built. A door without its shims refuses to
  start, so a wheel without them is a broken install, not a degraded one;
* one workflow builds the distribution, on a ``v*`` tag, with every action
  pinned by commit, and publishes it to a GitHub release; no other workflow
  builds one. A wheel built twice is two products with one name.

The build runs here, not in a mock: ``uv build`` is what the release runs,
and a test that inspected the config instead of the wheel would be a test of
what someone wrote rather than of what ships.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"

#: A pinned action: ``owner/name@<40 hex>``, with the version it stands for
#: in a trailing comment, as ``ci.yml`` already spells every action.
PINNED = re.compile(r"^\s*-?\s*uses:\s*\S+@[0-9a-f]{40}\s+#\s*v?\d", re.MULTILINE)
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.MULTILINE)

#: What a wheel build needs from the tree, and nothing more: the sources,
#: the files force-included into the package, and the metadata files.
BUILD_INPUTS = (
    "pyproject.toml",
    "LICENSE",
    "src",
    "data",
    "records/evidence/ghostcall-2026-08-02",
)


def _uv() -> str:
    found = shutil.which("uv")
    if found is None:
        pytest.fail("uv is not on PATH; the release builds with `uv build`")
    return found


def _build_wheel(tree: Path, out: Path) -> Path:
    done = subprocess.run(
        [_uv(), "build", "--wheel", "--out-dir", str(out)],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    (wheel,) = sorted(out.glob("*.whl"))
    return wheel


def _git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(where), *args],
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


def _tagged_copy(tmp_path: Path, tag: str) -> Path:
    """This tree's build inputs, as one commit under ``tag``."""
    tree = tmp_path / "tree"
    for entry in BUILD_INPUTS:
        source, target = REPO / entry, tree / entry
        if source.is_dir():
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-qm", "the tree under test")
    _git(tree, "tag", tag)
    return tree


# --- the version ------------------------------------------------------------------


def test_the_version_is_the_tags_and_nothing_spells_one(tmp_path: Path) -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in project["project"], (
        "pyproject.toml spells a version; the tag is the version"
    )
    assert "version" in project["project"].get("dynamic", []), project["project"]
    wheel = _build_wheel(_tagged_copy(tmp_path, "v9.9.9"), tmp_path / "dist")
    assert wheel.name.startswith("mcgyvr-9.9.9-"), wheel.name
    with zipfile.ZipFile(wheel) as archive:
        (metadata,) = [n for n in archive.namelist() if n.endswith("/METADATA")]
        text = archive.read(metadata).decode("utf-8")
    assert "\nVersion: 9.9.9\n" in text, text[:400]


def test_the_product_says_which_version_is_installed() -> None:
    import importlib.metadata

    import mcgyvr

    assert mcgyvr.__version__ == importlib.metadata.version("mcgyvr")


# --- the wheel --------------------------------------------------------------------


def _door_files() -> list[str]:
    """Every file the door is: the gates, its steps, the readers, the shims,
    the lease release — by the names the door itself declares."""
    from mcgyvr.serving import run

    names = [e.script for e in (*run.SEQUENCE, *run.ALWAYS, run.LEASE_RELEASE)]
    names += [p.name for p in (*run.SERVE_STEPS.values(), *run.READERS)]
    names += [f"bin/{shim}" for shim in run.SHIMS]
    return [f"mcgyvr/serving/gate-scripts/{name}" for name in names]


DATA_FILES = (
    "mcgyvr/data/capability-table.json",
    "mcgyvr/data/task-catalog.json",
    "mcgyvr/gate/_engine/ghostcall/__init__.py",
    "mcgyvr/gate/_engine/ghostcall/parser.py",
    "mcgyvr/gate/_engine/ghostcall/checker.py",
    "mcgyvr/gate/_engine/ghostcall/suggest.py",
    "mcgyvr/gate/_engine/ghostcall/LICENSE",
)


def test_the_wheel_carries_the_whole_door_executable_and_the_data(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(REPO, tmp_path / "dist")
    with zipfile.ZipFile(wheel) as archive:
        modes = {
            info.filename: (info.external_attr >> 16) & 0o777
            for info in archive.infolist()
        }
    missing = [name for name in (*_door_files(), *DATA_FILES) if name not in modes]
    assert missing == [], f"not in the wheel: {missing}"
    not_executable = [name for name in _door_files() if not modes[name] & stat.S_IXUSR]
    assert not_executable == [], (
        f"in the wheel without an executable bit: {not_executable}; the door "
        "refuses a gate it cannot run"
    )


# --- the release ------------------------------------------------------------------


def _release() -> dict[Any, Any]:
    assert RELEASE.is_file(), f"{RELEASE.relative_to(REPO)} does not exist"
    loaded = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), loaded
    return loaded


def _steps(workflow: dict[Any, Any]) -> list[dict[str, object]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and jobs, workflow
    found: list[dict[str, object]] = []
    for job in jobs.values():
        assert isinstance(job, dict)
        found.extend(step for step in job.get("steps", []) if isinstance(step, dict))
    return found


def test_the_release_builds_once_on_a_tag_and_publishes() -> None:
    workflow = _release()
    # PyYAML reads the bare key `on` as the boolean True.
    trigger = workflow.get("on", workflow.get(True))
    assert isinstance(trigger, dict), f"release.yml triggers on {trigger!r}"
    tags = trigger.get("push", {}).get("tags", [])
    assert any(str(t).startswith("v") for t in tags), (
        f"release.yml does not trigger on a v* tag: {trigger}"
    )
    runs = [str(step.get("run", "")) for step in _steps(workflow)]
    builds = [line for line in runs if "uv build" in line]
    assert len(builds) == 1, f"the release must build exactly once: {builds}"
    published = [
        line for line in runs if "gh release" in line or "release" in line.lower()
    ] + [
        str(step.get("uses"))
        for step in _steps(workflow)
        if "release" in str(step.get("uses", "")).lower()
    ]
    assert published, "nothing in release.yml publishes to a GitHub release"


def test_every_action_in_the_release_is_pinned_by_commit() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    used = USES.findall(text)
    assert used, "release.yml uses no action at all"
    pinned = PINNED.findall(text)
    assert len(pinned) == len(used), (
        f"{len(used)} actions, {len(pinned)} pinned by a 40-hex commit with the "
        f"version beside it as ci.yml spells them: {used}"
    )


def test_nothing_else_in_ci_builds_a_distribution() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        if workflow == RELEASE:
            continue
        text = workflow.read_text(encoding="utf-8")
        for spelling in ("uv build", "python -m build", "pip wheel", "hatch build"):
            assert spelling not in text, (
                f"{workflow.name} builds a distribution ({spelling!r}); the "
                "release workflow builds it once"
            )
