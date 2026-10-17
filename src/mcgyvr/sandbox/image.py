""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.sandbox.stack import NODE_MODULES, TOOL_PATH, VENV, WORKSPACE, Stack

#
#
LABEL_REPO = "mcgyvr.repo"
LABEL_KEY = "mcgyvr.cache-key"
LABEL_BASE_DIGEST = "mcgyvr.base-digest"

#
#
#
#
IMAGE_LAYOUT = 2

#
#
#
SEEDABLE = tuple(path.removeprefix(f"{WORKSPACE}/") for path in (VENV, NODE_MODULES))

#
#
#
DEFAULT_MAX_CACHED_IMAGES = 8

#
#
#
#€”
#
DAEMON_OVERRIDES = ("DOCKER_HOST", "DOCKER_CONTEXT")


def foreign_daemon() -> str | None:
    ""
    for name in DAEMON_OVERRIDES:
        if name in os.environ:
            return (
                f"the sandbox runs on this machine's daemon; {name}="
                f"{os.environ[name]} is set, and a container the product starts "
                "must never land on a rig â€” the door (python -m "
                "mcgyvr.serving.run) is the only way there"
            )
    return None


class ImageError(Exception):
    ""


@dataclass(frozen=True)
class DockerResult:
    ""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


#
#
#
#
#
#
#
#
#
#
#
#
DOCKER_CALL_TIMEOUT_S = 120.0
DOCKER_BUILD_TIMEOUT_S = 3600.0
_LONG_VERBS = frozenset({"build", "pull"})


#
#
#
DockerRunner = Callable[[Sequence[str], "bytes | None"], DockerResult]


def subprocess_runner(args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
    ""
    refusal = foreign_daemon()
    if refusal is not None:
        return DockerResult(2, "", refusal)
    if shutil.which("docker") is None:
        return DockerResult(127, "", "docker is not on PATH")
    long = bool(args) and args[0] in _LONG_VERBS
    bound = DOCKER_BUILD_TIMEOUT_S if long else DOCKER_CALL_TIMEOUT_S
    try:
        done = subprocess.run(
            ["docker", *args],
            input=stdin,
            capture_output=True,
            timeout=bound,
            check=False,
        )
    except subprocess.TimeoutExpired:
        verb = " ".join(args[:1])
        return DockerResult(124, "", f"docker {verb} did not finish within {bound:g}s")
    except OSError as exc:
        return DockerResult(1, "", str(exc))
    return DockerResult(
        returncode=done.returncode,
        stdout=done.stdout.decode("utf-8", "replace"),
        stderr=done.stderr.decode("utf-8", "replace"),
    )


@dataclass(frozen=True)
class TaskImage:
    ""

    tag: str
    base_digest: str
    cache_key: str
    built: bool  #he


@dataclass(frozen=True)
class CachedImage:
    ""

    tag: str
    repo: str
    cache_key: str
    size_bytes: int
    created: str


def cache_key(stack: Stack, repo: Path, setup: Sequence[str]) -> str:
    ""
    hasher = hashlib.sha256()
    hasher.update(f"layout:{IMAGE_LAYOUT}\n".encode())
    hasher.update(f"base:{stack.base_image}\n".encode())
    for name in stack.manifest_paths():
        hasher.update(f"manifest:{name}\n".encode())
        try:
            hasher.update(hashlib.sha256((repo / name).read_bytes()).digest())
        except OSError as exc:
            raise ImageError(
                f"cannot read manifest {name} to key the image cache: {exc}"
            ) from exc
    for command in stack.install_commands():
        hasher.update(("install:" + " ".join(command) + "\n").encode())
    for checker in stack.checker_commands():
        hasher.update(f"checker:{checker}\n".encode())
    for setup_command in setup:
        hasher.update(f"setup:{setup_command}\n".encode())
    return hasher.hexdigest()[:16]


def image_tag(repo: Path, key: str) -> str:
    ""
    return f"mcgyvr/{_slug(repo.resolve().name)}:{key}"


def render_dockerfile(stack: Stack, base_digest_ref: str, setup: Sequence[str]) -> str:
    ""
    lines = [
        f"FROM {base_digest_ref}",
        "WORKDIR /workspace",
        #
        #ld
        #
        f"ENV PATH={TOOL_PATH}:$PATH",
    ]
    manifests = stack.manifest_paths()
    if manifests:
        #
        #
        for name in manifests:
            lines.append(f"COPY {name} {name}")
    for command in stack.install_commands():
        lines.append("RUN " + " && ".join(command))
    for checker in stack.checker_commands():
        lines.append(f"RUN {checker}")
    for setup_command in setup:
        lines.append(f"RUN {setup_command}")
    return "\n".join(lines) + "\n"


def seeded_folders(tag: str, runner: DockerRunner) -> tuple[str, ...]:
    ""
    script = f"cd {WORKSPACE} || exit 0; " + "; ".join(
        f'[ -d "{folder}" ] && [ -n "$(ls -A "{folder}")" ] && echo "{folder}"'
        for folder in SEEDABLE
    )
    asked = runner(
        [
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/bin/sh",
            tag,
            "-c",
            f"{script}; true",
        ],
        None,
    )
    if not asked.ok:
        return ()
    said = {line.strip() for line in asked.stdout.splitlines()}
    return tuple(folder for folder in SEEDABLE if folder in said)


def resolve_base_digest(base_ref: str, runner: DockerRunner) -> str:
    ""
    pull = runner(["pull", base_ref], None)
    if not pull.ok:
        raise ImageError(f"could not pull base image {base_ref}: {pull.stderr.strip()}")
    inspect = runner(
        ["image", "inspect", "--format", "{{index .RepoDigests 0}}", base_ref],
        None,
    )
    digest_ref = inspect.stdout.strip()
    if not inspect.ok or "@sha256:" not in digest_ref:
        raise ImageError(
            f"could not resolve {base_ref} to a digest for pinning; got "
            f"{digest_ref!r}. A base image must pin to a digest."
        )
    return digest_ref


def image_present(tag: str, runner: DockerRunner) -> bool:
    ""
    return runner(["image", "inspect", tag], None).ok


def ensure_image(
    stack: Stack,
    repo: Path,
    setup: Sequence[str] = (),
    *,
    runner: DockerRunner = subprocess_runner,
) -> TaskImage:
    ""
    if not stack.detected:
        raise ImageError(
            "stack was not detected, so no task image can be built. Set "
            "`sandbox.image` to an image that already carries the repository's "
            "dependencies."
        )

    key = cache_key(stack, repo, setup)
    tag = image_tag(repo, key)
    if image_present(tag, runner):
        base_digest = _read_label(tag, LABEL_BASE_DIGEST, runner)
        return TaskImage(tag=tag, base_digest=base_digest, cache_key=key, built=False)

    if stack.base_image is None:  #se
        raise ImageError("detected stack has no base image to build from")
    base_digest = resolve_base_digest(stack.base_image, runner)
    dockerfile = render_dockerfile(stack, base_digest, setup)
    _build(tag, key, repo, base_digest, dockerfile, stack, setup, runner)
    return TaskImage(tag=tag, base_digest=base_digest, cache_key=key, built=True)


def _build(
    tag: str,
    key: str,
    repo: Path,
    base_digest: str,
    dockerfile: str,
    stack: Stack,
    setup: Sequence[str],
    runner: DockerRunner,
) -> None:
    ""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-build-") as context:
        context_dir = Path(context)
        (context_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        for name in stack.manifest_paths():
            dest = context_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, dest)
        args = [
            "build",
            "--tag",
            tag,
            "--label",
            f"{LABEL_REPO}={_slug(repo.resolve().name)}",
            "--label",
            f"{LABEL_KEY}={key}",
            "--label",
            f"{LABEL_BASE_DIGEST}={base_digest}",
            "--file",
            str(context_dir / "Dockerfile"),
            str(context_dir),
        ]
        result = runner(args, None)
        if not result.ok:
            raise ImageError(
                f"building task image {tag} failed: {result.stderr.strip()}"
            )


def list_cached(runner: DockerRunner = subprocess_runner) -> tuple[CachedImage, ...]:
    ""
    fmt = (
        "{{.ID}}\t{{index .RepoTags 0}}\t{{.Size}}\t{{.Created}}"
        f'\t{{{{index .Config.Labels "{LABEL_REPO}"}}}}'
        f'\t{{{{index .Config.Labels "{LABEL_KEY}"}}}}'
    )
    listing = runner(
        [
            "image",
            "ls",
            "--filter",
            f"label={LABEL_REPO}",
            "--no-trunc",
            "--format",
            "{{.ID}}",
        ],
        None,
    )
    if not listing.ok:
        raise ImageError(f"could not list the image cache: {listing.stderr.strip()}")

    images: list[CachedImage] = []
    for image_id in listing.stdout.split():
        inspected = runner(["image", "inspect", "--format", fmt, image_id], None)
        if not inspected.ok:
            continue
        fields = inspected.stdout.strip().split("\t")
        if len(fields) != 6:
            continue
        _id, tag, size, created, repo, key = fields
        images.append(
            CachedImage(
                tag=tag,
                repo=repo,
                cache_key=key,
                size_bytes=_int(size),
                created=created,
            )
        )
    #
    #
    images.sort(key=lambda c: c.created, reverse=True)
    return tuple(images)


def prune(
    max_images: int = DEFAULT_MAX_CACHED_IMAGES,
    *,
    runner: DockerRunner = subprocess_runner,
) -> tuple[str, ...]:
    ""
    if max_images < 0:
        raise ImageError("max_images cannot be negative")
    cached = list_cached(runner)
    doomed = cached[max_images:]
    removed: list[str] = []
    for image in doomed:
        if runner(["image", "rm", image.tag], None).ok:
            removed.append(image.tag)
    return tuple(removed)


def clear(
    repo_slug: str | None = None,
    *,
    runner: DockerRunner = subprocess_runner,
) -> tuple[str, ...]:
    ""
    removed: list[str] = []
    for image in list_cached(runner):
        if repo_slug is not None and image.repo != repo_slug:
            continue
        if runner(["image", "rm", image.tag], None).ok:
            removed.append(image.tag)
    return tuple(removed)


def _read_label(tag: str, label: str, runner: DockerRunner) -> str:
    fmt = f'{{{{index .Config.Labels "{label}"}}}}'
    result = runner(["image", "inspect", "--format", fmt, tag], None)
    return result.stdout.strip() if result.ok else ""


def _slug(name: str) -> str:
    ""
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in name.lower())
    return safe.strip("-._") or "repo"


def _int(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0
