"""Rewrite an issue body, and prove the text that landed is the text you sent.

``gh issue edit N --body-file F`` **blanks the body and exits 0** when ``F`` is
empty. It happened on 2026-08-02 and again while rewriting bodies for #234, and
it is the same shape as the defect ``tools/deps/wire.py`` was built for: a write
that fails into a plausible success. #235 deliberately left this out of that
module — a dependency tool that also edits bodies is a general ``gh`` wrapper —
so the guard lives here, next to the job that needs it.

Three properties, one per way the edit can lie about itself:

* **An empty or whitespace-only file is refused before ``gh`` is called**, so the
  blanking cannot happen by construction rather than being noticed afterwards.
* **The prior body is saved to ``<file>.prev`` first**, so recovery is local and
  needs no network. GitHub also keeps prior bodies, and the query is printed on
  failure, but a file on disk is the cheaper answer.
* **The live body is read back and compared to what was sent.** A mismatch is a
  named failure and a non-zero exit, per issue, because a loop that half-worked
  is the case worth naming.

Line endings are normalised on both sides of that comparison and nowhere else.
GitHub stores bodies with CRLF, so a byte-exact check would fail every edit and
teach the next reader to ignore it — which is how a guard becomes decoration.

Usage::

    python tools/issues/body.py set 225 --from bodies/225.md
    python tools/issues/body.py set 16 17 71 --from-dir bodies/   # bodies/<N>.md
    python tools/issues/body.py verify 16 17 71 --from-dir bodies/
    python tools/issues/body.py get 225 --out /tmp/225.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

TIMEOUT_S = 60

RECOVERY_QUERY = (
    'gh api graphql -f query=\'{repository(owner:"OWNER",name:"REPO")'
    "{issue(number:N){userContentEdits(last:5){nodes{editedAt diff}}}}}'"
)


class BodyError(RuntimeError):
    """An issue body could not be written, or could not be proven written."""


def _gh(args: Sequence[str]) -> str:
    """Run ``gh`` and return stdout, raising with stderr on failure.

    Not ``--silent``, for the reason ``tools/deps/wire.py`` states: the
    discarded write is the subject.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        raise BodyError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _normalise(text: str) -> str:
    """Compare-only normalisation: CRLF and trailing blank lines.

    GitHub returns bodies CRLF-terminated whatever was sent, and drops a
    trailing newline. Neither is a difference in the text, and treating them as
    one would make every edit report a mismatch.
    """
    return text.replace("\r\n", "\n").rstrip("\n")


def live_body(number: int) -> str:
    """The body the issue holds right now."""
    out = _gh(["issue", "view", str(number), "--json", "body"])
    parsed = json.loads(out)
    body = parsed.get("body")
    if not isinstance(body, str):
        raise BodyError(f"#{number}: no body field in the API response")
    return body


def _read_new_body(path: Path, number: int) -> str:
    """Load the replacement text, refusing the file that blanks a body."""
    if not path.is_file():
        raise BodyError(f"#{number}: {path} does not exist")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise BodyError(
            f"#{number}: {path} is empty or whitespace-only. "
            f"`gh issue edit --body-file` would blank the body and exit 0."
        )
    return text


def _set_one(number: int, path: Path) -> bool:
    """Write one body and prove it landed. True if the issue changed."""
    new = _read_new_body(path, number)
    old = live_body(number)

    if _normalise(old) == _normalise(new):
        print(f"  #{number}  unchanged")
        return False

    prev = path.with_suffix(path.suffix + ".prev")
    prev.write_text(old, encoding="utf-8")

    _gh(["issue", "edit", str(number), "--body-file", str(path)])

    landed = live_body(number)
    if _normalise(landed) != _normalise(new):
        raise BodyError(
            f"#{number}: the edit reported success and the live body differs "
            f"from what was sent ({len(_normalise(landed))} chars live vs "
            f"{len(_normalise(new))} sent). Prior text saved to {prev}; "
            f"GitHub's own history: {RECOVERY_QUERY}"
        )
    print(
        f"  #{number}  rewritten "
        f"({len(_normalise(old))} -> {len(_normalise(new))} chars)"
    )
    return True


def _verify_one(number: int, path: Path) -> bool:
    """True when the live body already matches the file. Writes nothing."""
    new = _read_new_body(path, number)
    if _normalise(live_body(number)) == _normalise(new):
        print(f"  #{number}  matches")
        return True
    print(f"  #{number}  DIFFERS from {path}", file=sys.stderr)
    return False


def _paths_for(numbers: Sequence[int], args: argparse.Namespace) -> dict[int, Path]:
    if args.from_file is not None:
        if len(numbers) != 1:
            raise BodyError("--from takes exactly one issue; use --from-dir for many")
        return {numbers[0]: Path(args.from_file)}
    return {n: Path(args.from_dir) / f"{n}.md" for n in numbers}


def run(numbers: Sequence[int], paths: dict[int, Path], *, write: bool) -> int:
    """Apply or check every issue, reporting per issue. Returns the count OK."""
    ok, failed = 0, []
    for n in numbers:
        try:
            result = _set_one(n, paths[n]) if write else _verify_one(n, paths[n])
        except BodyError as exc:
            failed.append((n, str(exc)))
            print(f"  #{n}  FAILED", file=sys.stderr)
        else:
            # `set` returns whether the issue changed — an already-correct body
            # is still a success. `verify` returns whether it matches, and a
            # mismatch is the whole point of the command.
            if write or result:
                ok += 1
    verb = "written" if write else "verified"
    print(f"{ok}/{len(numbers)} {verb}")
    for n, why in failed:
        print(f"  #{n}: {why}", file=sys.stderr)
    return ok


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    for name, helptext in (
        ("set", "rewrite bodies from files, proving each landed"),
        ("verify", "check live bodies against files, writing nothing"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("numbers", nargs="+", type=int)
        src = p.add_mutually_exclusive_group(required=True)
        src.add_argument("--from", dest="from_file", help="one file, one issue")
        src.add_argument("--from-dir", dest="from_dir", help="a dir of <N>.md")

    p_get = sub.add_parser("get", help="save the live body to a file")
    p_get.add_argument("numbers", nargs=1, type=int)
    p_get.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "get":
            Path(args.out).write_text(live_body(args.numbers[0]), encoding="utf-8")
            print(f"  #{args.numbers[0]}  saved to {args.out}")
            return 0
        paths = _paths_for(args.numbers, args)
        ok = run(args.numbers, paths, write=args.command == "set")
    except BodyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0 if ok == len(args.numbers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
