"""mcgyvr command line — a package after the split of cli.py.

Re-exports the two public entrypoint names.
"""

from mcgyvr.cli.dispatcher import build_parser, main

__all__ = ["build_parser", "main"]
