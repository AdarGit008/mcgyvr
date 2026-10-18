"""Per-repo task images: key them, build them, list them, evict them.

The cache key digests everything a dependency install depends on - the
generated Dockerfile layout version, the base image, the manifest contents,
and the install, checker and setup commands - so an unchanged dependency set
reuses one tag, and editing source never invalidates an image. Built images
are labelled with the repo slug, the key and the pinned base digest, which
lets the cache be listed and trimmed from Docker's own state instead of a
side file.

Every docker invocation goes through a :data:`DockerRunner`, so the argv, the
rendered Dockerfile and the key arithmetic can be checked on a machine with
no daemon.
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

from mcgyvr.sandbox.stack import NODE_MODULES, TOOL_PATH, VENV, WORKSPACE, Stack

# Labels stamped onto every image built here; `list_cached` filters the cache
# on the repo label, and a reused image's base digest is read from its label.
LABEL_REPO = "mcgyvr.repo"
LABEL_KEY = "mcgyvr.cache-key"
LABEL_BASE_DIGEST = "mcgyvr.base-digest"

#: Version of the Dockerfile layout :func:`render_dockerfile` produces. It is
#: hashed into the cache key, so changing how images are built changes the tags
#: instead of silently reusing images built the old way. Bump it whenever that
#: rendering changes in a way existing images cannot serve.
IMAGE_LAYOUT = 2

#: Workspace-relative folders an install fills inside the image (.venv,
#: node_modules). The container mounts an anonymous volume over each one it
#: finds populated, so writes land in the volume, not in the host checkout.
SEEDABLE = tuple(path.removeprefix(f"{WORKSPACE}/") for path in (VENV, NODE_MODULES))

# How many images :func:`prune` keeps when the caller does not say: room for a
# few repositories on recent dependency sets, and a bound on how large the
# cache can grow.
DEFAULT_MAX_CACHED_IMAGES = 8

# Environment variables that would aim the docker CLI at a daemon other than
# this machine's. Any of them being set is a refusal, because the sandbox runs
# on the local daemon and reaching another one is what the door
# (python -m mcgyvr.serving.run) is for.
# :func:`foreign_daemon` is the single place this tuple is read.
DAEMON_OVERRIDES = ("DOCKER_HOST", "DOCKER_CONTEXT")


def foreign_daemon() -> str | None:
    """Why the docker CLI cannot be trusted here, or ``None`` if it can.

    Returns a refusal naming the first :data:`DAEMON_OVERRIDES` variable found
    in the environment, and ``None`` when none is set - i.e. when the CLI
    would talk to this machine's daemon.
    """
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
    """An image could not be keyed, resolved, listed or built."""


@dataclass(frozen=True)
class DockerResult:
    """One finished docker invocation: exit status plus captured output.

    Failures are returned, never raised, so a caller decides whether a
    non-zero exit is fatal.
    """

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# Timeouts and conventions for the real CLI behind :func:`subprocess_runner`.
# Ordinary verbs are bounded tightly; `build` and `pull` are not, because a
# cold layer cache or a slow registry legitimately takes minutes.
# Failures follow the shell's conventions: exit 124 when the bound expires, 127
# when docker is missing, 2 when the daemon is overridden, so a caller sees
# every failure as a DockerResult and no exception escapes this layer.
# _LONG_VERBS is the set that earns DOCKER_BUILD_TIMEOUT_S; every other verb is
# held to DOCKER_CALL_TIMEOUT_S, which is a backstop against a hung CLI rather
# than a budget for how long an install may take.
# Both values are in seconds, the unit subprocess.run takes, and the pair is
# module level so a bound can be reasoned about without reading the runner's
# body; :func:`subprocess_runner` is the only place either one is used.
DOCKER_CALL_TIMEOUT_S = 120.0
DOCKER_BUILD_TIMEOUT_S = 3600.0
_LONG_VERBS = frozenset({"build", "pull"})


# The seam: a callable that takes docker argv plus optional stdin and reports
# the outcome. Tests pass recording stubs through it, so none of this module
# needs a daemon to be checked.
DockerRunner = Callable[[Sequence[str], "bytes | None"], DockerResult]


def subprocess_runner(args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
    """Run the real docker CLI, reporting the result instead of raising.

    Refuses before spawning anything when the daemon is overridden (see
    :func:`foreign_daemon`, exit 2) or when docker is not on PATH (exit 127),
    with the reason in stderr. `build` and `pull` get
    :data:`DOCKER_BUILD_TIMEOUT_S` and every other verb
    :data:`DOCKER_CALL_TIMEOUT_S`; an expired bound gives exit 124. `stdin` is
    fed to the process, and both streams are decoded leniently.
    """
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
    """The image a task runs in: its tag, its cache key, its pinned base.

    `base_digest` is what the image was built from - resolved for a fresh
    build, read back from :data:`LABEL_BASE_DIGEST` for a cache hit.
    """

    tag: str
    base_digest: str
    cache_key: str
    built: bool  # True when this call built it, False when the cache had it


@dataclass(frozen=True)
class CachedImage:
    """One image found in the cache, as read back from docker.

    `repo` and `cache_key` come from :data:`LABEL_REPO` and :data:`LABEL_KEY`;
    `created` is docker's own timestamp string, which is what :func:`prune`
    orders the cache by.
    """

    tag: str
    repo: str
    cache_key: str
    size_bytes: int
    created: str


def cache_key(stack: Stack, repo: Path, setup: Sequence[str]) -> str:
    """Digest the inputs of the dependency install into a 16-character key.

    Hashed in order: the layout version, the base image reference, each
    manifest's name and bytes, each language's install command, each checker
    command, and the caller's setup commands. Source files are absent by
    design, so editing code keeps the image while moving a dependency does
    not. A manifest that cannot be read raises :class:`ImageError` rather than
    keying an image that could not have been built from it.
    """
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
    """Name an image after its repo directory and its cache key.

    The slug keeps the tag legible in `docker image ls`; the key keeps two
    dependency sets of one repository apart, so a rebuilt set lands on a new tag
    instead of overwriting the image another checkout is still using.
    """
    return f"mcgyvr/{_slug(repo.resolve().name)}:{key}"


def render_dockerfile(stack: Stack, base_digest_ref: str, setup: Sequence[str]) -> str:
    """Render the Dockerfile that builds a stack on ``base_digest_ref``.

    The order is what makes the layer cache useful: workdir, then PATH, then
    only the manifests (so the install layers survive source edits), then one
    RUN per language joining its install command, then the checker installs,
    then the caller's setup commands last so they see the installed tooling.
    """
    lines = [
        f"FROM {base_digest_ref}",
        "WORKDIR /workspace",
        # PATH leads with the tool path, so the venv's and node_modules/.bin's
        # executables are what `python`, `pytest` and `npx` resolve to in every
        # RUN below, and in the container's own shell.
        f"ENV PATH={TOOL_PATH}:$PATH",
    ]
    manifests = stack.manifest_paths()
    if manifests:
        # Manifests only, never the source tree: the install layers below stay
        # valid until a dependency actually changes.
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
    """Ask the image which of its seeded folders the install actually filled.

    Runs a network-less throwaway container from `tag` that echoes each of
    :data:`SEEDABLE` that exists and is non-empty, and returns those folders in
    :data:`SEEDABLE` order. A failed run, or a folder the install left empty,
    just drops out of the tuple; the caller then mounts volumes over the
    folders that are really there.
    """
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
    """Pull ``base_ref`` and return it pinned to its sha256 digest.

    Building from a digest rather than a tag is what keeps a cache key honest:
    one key can then only mean one base. An unpullable base, or one whose first
    RepoDigest carries no ``@sha256:`` reference, raises :class:`ImageError`.
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
            f"{digest_ref!r}. A base image must pin to a digest."
        )
    return digest_ref


def image_present(tag: str, runner: DockerRunner) -> bool:
    """Whether a local image with this tag exists."""
    return runner(["image", "inspect", tag], None).ok


def ensure_image(
    stack: Stack,
    repo: Path,
    setup: Sequence[str] = (),
    *,
    runner: DockerRunner = subprocess_runner,
) -> TaskImage:
    """Return this repository's task image, building it only if it is missing.

    :func:`cache_key` picks the tag, so an image already present is reused and
    its base digest is read back from :data:`LABEL_BASE_DIGEST`. Otherwise the
    base is resolved to a digest, the Dockerfile rendered, and the image built
    with the labels :func:`list_cached` later needs. A stack that was never
    detected, or a build docker rejected, raises :class:`ImageError`.
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
    """Build `tag` from a throwaway context holding the Dockerfile and manifests.

    The repository is not the build context: the Dockerfile and the manifests
    are copied into a temp directory and only that directory is sent, so no
    source tree reaches the daemon. The repo slug, key and base digest are
    attached as labels, and a rejected build raises :class:`ImageError`
    carrying docker's stderr.
    """
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
    """List the images this module built, newest first.

    Docker is asked for the ids carrying :data:`LABEL_REPO`, then each id is
    inspected for its first tag, size, creation time, repo slug and cache key.
    An image that disappears between the two calls, or reports an unexpected
    field count, is skipped; an unparseable size becomes 0. A listing that
    cannot be taken at all raises :class:`ImageError`.
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
    # Newest first: docker's creation timestamps order lexically, and :func:`prune`
    # evicts from the tail, so this sort decides what survives.
    images.sort(key=lambda c: c.created, reverse=True)
    return tuple(images)


def prune(
    max_images: int = DEFAULT_MAX_CACHED_IMAGES,
    *,
    runner: DockerRunner = subprocess_runner,
) -> tuple[str, ...]:
    """Keep the ``max_images`` newest cached images and remove the rest.

    Returns the tags actually removed; an image docker refuses to remove is
    left in place and omitted from the result. A negative bound raises
    :class:`ImageError`, and a bound of 0 empties the cache.
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
    """Remove every cached image, or only those built from ``repo_slug``.

    Works off the same listing as :func:`prune`, so only images carrying this
    module's labels are ever touched, and returns the tags removed.
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
    """Make a repo directory name usable as a docker repository name.

    Lowercased, with anything outside alphanumerics and ``._-`` replaced by
    ``-`` and any leading or trailing separator trimmed; a name with no usable
    character left becomes ``repo``.
    """
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in name.lower())
    return safe.strip("-._") or "repo"


def _int(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0
