"""Command-line interface package for mcgyvr.

Re-exports the dispatcher's two public entry points: ``build_parser``, which
constructs and returns the configured ``argparse`` parser, and ``main``, which
parses ``argv`` and dispatches to the selected subcommand.
"""

from mcgyvr.cli.dispatcher import build_parser, main

__all__ = ["build_parser", "main"]
