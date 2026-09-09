"""Build the task image once per repository, and cache it.

Installing a project's dependencies for every task is unusable; installing
them once per repository is not (#29). So the sandbox image carries the
repository's dependencies, and the expensive build happens the first time a
repository is seen and is reused across every task and session after.

Three properties make that safe:

1. **The cache key is exactly the dependency set.** It is a hash of the base
   image reference, the *contents* of the manifests and lockfiles the stack
   detector named, and the build-time setup commands — and nothing else. A
   lockfile change produces a new key and rebuilds; an unrelated source
   change produces the same key and reuses. This is the whole of "invalidate
   on a dependency change and on nothing else".
2. **The base image is pinned by digest (REPRO-04).** The tag (``python:3.12
   -slim``) is resolved to an immutable ``sha256`` digest at build time and
   the Dockerfile is written ``FROM ref@sha256:…``, so a task built today and
   a task built after the tag floats to new content get the same base. The
   resolved digest is recorded on the image as a label.
3. **The cache is bounded and inspectable.** Every image carries mcgyvr
   labels; :func:`list_cached` reads them back with sizes, :func:`prune`
   evicts the oldest beyond a bound, and :func:`clear` removes them outright.
   The eviction rule is deliberately dull — oldest-created first — so it is
   predictable rather than clever.

Nothing here runs Docker directly: every call goes through a
:data:`DockerRunner`, so the argv and the generated Dockerfile are what a
test asserts on, and a machine without a daemon is never required to check
the logic (the pattern :mod:`mcgyvr.detect` established).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.sandbox.stack import Stack

# Labels stamped on every image mcgyvr builds, so the cache is discoverable
# and prunable without guessing at names.
LABEL_REPO = "mcgyvr.repo"
LABEL_KEY = "mcgyvr.cache-key"
LABEL_BASE_DIGEST = "mcgyvr.base-digest"

# Bound on how many task images the cache keeps. Oldest beyond this are
# evicted. A default, not a law: a real ceiling belongs in config, and this
# is only what an unconfigured install falls back to.
DEFAULT_MAX_CACHED_IMAGES = 8

# The variables that point `docker` at another daemon. The sandbox runs on
# this machine's daemon and nowhere else: a container the product starts must
# never land on a rig, and the door (python -m mcgyvr.serving.run) is the only
# way there. So the one runner that spawns docker refuses under either — it
# does not honour the variable, and it does not strip it and carry on.
DAEMON_OVERRIDES = ("DOCKER_HOST", "DOCKER_CONTEXT")


def foreign_daemon() -> str | None:
    """Why docker must not be spawned now, or None: a daemon override is set."""
    for name in DAEMON_OVERRIDES:
        if name in os.environ:
            return (
                f"the sandbox runs on this machine's daemon; {name}="
                f"{os.environ[name]} is set, and a container the product starts "
                "must never land on a rig — the door (python -m "
                "mcgyvr.serving.run) is the only way there"
            )
    return None


class ImageError(Exception):
    """A task image could not be resolved, built, or inspected."""


@dataclass(frozen=True)
class DockerResult:
    """The outcome of one ``docker`` invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# The seam. A runner takes docker's argv (without the leading "docker") and
# optional stdin, and returns the result. Production uses the subprocess
# runner below; tests pass a stub that records argv and returns canned output.
DockerRunner = Callable[[Sequence[str], "bytes | None"], DockerResult]


def subprocess_runner(args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
    """Run a real ``docker`` command. The default :data:`DockerRunner`.

    The one place the product builds a docker argv for its own daemon, so the
    one place :func:`foreign_daemon` is applied: with ``DOCKER_HOST`` or
    ``DOCKER_CONTEXT`` set nothing is spawned, and the result carries the
    refusal as its stderr, which every caller raises as its own error.
    """
    refusal = foreign_daemon()
    if refusal is not None:
        return DockerResult(2, "", refusal)
    if shutil.which("docker") is None:
        return DockerResult(127, "", "docker is not on PATH")
    try:
        done = subprocess.run(
            ["docker", *args],
            input=stdin,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return DockerResult(1, "", str(exc))
    return DockerResult(
        returncode=done.returncode,
        stdout=done.stdout.decode("utf-8", "replace"),
        stderr=done.stderr.decode("utf-8", "replace"),
    )


@dataclass(frozen=True)
class TaskImage:
    """A resolved task image: its tag, its pinned base, and whether it was built."""

    tag: str
    base_digest: str
    cache_key: str
    built: bool  # False means it was already cached — the point of the cache


@dataclass(frozen=True)
class CachedImage:
    """One image in the cache, as read back from Docker's own metadata."""

    tag: str
    repo: str
    cache_key: str
    size_bytes: int
    created: str


def cache_key(stack: Stack, repo: Path, setup: Sequence[str]) -> str:
    """The content hash that decides when the image rebuilds.

    Built from the base reference, each manifest's path and bytes, the install
    commands and the setup commands — the complete and only inputs to the
    dependency set. Manifests are read in sorted order so the key is
    independent of detection order, and their *content* is hashed so an edit
    to a lockfile changes the key while a rename of an unrelated source file
    does not.
    """
    hasher = hashlib.sha256()
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
    for setup_command in setup:
        hasher.update(f"setup:{setup_command}\n".encode())
    return hasher.hexdigest()[:16]


def image_tag(repo: Path, key: str) -> str:
    """The tag a repository's task image is stored under.

    ``mcgyvr/<repo-slug>:<cache-key>`` — the slug keeps images legible in
    ``docker images`` and the key in the tag means a dependency change lands
    as a distinct image rather than overwriting the last one.
    """
    return f"mcgyvr/{_slug(repo.resolve().name)}:{key}"


def render_dockerfile(stack: Stack, base_digest_ref: str, setup: Sequence[str]) -> str:
    """Generate the Dockerfile that installs the repository's dependencies.

    Only the manifests are copied into the build — never the whole repository
    — so the image is the dependency layer and nothing else, and the source
    the worker changes is mounted at task time rather than baked in.
    """
    lines = [
        f"FROM {base_digest_ref}",
        "WORKDIR /workspace",
    ]
    manifests = stack.manifest_paths()
    if manifests:
        # Copy each manifest to its own path so a nested one keeps its
        # location; the install commands assume the repository layout.
        for name in manifests:
            lines.append(f"COPY {name} {name}")
    for command in stack.install_commands():
        lines.append("RUN " + " && ".join(command))
    for setup_command in setup:
        lines.append(f"RUN {setup_command}")
    return "\n".join(lines) + "\n"


def resolve_base_digest(base_ref: str, runner: DockerRunner) -> str:
    """Pull ``base_ref`` and return its immutable ``ref@sha256:…`` (REPRO-04).

    The tag is pulled so the digest reflects what would actually run, then
    read from the local image's repo-digests. A base that cannot be resolved
    to a digest is an error, not a silent fall back to the floating tag —
    reproducibility is the whole point.
    """
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
            f"{digest_ref!r}. A base image must pin to a digest (REPRO-04)."
        )
    return digest_ref


def image_present(tag: str, runner: DockerRunner) -> bool:
    """Whether an image with ``tag`` already exists locally."""
    return runner(["image", "inspect", tag], None).ok


def ensure_image(
    stack: Stack,
    repo: Path,
    setup: Sequence[str] = (),
    *,
    runner: DockerRunner = subprocess_runner,
) -> TaskImage:
    """Return the repository's task image, building it once if it is absent.

    The first task for a repository pays the build; every task after finds the
    tag present and returns immediately (``built=False``). A change to a
    manifest changes the cache key, hence the tag, hence triggers exactly one
    rebuild.
    """
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

    if stack.base_image is None:  # pragma: no cover — detected implies a base
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
    """Build ``tag`` from a context holding only the manifests and Dockerfile."""
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
    """Every image mcgyvr has cached, newest first, with its size.

    Reads Docker's own metadata filtered to the mcgyvr repo label, so the
    cache is inspectable without a side ledger that could drift from reality.
    """
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
    # Newest first: Docker returns creation order-ish, but sort explicitly so
    # the eviction rule does not depend on listing order.
    images.sort(key=lambda c: c.created, reverse=True)
    return tuple(images)


def prune(
    max_images: int = DEFAULT_MAX_CACHED_IMAGES,
    *,
    runner: DockerRunner = subprocess_runner,
) -> tuple[str, ...]:
    """Evict the oldest images beyond ``max_images``. Returns what was removed.

    The rule is oldest-created-first, which is predictable and needs no access
    tracking. Removing an image only costs the next task for that repository a
    rebuild, so an over-eager bound is a performance choice, never a
    correctness one.
    """
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
    """Remove cached images — all of them, or one repository's. Returns removed.

    The documented way to reset the cache (#29). Scoped to mcgyvr's own label
    so it never touches an image the user built themselves.
    """
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
    """A docker-safe repository slug: lowercase, ``[a-z0-9._-]`` only."""
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in name.lower())
    return safe.strip("-._") or "repo"


def _int(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0
