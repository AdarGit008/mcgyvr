"""Image build and per-repo cache, with Docker itself replaced by a stub.

None of this needs a daemon to be correct: the argv, the generated Dockerfile
and the cache-key arithmetic are the behaviour, and a machine without Docker
should still be able to check them (the seam :mod:`mcgyvr.detect` established).
Every test drives a recording runner and asserts on what would have been run.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.sandbox import image as image_module
from mcgyvr.sandbox.image import (
    LABEL_BASE_DIGEST,
    LABEL_KEY,
    LABEL_REPO,
    DockerResult,
    ImageError,
    cache_key,
    clear,
    ensure_image,
    list_cached,
    prune,
    render_dockerfile,
    resolve_base_digest,
)
from mcgyvr.sandbox.stack import detect_stack


def python_repo(tmp_path: Path, lock: str = "# lock\n") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "uv.lock").write_text(lock, encoding="utf-8")
    return repo


# --- cache key: exactly the dependency set -------------------------------


def test_cache_key_is_stable_for_the_same_inputs(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    stack = detect_stack(repo)
    assert cache_key(stack, repo, ()) == cache_key(stack, repo, ())


def test_a_lockfile_change_changes_the_key(tmp_path: Path) -> None:
    repo = python_repo(tmp_path, lock="# one\n")
    before = cache_key(detect_stack(repo), repo, ())
    (repo / "uv.lock").write_text("# two — a dependency moved\n", encoding="utf-8")
    after = cache_key(detect_stack(repo), repo, ())
    assert before != after


def test_an_unrelated_source_change_does_not_change_the_key(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    before = cache_key(detect_stack(repo), repo, ())
    (repo / "app.py").write_text("print('new feature')\n", encoding="utf-8")
    after = cache_key(detect_stack(repo), repo, ())
    assert before == after


def test_setup_commands_are_part_of_the_key(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    stack = detect_stack(repo)
    assert cache_key(stack, repo, ()) != cache_key(
        stack, repo, ("apt-get install -y x",)
    )


# --- Dockerfile ----------------------------------------------------------


def test_dockerfile_pins_the_base_and_installs_only_manifests(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    stack = detect_stack(repo)
    dockerfile = render_dockerfile(
        stack, "python:3.12-slim@sha256:deadbeef", ("echo hi",)
    )
    assert dockerfile.startswith("FROM python:3.12-slim@sha256:deadbeef\n")
    assert "COPY pyproject.toml pyproject.toml" in dockerfile
    assert "COPY uv.lock uv.lock" in dockerfile
    assert "RUN pip install uv && uv sync --frozen" in dockerfile
    assert "RUN echo hi" in dockerfile


# --- digest resolution (REPRO-04) ----------------------------------------


class _DigestRunner:
    """A runner that pulls and reports a digest for known base references."""

    def __init__(self, digests: dict[str, str]) -> None:
        self.digests = digests
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        cmd = list(args)
        self.calls.append(cmd)
        if cmd[0] == "pull":
            ok = cmd[1] in self.digests
            return DockerResult(0 if ok else 1, "", "" if ok else "no such image")
        if cmd[:2] == ["image", "inspect"] and "RepoDigests" in cmd[3]:
            digest = self.digests.get(cmd[4], "")
            return DockerResult(0 if digest else 1, digest, "")
        return DockerResult(1, "", f"unexpected: {cmd}")


def test_resolve_base_digest_pins_to_sha256() -> None:
    runner = _DigestRunner({"python:3.12-slim": "python:3.12-slim@sha256:abc123"})
    assert (
        resolve_base_digest("python:3.12-slim", runner)
        == "python:3.12-slim@sha256:abc123"
    )
    assert ["pull", "python:3.12-slim"] in runner.calls


def test_a_base_that_will_not_resolve_is_refused() -> None:
    runner = _DigestRunner({})
    with pytest.raises(ImageError):
        resolve_base_digest("python:3.12-slim", runner)


# --- ensure_image: build once, then reuse --------------------------------


class _BuildRunner:
    """A runner that simulates a daemon with a mutable set of present images."""

    def __init__(self, present: set[str] | None = None) -> None:
        self.present: set[str] = set(present or ())
        self.base_digest = "python:3.12-slim@sha256:pinned"
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        cmd = list(args)
        self.calls.append(cmd)
        if cmd[0] == "pull":
            return DockerResult(0, "", "")
        if cmd[:2] == ["image", "inspect"]:
            if len(cmd) == 3:  # existence check by tag
                return DockerResult(0 if cmd[2] in self.present else 1, "", "")
            fmt = cmd[3]
            if "RepoDigests" in fmt:
                return DockerResult(0, self.base_digest, "")
            if LABEL_BASE_DIGEST in fmt:
                return DockerResult(0, self.base_digest, "")
            return DockerResult(0, "", "")
        if cmd[0] == "build":
            tag = cmd[cmd.index("--tag") + 1]
            self.present.add(tag)
            return DockerResult(0, "", "")
        return DockerResult(1, "", f"unexpected: {cmd}")

    def built_tags(self) -> list[str]:
        return [c[c.index("--tag") + 1] for c in self.calls if c[0] == "build"]


def test_first_task_builds_and_stamps_labels(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    runner = _BuildRunner()
    result = ensure_image(detect_stack(repo), repo, (), runner=runner)
    assert result.built is True
    assert result.base_digest == "python:3.12-slim@sha256:pinned"
    # The build carries the labels the cache is later read back through.
    build = next(c for c in runner.calls if c[0] == "build")
    assert f"{LABEL_REPO}=repo" in build
    assert f"{LABEL_KEY}={result.cache_key}" in build
    assert f"{LABEL_BASE_DIGEST}={result.base_digest}" in build


def test_second_task_reuses_the_cached_image(tmp_path: Path) -> None:
    repo = python_repo(tmp_path)
    runner = _BuildRunner()
    first = ensure_image(detect_stack(repo), repo, (), runner=runner)
    # Same repo, same manifests → the tag is present → no second build.
    second = ensure_image(detect_stack(repo), repo, (), runner=runner)
    assert first.tag == second.tag
    assert second.built is False
    assert runner.built_tags() == [first.tag]  # built exactly once


def test_a_lockfile_change_triggers_exactly_one_rebuild(tmp_path: Path) -> None:
    repo = python_repo(tmp_path, lock="# one\n")
    runner = _BuildRunner()
    first = ensure_image(detect_stack(repo), repo, (), runner=runner)
    (repo / "uv.lock").write_text("# two\n", encoding="utf-8")
    second = ensure_image(detect_stack(repo), repo, (), runner=runner)
    assert first.tag != second.tag  # a new key, hence a new tag
    assert runner.built_tags() == [first.tag, second.tag]


def test_undetected_stack_cannot_build(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ImageError):
        ensure_image(detect_stack(empty), empty, (), runner=_BuildRunner())


# --- cache: inspectable, bounded, clearable ------------------------------


class _CacheRunner:
    """A runner over a fixed set of cached images, newest last in insertion."""

    def __init__(self, images: list[tuple[str, str, str, int, str]]) -> None:
        # each image: (id, tag, repo, size, created)
        self.images = images
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        cmd = list(args)
        self.calls.append(cmd)
        if cmd[:2] == ["image", "ls"]:
            return DockerResult(0, "\n".join(i[0] for i in self.images), "")
        if cmd[:2] == ["image", "inspect"]:
            target = cmd[-1]
            for image_id, tag, repo, size, created in self.images:
                if target == image_id:
                    row = f"{image_id}\t{tag}\t{size}\t{created}\t{repo}\tkey"
                    return DockerResult(0, row, "")
            return DockerResult(1, "", "no such image")
        if cmd[:2] == ["image", "rm"]:
            self.images = [i for i in self.images if i[1] != cmd[2]]
            return DockerResult(0, "", "")
        return DockerResult(1, "", f"unexpected: {cmd}")


def _cache(n: int) -> list[tuple[str, str, str, int, str]]:
    # created timestamps ascending, so image i is older than image i+1
    return [
        (f"id{i}", f"mcgyvr/repo:key{i}", "repo", 1000 * (i + 1), f"2026-08-0{i + 1}")
        for i in range(n)
    ]


def test_list_cached_reads_back_sizes_newest_first() -> None:
    runner = _CacheRunner(_cache(3))
    cached = list_cached(runner)
    assert [c.tag for c in cached] == [
        "mcgyvr/repo:key2",
        "mcgyvr/repo:key1",
        "mcgyvr/repo:key0",
    ]
    assert cached[0].size_bytes == 3000


def test_prune_evicts_the_oldest_beyond_the_bound() -> None:
    runner = _CacheRunner(_cache(5))
    removed = prune(2, runner=runner)
    # Keep the 2 newest (key4, key3); evict the 3 oldest.
    assert set(removed) == {"mcgyvr/repo:key2", "mcgyvr/repo:key1", "mcgyvr/repo:key0"}


def test_clear_scopes_to_one_repo_when_asked() -> None:
    images = [*_cache(1), ("idz", "mcgyvr/other:k", "other", 10, "2026-08-09")]
    runner = _CacheRunner(images)
    removed = clear("other", runner=runner)
    assert removed == ("mcgyvr/other:k",)


def test_subprocess_runner_reports_absent_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mcgyvr.sandbox.image.shutil.which", lambda _: None)
    result = image_module.subprocess_runner(["ps"])
    assert result.returncode == 127
    assert "not on PATH" in result.stderr
