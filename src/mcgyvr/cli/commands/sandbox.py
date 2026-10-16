"""The `mcgyvr sandbox` command.

Only what is built is exposed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
)
from mcgyvr.config import load as load_config

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

from mcgyvr.cli.common import _add_repo, _mib, add_config
from mcgyvr.cli.sandbox import _sandbox_policy, _say_what_the_sandbox_leaves_out


def _sandbox(args: argparse.Namespace) -> int:
    from mcgyvr.detect import detect_docker
    from mcgyvr.sandbox.base import SandboxError, choose_mode
    from mcgyvr.sandbox.image import ImageError, clear, list_cached
    from mcgyvr.sandbox.stack import detect_stack

    docker_ok, docker_how = detect_docker()

    if args.clear_cache:
        if not docker_ok:
            print(f"No Docker daemon, so nothing is cached ({docker_how}).")
            return 0
        removed = clear()
        print(f"Cleared {len(removed)} cached image(s).")
        for tag in removed:
            print(f"  removed {tag}")
        return 0

    if args.cache:
        if not docker_ok:
            print(f"No Docker daemon, so nothing is cached ({docker_how}).")
            return 0
        try:
            cached = list_cached()
        except ImageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not cached:
            print("Image cache is empty.")
            return 0
        total = sum(c.size_bytes for c in cached)
        print(f"Cached task images ({_mib(total)} total, newest first):\n")
        for image in cached:
            print(f"  {image.tag:<40} {_mib(image.size_bytes):>10}  [{image.repo}]")
        return 0

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 1
    _say_what_the_sandbox_leaves_out(repo)

    # Show what a run here would resolve to: the setup's `sandbox.mode` and
    # `sandbox.allow_fallback`, read as a run reads them. No setup at all is
    # the schema's defaults (`docker`, no fallback); a setup that cannot be
    # read has no resolved mode to show.
    chosen = Path(args.config) if getattr(args, "config", None) else None
    try:
        config: Config | None = load_config(chosen)
    except ConfigMissingError as exc:
        if chosen is not None:
            # Named with --config and not there: an error, as on `run`, not
            # the defaults a bare install reads.
            print(f"error: {exc}", file=sys.stderr)
            return 1
        config = None
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    configured = (
        config.get("sandbox.mode") if config is not None else None
    ) or "docker"
    try:
        choice = choose_mode(
            configured,
            docker_ok,
            allow_fallback=_sandbox_policy(config)["allow_fallback"],
        )
    except SandboxError as refused:
        print(f"Sandbox mode: refused  ({docker_how})")
        print(f"  - {refused}")
    else:
        print(f"Sandbox mode: {choice.mode}  ({docker_how})")
        for note in choice.notes:
            print(f"  - {note}")

    stack = detect_stack(repo)
    print(f"\nStack for {repo}:")
    if not stack.detected:
        for note in stack.notes:
            print(f"  - {note}")
        return 0

    print(f"  base image: {stack.base_image}")
    for component in stack.components:
        pin = "pinned" if component.pinned else "UNPINNED"
        print(
            f"  {component.language:<8} {component.package_manager:<8} "
            f"({pin}, {component.how})"
        )
        print(f"      install: {' && '.join(component.install)}")
        print(f"      manifests: {', '.join(component.manifests)}")
    for note in stack.notes:
        print(f"  - {note}")
    return 0


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `sandbox` command."""

    sbx = sub.add_parser(
        "sandbox",
        help="show the sandbox mode and the stack detected for a repository",
    )
    _add_repo(sbx, "the repository to inspect")
    sbx.add_argument(
        "--cache",
        action="store_true",
        help="list cached task images with their sizes instead of inspecting a repo",
    )
    sbx.add_argument(
        "--clear-cache",
        action="store_true",
        help="remove every task image mcgyvr has cached",
    )
    add_config(sbx, what="setup whose `sandbox` block a run here would read")
    sbx.set_defaults(func=_sandbox)
