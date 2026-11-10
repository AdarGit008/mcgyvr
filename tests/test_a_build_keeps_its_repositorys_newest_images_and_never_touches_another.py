"""A build trims its own repository's image cache, and only that.

Every dependency set a repository moves to is a new task image, so without a
trim the cache grows for as long as the repository lives. After a task
container builds an image, that repository's cached images beyond the newest
``sandbox.image_cache_keep`` (default ``DEFAULT_MAX_CACHED_IMAGES``) are removed
and the removal is said on stderr. Only images labelled with the repository
being built are counted or removed: a run of another repository, started in
parallel, keeps the image it is about to start whatever its own count is. A
cache hit builds nothing and trims nothing; ``0`` turns the trim off; a cache
docker will not list is said and the task goes on; an image docker refuses to
remove (a container still uses it) stays.

What a real daemon does is checked up to the daemon, through recorded argv.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcgyvr.cli.sandbox import _sandbox_policy
from mcgyvr.config import ConfigSchemaError
from mcgyvr.config import load as load_config
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import open_sandbox
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import (
    DEFAULT_MAX_CACHED_IMAGES,
    LABEL_BASE_DIGEST,
    LABEL_REPO,
    DockerResult,
    prune,
)
from tests import livejournal as lj

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _repo(parent: Path, name: str) -> Path:
    """A committed uv project whose directory name is its image slug."""
    repo = parent / name
    repo.mkdir()
    (repo / "pyproject.toml").write_text(f"[project]\nname = '{name}'\n")
    (repo / "uv.lock").write_text("version = 1\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        check=True,
        env={**os.environ, **_IDENTITY},
    )
    return repo


@dataclass
class _Image:
    image_id: str
    tag: str
    repo: str
    created: str


class _Daemon:
    """A daemon with an image cache: it builds, lists, inspects and removes.

    Each build is newer than everything already cached. An image a container
    started from and not yet removed is refused removal, as docker refuses it.
    Calls are serialised, so two sandboxes may share it from two threads.
    """

    def __init__(self, cached: Sequence[tuple[str, str]] = ()) -> None:
        self.images: list[_Image] = []
        self.calls: list[list[str]] = []
        self.containers: dict[str, str] = {}  # name -> image tag
        self.list_fails = False
        self._clock = 0
        self._lock = threading.Lock()
        for repo, key in cached:
            self._add(f"mcgyvr/{repo}:{key}", repo)

    def _add(self, tag: str, repo: str) -> None:
        self._clock += 1
        created = f"2026-08-01T00:00:{self._clock:02d}Z"
        self.images.append(_Image(f"id-{self._clock}", tag, repo, created))

    def tags(self, repo: str) -> set[str]:
        return {i.tag for i in self.images if i.repo == repo}

    def removals(self) -> list[str]:
        return [c[2] for c in self.calls if c[:2] == ["image", "rm"]]

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        with self._lock:
            return self._answer(list(args))

    def _answer(self, cmd: list[str]) -> DockerResult:
        self.calls.append(cmd)
        if cmd[0] == "pull":
            return DockerResult(0, "", "")
        if cmd[0] == "build":
            tag = cmd[cmd.index("--tag") + 1]
            label = next(v for v in cmd if v.startswith(f"{LABEL_REPO}="))
            self._add(tag, label.split("=", 1)[1])
            return DockerResult(0, "", "")
        if cmd[:2] == ["image", "ls"]:
            if self.list_fails:
                return DockerResult(1, "", "Cannot connect to the Docker daemon")
            wanted = cmd[cmd.index("--filter") + 1].removeprefix(f"label={LABEL_REPO}")
            listed = [
                i.image_id for i in self.images if not wanted or wanted == f"={i.repo}"
            ]
            return DockerResult(0, "\n".join(listed), "")
        if cmd[:2] == ["image", "inspect"]:
            return self._inspect(cmd)
        if cmd[:2] == ["image", "rm"]:
            if cmd[2] in self.containers.values():
                return DockerResult(1, "", "conflict: container is using its image")
            self.images = [i for i in self.images if i.tag != cmd[2]]
            return DockerResult(0, "", "")
        if cmd[:2] == ["run", "--rm"]:  # the seeded-folder probe
            return DockerResult(0, ".venv\n", "")
        if cmd[:2] == ["run", "--detach"]:
            name = cmd[cmd.index("--name") + 1]
            self.containers[name] = next(i.tag for i in self.images if i.tag in cmd)
            return DockerResult(0, "container-id", "")
        if cmd[:3] == ["rm", "--force", "--volumes"]:
            self.containers.pop(cmd[3], None)
            return DockerResult(0, "", "")
        return DockerResult(0, "", "")

    def _inspect(self, cmd: list[str]) -> DockerResult:
        if len(cmd) == 3:  # existence check by tag
            present = any(i.tag == cmd[2] for i in self.images)
            return DockerResult(0 if present else 1, "", "")
        fmt, target = cmd[3], cmd[4]
        if "RepoDigests" in fmt or LABEL_BASE_DIGEST in fmt:
            return DockerResult(0, "python:3.12-slim@sha256:pinned", "")
        for i in self.images:  # the cache listing's per-id row
            if i.image_id == target:
                return DockerResult(
                    0, f"{i.image_id}\t{i.tag}\t10\t{i.created}\t{i.repo}\tk", ""
                )
        return DockerResult(1, "", "no such image")


@pytest.fixture(autouse=True)
def _no_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(0, "", "", False)
    )


def _old(repo: str, n: int) -> list[tuple[str, str]]:
    return [(repo, f"old{i}") for i in range(n)]


# --- the trim after a build -------------------------------------------------


def test_a_build_keeps_its_repositorys_newest_images(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    alpha = _repo(tmp_path, "alpha")
    daemon = _Daemon(_old("alpha", 4))
    sandbox = DockerSandbox(alpha, runner=daemon, image_cache_keep=2)
    with sandbox:
        assert sandbox._image_tag in daemon.tags("alpha")

    # The new image and the newest old one stay; the three oldest go.
    assert daemon.tags("alpha") == {sandbox._image_tag, "mcgyvr/alpha:old3"}
    assert sorted(daemon.removals()) == [f"mcgyvr/alpha:old{i}" for i in range(3)]
    err = capsys.readouterr().err
    assert "removed 3 older task image(s) of alpha" in err
    assert "`mcgyvr sandbox --cache`" in err


def test_another_repositorys_images_are_never_counted_or_removed(
    tmp_path: Path,
) -> None:
    alpha = _repo(tmp_path, "alpha")
    beta_images = _old("beta", 6)
    daemon = _Daemon([*beta_images, *_old("alpha", 2)])
    with DockerSandbox(alpha, runner=daemon, image_cache_keep=1):
        pass

    assert daemon.tags("beta") == {f"mcgyvr/{r}:{k}" for r, k in beta_images}
    assert not any(tag.startswith("mcgyvr/beta:") for tag in daemon.removals())
    assert len(daemon.tags("alpha")) == 1
    # Docker is asked for alpha's images only, so beta's are not even inspected:
    # the trim costs one inspect per image of the repository built.
    listing = next(c for c in daemon.calls if c[:2] == ["image", "ls"])
    assert f"label={LABEL_REPO}=alpha" in listing
    beta_ids = {f"id-{n}" for n in range(1, len(beta_images) + 1)}
    inspected = {c[-1] for c in daemon.calls if c[:2] == ["image", "inspect"]}
    assert not inspected & beta_ids


def test_two_repositories_building_in_parallel_each_keep_the_image_they_start(
    tmp_path: Path,
) -> None:
    alpha, beta = _repo(tmp_path, "alpha"), _repo(tmp_path, "beta")
    daemon = _Daemon([*_old("alpha", 3), *_old("beta", 3)])
    started: dict[str, str] = {}
    both_up = threading.Barrier(2, timeout=30)
    failures: list[BaseException] = []

    def run(repo: Path) -> None:
        try:
            sandbox = DockerSandbox(repo, runner=daemon, image_cache_keep=1)
            with sandbox:
                assert sandbox._image_tag is not None
                started[repo.name] = sandbox._image_tag
                # Both containers are up before either is torn down, so each
                # build's trim ran while the other repository's run was live.
                both_up.wait()
                assert sandbox._image_tag in daemon.tags(repo.name)
        except BaseException as exc:  # surfaced on the main thread below
            failures.append(exc)

    threads = [threading.Thread(target=run, args=(r,)) for r in (alpha, beta)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not failures, failures

    assert daemon.tags("alpha") == {started["alpha"]}
    assert daemon.tags("beta") == {started["beta"]}
    assert started["alpha"] not in daemon.removals()
    assert started["beta"] not in daemon.removals()


def test_a_cache_hit_builds_nothing_and_trims_nothing(tmp_path: Path) -> None:
    alpha = _repo(tmp_path, "alpha")
    daemon = _Daemon(_old("alpha", 5))
    sandbox = DockerSandbox(alpha, runner=daemon, image_cache_keep=1)
    with sandbox:
        built = sandbox._image_tag
    assert built is not None
    before = daemon.tags("alpha")

    again = _Daemon()
    again.images = list(daemon.images)
    with DockerSandbox(alpha, runner=again, image_cache_keep=1):
        pass

    assert not any(c[0] == "build" for c in again.calls)
    assert not any(c[:2] == ["image", "ls"] for c in again.calls)
    assert again.tags("alpha") == before == {built}


def test_zero_keeps_every_image(tmp_path: Path) -> None:
    alpha = _repo(tmp_path, "alpha")
    daemon = _Daemon(_old("alpha", DEFAULT_MAX_CACHED_IMAGES + 3))
    with DockerSandbox(alpha, runner=daemon, image_cache_keep=0):
        pass

    assert daemon.removals() == []
    assert not any(c[:2] == ["image", "ls"] for c in daemon.calls)
    assert len(daemon.tags("alpha")) == DEFAULT_MAX_CACHED_IMAGES + 4


def test_the_default_keeps_the_newest_default_count(tmp_path: Path) -> None:
    alpha = _repo(tmp_path, "alpha")
    daemon = _Daemon(_old("alpha", DEFAULT_MAX_CACHED_IMAGES + 2))
    with DockerSandbox(alpha, runner=daemon):
        pass

    assert len(daemon.tags("alpha")) == DEFAULT_MAX_CACHED_IMAGES
    assert len(daemon.removals()) == 3


def test_a_cache_that_cannot_be_listed_is_said_and_the_task_goes_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    alpha = _repo(tmp_path, "alpha")
    daemon = _Daemon(_old("alpha", 3))
    daemon.list_fails = True
    sandbox = DockerSandbox(alpha, runner=daemon, image_cache_keep=1)
    with sandbox:
        assert sandbox.run(["true"]).exit_code == 0

    assert daemon.removals() == []
    assert "the image cache was not trimmed" in capsys.readouterr().err


def test_an_image_a_container_still_uses_stays_and_is_not_reported() -> None:
    daemon = _Daemon(_old("alpha", 3))
    daemon.containers["someone-else"] = "mcgyvr/alpha:old0"
    removed = prune("alpha", 1, runner=daemon)

    assert removed == ("mcgyvr/alpha:old1",)
    assert daemon.tags("alpha") == {"mcgyvr/alpha:old0", "mcgyvr/alpha:old2"}


# --- the setting ------------------------------------------------------------


def test_the_setting_defaults_to_the_image_modules_bound(tmp_path: Path) -> None:
    config = load_config(lj.make_config(tmp_path / "setup"))
    assert config.get("sandbox.image_cache_keep") == DEFAULT_MAX_CACHED_IMAGES
    assert _sandbox_policy(config)["image_cache_keep"] == DEFAULT_MAX_CACHED_IMAGES
    assert _sandbox_policy(None)["image_cache_keep"] == DEFAULT_MAX_CACHED_IMAGES


@pytest.mark.parametrize("keep", [0, 3])
def test_the_setting_reaches_the_container(
    keep: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    path = lj.make_config(tmp_path / "setup")
    lj.append_policy(path, f"sandbox:\n  image_cache_keep: {keep}\n")
    policy = _sandbox_policy(load_config(path))
    assert policy["image_cache_keep"] == keep

    sandbox = open_sandbox(_repo(tmp_path, "alpha"), docker_available=True, **policy)
    assert isinstance(sandbox, DockerSandbox)
    assert sandbox._image_cache_keep == keep


@pytest.mark.parametrize("value", ["-1", "lots"])
def test_the_setting_takes_a_count_of_zero_or_more_only(
    value: str, tmp_path: Path
) -> None:
    path = lj.make_config(tmp_path / "setup")
    lj.append_policy(path, f"sandbox:\n  image_cache_keep: {value}\n")
    with pytest.raises(ConfigSchemaError, match="image_cache_keep"):
        load_config(path)
