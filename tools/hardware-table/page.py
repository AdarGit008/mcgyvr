#!/usr/bin/env python3
"""Read a public web page as plain text, for quoting it exactly.

  page.py URL --find "memory channels" --find "max memory speed"   windows at phrases
  page.py URL --dump [--at 12000] [--chars 4000]                   a slice of the text
  page.py URL                                                      status and length
  page.py URL --table --find "FP16"     the same, table cells and rows kept apart
  page.py URL --html "Numeric Format Support" [--chars 2500]       HTML at a phrase

The page is fetched once with a plain request (no key, no login) and cached under
``cache/`` (``verify_quotes.fetch``). Tags are removed, entities decoded and runs
of space made one space; nothing else is changed, so a phrase copied from this
output is the page's own wording. A page that answers anything but 200 is
reported, not worked around.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_quotes


def text_of(raw: str, table: bool = False) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", verify_quotes.marks(raw))
    if table:
        # Keep a table's shape: " | " after every cell (so an empty cell still
        # shows) and " // " after every row. Neither mark is part of the page:
        # leave them out of a quote.
        raw = re.sub(r"(?is)</t[dh]\s*>", " | ", raw)
        raw = re.sub(r"(?is)</tr\s*>", " // ", raw)
    raw = re.sub(r"(?is)</?(sup|sub|span|b|i|em|strong|a|font|u)\b[^>]*>", "", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = unicodedata.normalize("NFKC", html.unescape(raw))
    return re.sub(r"\s+", " ", raw).strip()


def _windows(text: str, phrase: str, width: int, most: int) -> None:
    low = text.lower()
    at, shown = 0, 0
    while shown < most:
        at = low.find(phrase.lower(), at)
        if at < 0:
            break
        print(f"--- {phrase!r} at {at}:")
        print(text[max(0, at - 60) : at + len(phrase) + width])
        at += len(phrase)
        shown += 1
    if not shown:
        print(f"--- {phrase!r}: not on the page")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("url")
    parser.add_argument(
        "--find", action="append", default=[], help="a phrase to show in context"
    )
    parser.add_argument(
        "--width", type=int, default=260, help="characters shown after a phrase"
    )
    parser.add_argument("--max", type=int, default=4, help="most windows per phrase")
    parser.add_argument(
        "--table",
        action="store_true",
        help="keep table cells (' | ') and rows (' // ') visible",
    )
    parser.add_argument(
        "--html",
        action="append",
        default=[],
        help="a phrase to show in the page's own HTML (tags and attributes kept)",
    )
    parser.add_argument("--dump", action="store_true", help="print a slice of the text")
    parser.add_argument("--at", type=int, default=0)
    parser.add_argument("--chars", type=int, default=4000)
    args = parser.parse_args()
    raw, how = verify_quotes.fetch(args.url)
    if raw is None:
        print(f"NOT READ: {how}  {args.url}")
        return 2
    text = text_of(raw, table=args.table)
    print(f"read: {how}, {len(text)} characters of text  {args.url}")
    for phrase in args.find:
        _windows(text, phrase, args.width, args.max)
    for phrase in args.html:
        source = re.sub(r"\s+", " ", raw)
        at = source.lower().find(phrase.lower())
        if at < 0:
            print(f"--- html {phrase!r}: not in the page")
            continue
        print(f"--- html {phrase!r} at {at}:")
        print(source[max(0, at - 60) : at + len(phrase) + args.chars])
    if args.dump:
        print(f"--- text {args.at}..{args.at + args.chars}:")
        print(text[args.at : args.at + args.chars])
    return 0


if __name__ == "__main__":
    sys.exit(main())
