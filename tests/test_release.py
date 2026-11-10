"""There is a product: a wheel built once from a tag, that carries the whole door.

Four buckets — source, product, declared config, live state — with arrows one way:
source is built into a product, once, on a ``v*`` tag, and the product is installed;
config joins at install time, never at build time.

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
  builds one. A wheel built twice is two products with one name;
* the workflow names no repository: it releases the run's own, so a fork's tag
  is a fork's release;
* a rehearsal publishes nothing: dispatched by hand it defaults to a dry run
  that builds and checks and skips both publishing jobs, and a real release
  from anything but a tag is refused;
* ``make release`` is the local half — build, version check, notes, ``twine
  check`` — and prints the tag command instead of running it.

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
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests._paths import REPO

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
    "scripts/release",
    "skills/mcgyvr/SETUP.md",
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


def _committed_copy(
    tmp_path: Path, extra: tuple[str, ...] = (), changelog: str | None = None
) -> Path:
    """This tree's build inputs (and ``extra`` entries), as one commit, with
    ``changelog`` as its CHANGELOG.md when one is given."""
    tree = tmp_path / "tree"
    for entry in (*BUILD_INPUTS, *extra):
        source, target = REPO / entry, tree / entry
        if source.is_dir():
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if changelog is not None:
        (tree / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-qm", "the tree under test")
    return tree


def _tagged_copy(tmp_path: Path, tag: str) -> Path:
    """This tree's build inputs, as one commit under ``tag``."""
    tree = _committed_copy(tmp_path)
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
    """What is installed, and not a literal: a checkout has a git history,
    so the version read from it is never the no-git fallback."""
    import importlib.metadata

    import mcgyvr

    assert mcgyvr.__version__ == importlib.metadata.version("mcgyvr")
    assert mcgyvr.__version__ != "0.0.0", "the literal survived"


def test_a_tag_that_is_not_a_version_does_not_break_the_build(tmp_path: Path) -> None:
    """This repository names tags `archive/<lane>` too. One above the last
    release must leave the version the release's, at a distance — not fail
    every build on every full clone with "does not parse as a version"."""
    tree = _tagged_copy(tmp_path, "v9.9.9")
    (tree / "NOTE").write_text("one commit later\n", encoding="utf-8")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-qm", "later")
    _git(tree, "tag", "archive/review-9")
    wheel = _build_wheel(tree, tmp_path / "dist")
    assert wheel.name.startswith("mcgyvr-9.9.10.dev1+g"), wheel.name


def test_a_pre_release_tag_is_the_version_it_normalises_to() -> None:
    """The release checks the wheel against the tag as versions: `v0.1.0-rc1`
    builds `mcgyvr-0.1.0rc1-…`, which is that tag and not a mismatch."""
    from scripts.release.wheel_is_tag import mismatch

    assert mismatch("v0.1.0-rc1", Path("mcgyvr-0.1.0rc1-py3-none-any.whl")) is None
    assert mismatch("v0.1.0", Path("mcgyvr-0.1.0-py3-none-any.whl")) is None
    why = mismatch("v0.2.0", Path("mcgyvr-0.1.0-py3-none-any.whl"))
    assert why is not None and "0.2.0" in why and "0.1.0" in why, why
    assert mismatch("archive/x", Path("mcgyvr-0.1.0-py3-none-any.whl")) is not None


# --- the wheel --------------------------------------------------------------------


def _door_files() -> list[str]:
    """Every file the door is: the gates, its steps, the readers, the shims,
    the lease release — by the names the door itself declares."""
    from mcgyvr.serving import run

    entries = (*run.SEQUENCE, *run.ALWAYS, *run.LINK_SEQUENCE, run.LEASE_RELEASE)
    names = [e.script for e in entries]
    names += [p.name for p in run.SERVE_STEPS.values()]
    names += [f"bin/{shim}" for shim in run.SHIMS]
    # A reader is named by where it sits in the package: most are beside the
    # gates, and the link timer is beside the door.
    package = run.HERE.parent.parent
    readers = [p.relative_to(package).as_posix() for p in run.READERS]
    return [f"mcgyvr/serving/gate-scripts/{name}" for name in names] + readers


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
        line for line in runs if "gh release create" in line and "--verify-tag" in line
    ]
    assert len(published) == 1, (
        f"release.yml must run `gh release create --verify-tag` once: {published}"
    )


ON_GITHUB = "github.server_url == 'https://github.com'"


def test_the_release_runs_on_github_and_reaches_pypi_by_trusted_publishing() -> None:
    """The release is a GitHub release and the PyPI identity is GitHub's OIDC
    token: a forge that also reads `.github/workflows` must skip `build`, and
    `pypi` must ride on it (so it is skipped with it) under the environment
    and the one permission the trusted publisher names. It rides on
    `github-release`, which rides on `build`, so whatever skips the GitHub
    release — a forge, a rehearsal — skips the upload with it."""
    jobs = _release()["jobs"]
    assert jobs["build"].get("if") == ON_GITHUB, jobs["build"].get("if")
    assert jobs["github-release"].get("needs") == "build", jobs["github-release"]
    pypi = jobs["pypi"]
    assert pypi.get("needs") == "github-release", pypi.get("needs")
    assert "if" not in pypi, "an `if:` on pypi would be evaluated, not skipped"
    assert pypi.get("environment") == "pypi", pypi.get("environment")
    assert pypi.get("permissions") == {"id-token": "write"}, pypi.get("permissions")
    text = RELEASE.read_text(encoding="utf-8")
    secrets = re.findall(r"\$\{\{\s*secrets\.[A-Za-z0-9_]+", text)
    assert secrets == [], f"the release reads a stored secret: {secrets}"


def test_the_release_is_of_the_runs_own_repository() -> None:
    """No repository is written in the workflow: `gh` is told the run's own,
    so a fork's tag makes the fork's release and never the upstream's."""
    text = RELEASE.read_text(encoding="utf-8")
    slugs = re.findall(r"(?:github\.com/|/repos/)[\w.-]+/[\w.-]+", text)
    assert slugs == [], f"release.yml names a repository: {slugs}"
    # A bare `<owner>/mcgyvr` anywhere — a comment, an env value, a `with:` —
    # unless it is a path in this tree (`src/mcgyvr`).
    bare = re.findall(r"(?<![\w./-])([\w.-]+/mcgyvr)\b(?![\w-])", text)
    named = [slug for slug in bare if not (REPO / slug).exists()]
    assert named == [], f"release.yml names a repository: {named}"
    told = re.findall(r"(?:--repo|-R|GH_REPO:?)[ =]+(\S+)", text)
    assert told == ['"$GITHUB_REPOSITORY"'], f"gh is told a repository: {told}"
    jobs = _release()["jobs"]
    step = _step(jobs["github-release"], "publish the GitHub release")
    assert '--repo "$GITHUB_REPOSITORY"' in str(step["run"]), step["run"]
    # An action told a repository is told the run's own, or nothing.
    for job in jobs.values():
        for each in job.get("steps", []):
            for key in ("repository", "repository-url", "repo"):
                value = (each.get("with") or {}).get(key)
                assert value is None or "github.repository" in str(value), (key, each)


def test_the_twine_check_is_pinned_and_one_pin() -> None:
    """The check is part of the release, so it is pinned like the actions, and
    `make release` checks with the same twine the tag's run does."""
    pins = re.findall(r"--with twine==(\d[\w.]*)", RELEASE.read_text(encoding="utf-8"))
    makefile = re.findall(
        r"--with twine==(\d[\w.]*)", (REPO / "Makefile").read_text(encoding="utf-8")
    )
    assert len(pins) == 1 and makefile == pins, (pins, makefile)
    assert "--with twine " not in RELEASE.read_text(encoding="utf-8")


def test_a_dispatch_is_a_dry_run_unless_told_otherwise() -> None:
    """By hand the workflow rehearses: `dry_run` is a boolean that defaults to
    true, and only `build` runs unless `build` says this run publishes."""
    workflow = _release()
    trigger = workflow.get("on", workflow.get(True))
    assert isinstance(trigger, dict), trigger
    dry_run = trigger["workflow_dispatch"]["inputs"]["dry_run"]
    assert dry_run.get("type") == "boolean", dry_run
    assert dry_run.get("default") is True, dry_run
    jobs = workflow["jobs"]
    assert jobs["github-release"].get("if") == "needs.build.outputs.publish == 'true'"
    assert jobs["build"]["outputs"]["publish"] == "${{ steps.mode.outputs.publish }}"


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    (found,) = [step for step in job["steps"] if step.get("name") == name]
    assert isinstance(found, dict)
    return found


def _mode(
    tmp_path: Path, ref_type: str, ref_name: str, dry_run: str, cwd: Path = REPO
) -> tuple[int, str, str]:
    """Run the `release or rehearsal` step's own script as the runner would,
    with `uv run … python` standing for this interpreter (packaging is in the
    test environment) and the runner's files in ``tmp_path``. Returns the exit
    code, then what it wrote to GITHUB_ENV and to GITHUB_OUTPUT."""
    script = str(_step(_release()["jobs"]["build"], "release or rehearsal")["run"])
    shim = tmp_path / "bin" / "uv"
    shim.parent.mkdir(exist_ok=True)
    shim.write_text(
        '#!/bin/sh\nwhile [ "$1" != python ]; do shift; done; shift\n'
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    env_file, out_file = tmp_path / "env", tmp_path / "out"
    env_file.write_text("", encoding="utf-8")
    out_file.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{shim.parent}{os.pathsep}{os.environ['PATH']}",
            "DRY_RUN": dry_run,
            "GITHUB_REF_TYPE": ref_type,
            "GITHUB_REF_NAME": ref_name,
            "GITHUB_ENV": str(env_file),
            "GITHUB_OUTPUT": str(out_file),
        },
    )
    assert done.returncode == 0 or "REFUSED" in done.stderr, done.stderr
    return done.returncode, env_file.read_text("utf-8"), out_file.read_text("utf-8")


@pytest.mark.skipif(os.name == "nt", reason="the runner's shell is bash on ubuntu")
def test_a_rehearsal_from_a_branch_stamps_the_newest_changelog_version(
    tmp_path: Path,
) -> None:
    from scripts.release.changelog_notes import latest

    newest = latest((REPO / "CHANGELOG.md").read_text(encoding="utf-8"))
    code, env, out = _mode(tmp_path, "branch", "feat/x", "true")
    assert code == 0
    assert f"SETUPTOOLS_SCM_PRETEND_VERSION={newest}\n" in env, env
    assert f"TAG=v{newest}\n" in env, env
    assert "publish=false\n" in out, out


@pytest.mark.skipif(os.name == "nt", reason="the runner's shell is bash on ubuntu")
def test_a_rehearsal_of_a_version_tagged_elsewhere_stays_green_and_says_so(
    tmp_path: Path,
) -> None:
    """The same tree `make release` refuses: the dry run still passes (it is a
    rehearsal), but files the tag's commit for the summary to name."""
    tree = _committed_copy(tmp_path / "t", changelog=RELEASE_CHANGELOG)
    code, env, _ = _mode(tmp_path, "branch", "feat/x", "true", cwd=tree)
    assert code == 0 and "TAGGED_AT" not in env, env
    _git(tree, "tag", "v9.9.9")
    _git(tree, "commit", "-q", "--allow-empty", "-m", "after the release")
    tagged = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "v9.9.9^{commit}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    code, env, out = _mode(tmp_path, "branch", "feat/x", "true", cwd=tree)
    assert code == 0 and "publish=false\n" in out, (env, out)
    assert f"TAGGED_AT={tagged}\n" in env, env
    summary = str(_step(_release()["jobs"]["build"], "summary")["run"])
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    words = "is already tagged at $"
    assert words in summary and words in makefile, "the two rehearsals word it apart"
    assert "write the next version's CHANGELOG section" in summary
    assert "write the next version's CHANGELOG section" in makefile


@pytest.mark.skipif(os.name == "nt", reason="the runner's shell is bash on ubuntu")
def test_a_tag_is_read_not_stamped_and_a_real_release_needs_one(tmp_path: Path) -> None:
    code, env, out = _mode(tmp_path, "tag", "v9.9.9", "false")
    assert code == 0
    assert "PRETEND" not in env, "a tag's version is read from the tag, not stamped"
    assert "TAG=v9.9.9\n" in env and "publish=true\n" in out, (env, out)
    code, env, out = _mode(tmp_path, "tag", "v9.9.9", "true")
    assert code == 0 and "PRETEND" not in env and "publish=false\n" in out, (env, out)
    code, env, out = _mode(tmp_path, "branch", "main", "false")
    assert code == 1, "a real release from a branch must be refused"
    assert out == "", f"a refused run told the later jobs something: {out}"


# --- make release: the local half ---------------------------------------------------

#: A changelog with one written release, the version the local half rehearses.
RELEASE_CHANGELOG = """\
# Changelog

## [Unreleased]

## [9.9.9] - 2026-11-10

### Added
- The rehearsed release.
"""


def _release_tree(tmp_path: Path) -> Path:
    """This tree's build inputs and its Makefile, one commit, no tag."""
    return _committed_copy(tmp_path, ("Makefile",), RELEASE_CHANGELOG)


def _make_release(tree: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """`make release` with this interpreter for the release scripts and a
    recording stand-in for twine, so the test needs no index to reach."""
    twine = tmp_path / "twine"
    twine.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path / "twine.calls"}"\n')
    twine.chmod(0o755)
    return subprocess.run(
        [
            "make",
            "release",
            f"RELEASE_PY={sys.executable}",
            f"TWINE={twine}",
            f"RELEASE_DIR={tmp_path / 'out'}",
        ],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
    )


needs_make = pytest.mark.skipif(
    shutil.which("make") is None or os.name == "nt", reason="`make release` needs make"
)


@needs_make
def test_make_release_runs_the_local_half_and_only_prints_the_tag(
    tmp_path: Path,
) -> None:
    tree = _release_tree(tmp_path)
    done = _make_release(tree, tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    # uv leaves a `.gitignore` in its out-dir; the recipe's globs skip it.
    out = (tmp_path / "out").iterdir()
    built = sorted(p.name for p in out if not p.name.startswith("."))
    assert built == ["mcgyvr-9.9.9-py3-none-any.whl", "mcgyvr-9.9.9.tar.gz"], built
    assert "The rehearsed release." in done.stdout, "the notes were not printed"
    (call,) = (tmp_path / "twine.calls").read_text().splitlines()
    assert call.split()[0] == "check" and len(call.split()) == 3, call
    assert "git tag -a v9.9.9 -m v9.9.9" in done.stdout, done.stdout
    assert "git push origin v9.9.9" in done.stdout, done.stdout
    tags = subprocess.run(
        ["git", "-C", str(tree), "tag", "-l"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert tags.stdout == "", f"make release tagged: {tags.stdout}"


@needs_make
def test_make_release_refuses_a_version_tagged_elsewhere_and_a_changed_tree(
    tmp_path: Path,
) -> None:
    tree = _release_tree(tmp_path)
    (tree / "pyproject.toml").write_text(
        (tree / "pyproject.toml").read_text() + "\n", encoding="utf-8"
    )
    done = _make_release(tree, tmp_path)
    assert done.returncode != 0 and "commit first" in done.stderr, done.stderr
    _git(tree, "commit", "-qam", "a second commit")
    _git(tree, "tag", "v9.9.9", "HEAD~1")
    done = _make_release(tree, tmp_path)
    assert done.returncode != 0 and "already tagged" in done.stderr, done.stderr
    assert not (tmp_path / "out").exists(), "a refused release built something"


def test_make_release_pushes_and_uploads_nothing() -> None:
    """What the recipe runs, not what it prints: with its echoed lines taken
    out, nothing in it tags, pushes, uploads or makes a release."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("\nrelease:", 1)[1]
    run = re.sub(r'echo "[^"]*"', "", recipe)
    for spelling in ("git tag", "git push", "twine upload", "gh release", "publish"):
        assert spelling not in run, f"make release runs {spelling!r}"


def test_the_macos_and_windows_job_waits_on_a_github_only_job() -> None:
    """On a forge with no macOS or Windows runners the job is skipped, not
    queued for a runner that never comes."""
    loaded = yaml.safe_load((WORKFLOWS / "platforms.yml").read_text(encoding="utf-8"))
    jobs = loaded["jobs"]
    assert jobs["on-github"].get("if") == ON_GITHUB, jobs["on-github"]
    assert jobs["platforms"].get("needs") == "on-github", jobs["platforms"]
    assert "if" not in jobs["platforms"], jobs["platforms"]


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
