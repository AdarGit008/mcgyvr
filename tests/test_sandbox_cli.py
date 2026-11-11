"""The `mcgyvr sandbox` inspection command.

It exists so a stranger can see, before running anything, which mode is in
force and what the sandbox will try to install. The stack lines are asserted
here; the mode line depends on whether the test machine has Docker and is left
to the sandbox suite.

`--cache` lists the task images mcgyvr built and `--clear-cache` removes them.
Those cases run the real `sandbox.image` listing and removal against an
invented docker that holds a few labelled images, so no daemon is reached.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.cli import main
from mcgyvr.sandbox import image
from mcgyvr.sandbox.image import LABEL_KEY, LABEL_REPO, DockerResult


def test_sandbox_reports_a_detected_stack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")

    code = main(["sandbox", "--repo", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "base image: python:3.12-slim" in out
    assert "pip install uv && uv sync --frozen" in out


def test_sandbox_says_an_unlocked_project_gets_its_dev_group(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\n\n[dependency-groups]\ndev = ['ruff']\n",
        encoding="utf-8",
    )

    assert main(["sandbox", "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out

    install = next(line for line in out.splitlines() if "install:" in line)
    assert "pip install . --group dev" in install, out
    assert "dev group installed" in out


def test_sandbox_reports_an_undetected_stack_with_the_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")

    code = main(["sandbox", "--repo", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Stack not detected" in out
    assert "sandbox.image" in out


def test_sandbox_rejects_a_path_that_is_not_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope"
    code = main(["sandbox", "--repo", str(missing)])
    assert code == 1
    assert "not a directory" in capsys.readouterr().err


class _Docker:
    """An invented docker holding `images`: id -> (tag, size, created, repo)."""

    def __init__(self, images: dict[str, tuple[str, int, str, str]]) -> None:
        self.images = dict(images)
        self.listing_fails = False

    def __call__(self, args: Sequence[str], stdin: bytes | None) -> DockerResult:
        if list(args[:2]) == ["image", "ls"]:
            assert f"label={LABEL_REPO}" in args
            if self.listing_fails:
                return DockerResult(1, "", "Cannot connect to the Docker daemon")
            return DockerResult(0, "\n".join(self.images), "")
        if list(args[:2]) == ["image", "inspect"]:
            assert LABEL_REPO in args[3] and LABEL_KEY in args[3]
            tag, size, created, repo = self.images[args[-1]]
            return DockerResult(
                0, f"{args[-1]}\t{tag}\t{size}\t{created}\t{repo}\tk", ""
            )
        if list(args[:2]) == ["image", "rm"]:
            found = [i for i, (tag, *_) in self.images.items() if tag == args[2]]
            for image_id in found:
                del self.images[image_id]
            return DockerResult(0 if found else 1, "", "")
        raise AssertionError(f"unexpected docker call: {args}")


MIB = 1024 * 1024
CACHED = {
    "sha256:old": ("mcgyvr-task/app:aaa", 300 * MIB, "2026-11-01T10:00:00Z", "app"),
    "sha256:new": ("mcgyvr-task/lib:bbb", 100 * MIB, "2026-11-09T10:00:00Z", "lib"),
}


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> _Docker:
    fake = _Docker(CACHED)
    monkeypatch.setattr("mcgyvr.detect.detect_docker", lambda: (True, "invented"))
    # The command calls both with docker's own runner; the real code runs with
    # the invented one in its place (clear lists through list_cached).
    listed, cleared = image.list_cached, image.clear
    monkeypatch.setattr(
        image, "list_cached", lambda runner=fake, **kw: listed(runner, **kw)
    )
    monkeypatch.setattr(
        image, "clear", lambda repo_slug=None: cleared(repo_slug, runner=fake)
    )
    return fake


def test_cache_lists_the_task_images_newest_first_with_their_sizes(
    docker: _Docker, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sandbox", "--cache"]) == 0
    out = capsys.readouterr().out

    assert "Cached task images (400.0 MiB total, newest first):" in out
    lines = [line.split() for line in out.splitlines() if "mcgyvr-task/" in line]
    assert lines == [
        ["mcgyvr-task/lib:bbb", "100.0", "MiB", "[lib]"],
        ["mcgyvr-task/app:aaa", "300.0", "MiB", "[app]"],
    ]


def test_cache_says_an_empty_cache_is_empty(
    docker: _Docker, capsys: pytest.CaptureFixture[str]
) -> None:
    docker.images.clear()

    assert main(["sandbox", "--cache"]) == 0
    assert capsys.readouterr().out.strip() == "Image cache is empty."


def test_cache_that_cannot_be_listed_is_an_error(
    docker: _Docker, capsys: pytest.CaptureFixture[str]
) -> None:
    docker.listing_fails = True

    assert main(["sandbox", "--cache"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: could not list the image cache:"), err


def test_clear_cache_removes_every_task_image_and_names_each(
    docker: _Docker, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sandbox", "--clear-cache"]) == 0
    out = capsys.readouterr().out.splitlines()

    assert out[0] == "Cleared 2 cached image(s)."
    assert sorted(line.strip() for line in out[1:]) == [
        "removed mcgyvr-task/app:aaa",
        "removed mcgyvr-task/lib:bbb",
    ]
    assert docker.images == {}


def test_clear_cache_is_taken_before_cache_when_both_are_given(
    docker: _Docker, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sandbox", "--cache", "--clear-cache"]) == 0
    assert capsys.readouterr().out.startswith("Cleared 2 cached image(s).")


@pytest.mark.parametrize("flag", ["--cache", "--clear-cache"])
def test_with_no_docker_daemon_nothing_is_cached(
    flag: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("mcgyvr.detect.detect_docker", lambda: (False, "no docker"))

    assert main(["sandbox", flag]) == 0
    assert capsys.readouterr().out.strip() == (
        "No Docker daemon, so nothing is cached (no docker)."
    )
