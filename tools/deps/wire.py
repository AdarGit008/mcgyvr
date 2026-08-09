"""Edit the issue tree's dependency graph, and prove every write landed.

GitHub's issue-dependency endpoints take the issue's numeric ``id``, not its
number, and ``issue_id`` must be an **integer**::

    POST   /repos/{o}/{r}/issues/{n}/dependencies/blocked_by   {"issue_id": <int>}
    DELETE /repos/{o}/{r}/issues/{n}/dependencies/blocked_by/{issue_id}

``gh api -f issue_id=123`` sends a *string*, which the API rejects with
``422 Invalid property /issue_id``. ``gh api -F issue_id=123`` sends an integer
and works. That distinction cost roughly twenty silently-discarded edges while
wiring the ADR-0018 restructure on 2026-08-09, and it is the reason this module
exists rather than a shell loop.

Two things made a one-character difference expensive, and both are designed out
here:

* **The failure is invisible under ``--silent``**, which is exactly the flag a
  loop over dozens of edges reaches for. Twenty edges reported as written; none
  were.
* **Nothing read the graph back.** The loss surfaced only in a manual survey
  afterwards.

So every mutation in this module is followed by a read of the live graph, and a
write that did not land is a named failure and a non-zero exit — never silence.
This is the same discipline ``tests/test_claims.py`` states for vendored
evidence: a report is only evidence if something checked it against the source.

Ids are resolved from the API at call time rather than from a cached map. A
stale or short-a-page cache degrades into ``issue_id=""``, which fails with the
same 422 and the same silence — one of the two real failures on 2026-08-09.

Usage::

    python tools/deps/wire.py show                 # the whole graph
    python tools/deps/wire.py show 229 230         # just these
    python tools/deps/wire.py block 230 --by 229   # 230 is blocked by 229
    python tools/deps/wire.py unblock 230 --by 229
    python tools/deps/wire.py block 3 4 5 --by 234 # fan one blocker over many
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence

TIMEOUT_S = 60


class WireError(RuntimeError):
    """A dependency edit could not be made, or could not be proven."""


def _gh(args: Sequence[str]) -> str:
    """Run ``gh`` and return stdout, raising with stderr on failure.

    Deliberately not ``--silent``: a discarded write is the failure this module
    exists to prevent, so the error text is kept and surfaced.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        raise WireError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def issue_id(number: int) -> int:
    """The numeric id the dependency endpoints want, read live.

    Not cached: a map missing one issue yields ``issue_id=""``, which fails the
    same silent way the string/integer confusion does.
    """
    out = _gh(["api", f"repos/:owner/:repo/issues/{number}", "--jq", ".id"]).strip()
    if not out:
        raise WireError(f"#{number}: no id returned — does the issue exist?")
    return int(out)


def blocked_by(number: int) -> list[int]:
    """The issue numbers currently blocking ``number``."""
    out = _gh(
        [
            "api",
            f"repos/:owner/:repo/issues/{number}/dependencies/blocked_by",
            "--jq",
            "[.[].number]",
        ]
    ).strip()
    return sorted(json.loads(out)) if out else []


def _edit(number: int, blocker: int, *, add: bool) -> None:
    """Add or remove one edge, then read the graph back to prove it."""
    bid = issue_id(blocker)
    if add:
        _gh(
            [
                "api",
                "-X",
                "POST",
                f"repos/:owner/:repo/issues/{number}/dependencies/blocked_by",
                # -F, not -f: -f sends a string and the API rejects it.
                "-F",
                f"issue_id={bid}",
            ]
        )
    else:
        _gh(
            [
                "api",
                "-X",
                "DELETE",
                f"repos/:owner/:repo/issues/{number}/dependencies/blocked_by/{bid}",
            ]
        )

    present = blocker in blocked_by(number)
    if present is not add:
        wanted = "add" if add else "remove"
        raise WireError(
            f"#{number} <- #{blocker}: {wanted} reported success but the graph "
            f"disagrees. This is the silent-write failure mode; do not assume "
            f"any sibling edge landed either."
        )


def apply(numbers: Sequence[int], blocker: int, *, add: bool) -> int:
    """Edit one edge per number. Returns the count that landed.

    Partial failure is reported per edge rather than collapsed into one verdict,
    because a loop that half-worked is the case that needs naming.
    """
    landed, failed = 0, []
    arrow = "<-" if add else "-x"
    for n in numbers:
        try:
            _edit(n, blocker, add=add)
        except WireError as exc:
            failed.append((n, str(exc)))
            print(f"  #{n} {arrow} #{blocker}  FAILED", file=sys.stderr)
        else:
            landed += 1
            print(f"  #{n} {arrow} #{blocker}")

    print(f"{landed}/{len(numbers)} edges {'added' if add else 'removed'}")
    for n, why in failed:
        print(f"  #{n}: {why}", file=sys.stderr)
    return landed


def open_issue_numbers() -> list[int]:
    """Every open issue, pull requests excluded."""
    out = _gh(
        [
            "api",
            "repos/:owner/:repo/issues?state=open&per_page=100",
            "--paginate",
            "--jq",
            "[.[] | select(.pull_request | not) | .number]",
        ]
    )
    numbers: list[int] = []
    for chunk in out.splitlines():
        if chunk.strip():
            numbers.extend(json.loads(chunk))
    return sorted(set(numbers))


def show(numbers: Sequence[int]) -> None:
    """Print the graph. Unblocked issues are listed too — absence is a fact."""
    targets = list(numbers) or open_issue_numbers()
    blocked, free = [], []
    for n in targets:
        deps = blocked_by(n)
        (blocked if deps else free).append((n, deps))
    for n, deps in blocked:
        print(f"  #{n:<5} <- {','.join(str(d) for d in deps)}")
    print(f"\n{len(free)} unblocked of {len(targets)}: ", end="")
    print(" ".join(f"#{n}" for n, _ in free))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="print the dependency graph")
    p_show.add_argument("numbers", nargs="*", type=int)

    for name, helptext in (("block", "add a blocker"), ("unblock", "remove one")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("numbers", nargs="+", type=int)
        p.add_argument("--by", required=True, type=int, help="the blocking issue")

    args = parser.parse_args(argv)

    try:
        if args.command == "show":
            show(args.numbers)
            return 0
        landed = apply(args.numbers, args.by, add=args.command == "block")
    except WireError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0 if landed == len(args.numbers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
