#!/usr/bin/env python3
"""Query the mcgyvr OKF bundle.

The shipped `okf-rag query` hardcodes its own repo's `okf/` bundle (only
build/update/ensure/status accept --corpus), so a bundle living in another
repo is not reachable through it. This wrapper points get_knowledge() at
mcgyvr's bundle instead. OKF-only: it does not consult pgvector, so a
fuzzy query returns NONE rather than WEAK.

NOTE ON THE TRUST GATE. get_knowledge() returns STRONG only when a concept is
HUMAN_REVIEWED (`verified.by` starts with "human:"), status is stable, and it is
not stale (okf_rag/api.py::_okf_result). Every concept here is signed
`machine:claude-opus-5`, so get_knowledge ABSTAINS on all of them by design —
the store refuses to serve machine-generated findings as authoritative until a
human signs off. Use --raw to read one before signing, and `sign` to promote it.

    python3 tools/okf/query.py "serving/vllm/enforce-eager-cost"
    python3 tools/okf/query.py --raw "serving/method/run-to-run-spread"
    python3 tools/okf/query.py --list
    python3 tools/okf/query.py --sign serving/method/run-to-run-spread --as human:adar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OKF_RAG_SRC = Path("/home/adaramir/pi_agent/projects/okf-rag/src")
BUNDLE = Path(__file__).resolve().parents[2] / "okf"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("--exact", action="store_true", help="demand a verbatim answer")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true", help="list every concept ID")
    ap.add_argument(
        "--raw",
        action="store_true",
        help="read the concept directly, bypassing the trust gate",
    )
    ap.add_argument(
        "--sign",
        metavar="CONCEPT_ID",
        help="promote a concept to human-reviewed after you have read it",
    )
    ap.add_argument(
        "--as",
        dest="signer",
        default="human:adar",
        help="signer for --sign (default: human:adar)",
    )
    ap.add_argument("--bundle", type=Path, default=BUNDLE)
    ap.add_argument(
        "--src", type=Path, default=OKF_RAG_SRC, help="okf_rag package source dir"
    )
    args = ap.parse_args(argv)

    if not args.src.is_dir():
        print(f"okf_rag source not found at {args.src}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(args.src))
    from okf_rag.api import configure, get_knowledge
    from okf_rag.models import trust_tier
    from okf_rag.okf.db import OkfDb

    db = OkfDb(args.bundle)

    if args.list:
        for c in sorted(db.list(prefix=""), key=lambda c: c.concept_id):
            verdict = next(
                (t.split(":", 1)[1] for t in c.tags if t.startswith("verdict:")), "-"
            )
            print(
                f"{c.concept_id:<58} {verdict:<10} {c.status:<12} {trust_tier(c).name}"
            )
        return 0

    if args.sign:
        import datetime as _dt

        path = args.bundle / (args.sign + ".md")
        if not path.is_file():
            print(f"no such concept: {args.sign}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        import re as _re

        new, n = _re.subn(
            r"^verified: \{[^}]*\}$",
            f"verified: {{ by: {args.signer}, at: {stamp} }}",
            text,
            count=1,
            flags=_re.M,
        )
        if not n:
            print("no verified: line to replace", file=sys.stderr)
            return 2
        path.write_text(new, encoding="utf-8")
        print(f"signed {args.sign} as {args.signer} at {stamp}")
        print(
            "NOTE: build_okf.py reads approvals.json, so a rebuild "
            "restores this signature. Editing the file by hand does not."
        )
        return 0

    if not args.query:
        ap.error("a query is required unless --list is given")

    if args.raw:
        c = db.lookup(args.query)
        if c is None:
            print("no such concept", file=sys.stderr)
            return 1
        print(f"# {c.concept_id}")
        print(f"status={c.status} tier={trust_tier(c).name} stale={db.is_stale(c)}")
        print(f"sources={[s.resource for s in c.sources]}")
        print()
        print(c.body)
        return 0

    configure(okf_db=db, rag=None)
    result = get_knowledge(args.query, requires_quote=args.exact)

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "signal_strength": result.signal_strength.name,
                    "exact": result.exact,
                    "data": result.data,
                    "provenance": [
                        {
                            "concept_id": p.concept_id,
                            "quote": p.quote,
                            "source_uri": p.source_uri,
                            "title": p.title,
                        }
                        for p in result.provenance
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(f"signal: {result.signal_strength.name}  exact: {result.exact}")
    if result.signal_strength.name == "NONE":
        c = db.lookup(args.query)
        if c is not None:
            print(
                f"  concept EXISTS but the trust gate refused it: "
                f"tier={trust_tier(c).name} status={c.status} "
                f"stale={db.is_stale(c)}"
            )
            print(
                "  STRONG needs HUMAN_REVIEWED + stable + not stale. "
                "Read it with --raw, then --sign it."
            )
    if result.provenance:
        print("provenance:")
        for p in result.provenance:
            print(f"  - {p.concept_id}  ({p.source_uri or 'no uri'})")
    print()
    print(result.data or "(abstained — no matching concept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
