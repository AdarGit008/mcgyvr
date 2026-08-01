"""Command-line entrypoint.

Only what is built is exposed. Subcommands appear here as they land; the
scope of record for what is coming is the issue tree.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mcgyvr import __version__
from mcgyvr.capability import CapabilityTableError, load


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

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
