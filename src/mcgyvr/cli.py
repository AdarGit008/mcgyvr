"""Command-line entrypoint.

Only what is built is exposed. Subcommands appear here as they land; the
scope of record for what is coming is the issue tree.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mcgyvr import __version__
from mcgyvr.capability import CapabilityTableError, load
from mcgyvr.config import CONFIG_FILENAME, CONFIG_PATH_ENV, ConfigError
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import load as load_config


def _capabilities(args: argparse.Namespace) -> int:
    try:
        table = load()
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    models = table.fitting(args.vram) if args.vram else table.models
    if args.vram:
        print(f"Measured models that fit {args.vram:g} GB with working headroom:\n")
    else:
        print("Measured models:\n")

    for model in sorted(models, key=lambda m: m.best_quality or 0, reverse=True):
        quality = model.best_quality
        score = f"{quality:.1%}" if quality is not None else "unmeasured"
        backend = f" [{model.requires_backend} only]" if model.requires_backend else ""
        print(
            f"  {model.id:<28} {model.vram_gb_working:>5.1f} GB  {score:>10}{backend}"
        )

    if table.caveats:
        print("\nHarness caveats that invalidate naive re-measurement:")
        for caveat in table.caveats:
            print(f"  {caveat.id} [{caveat.severity}] {caveat.summary}")
    return 0


def _config(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else resolve_config_path()
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{config.path}: valid\n")
    print("Sources:")
    for source in config.sources.values():
        credential = (
            f"key from ${source.api_key_env}" if source.api_key_env else "no credential"
        )
        print(
            f"  {source.name:<16} {source.api:<8} {source.base_url:<32} "
            f"x{source.max_parallel}  ({credential})"
        )

    print("\nLadder, cheapest first:")
    for tier in config.ladder.tiers:
        print(f"  {tier.name:<16} {tier.model:<32} on {tier.source}")

    if config.is_local_only:
        print(
            "\nEvery rung runs locally: this install needs no API key, and the "
            "deterministic gate is its acceptance bar."
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
    )
    parser.add_argument("--version", action="version", version=f"mcgyvr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    caps = sub.add_parser(
        "capabilities",
        help="show the shipped capability table used to propose worker bindings",
    )
    caps.add_argument(
        "--vram",
        type=float,
        default=None,
        metavar="GB",
        help="show only models that fit this much VRAM with working headroom",
    )
    caps.set_defaults(func=_capabilities)

    conf = sub.add_parser(
        "config",
        help="validate the configuration file and show what it resolves to",
    )
    conf.add_argument(
        "path",
        nargs="?",
        default=None,
        help=f"config to read (default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})",
    )
    conf.set_defaults(func=_config)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
