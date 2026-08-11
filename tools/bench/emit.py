#!/usr/bin/env python3
"""#225 — write one paired bench problem's files from an authored spec.

**This emits files. It does not author problems.** Every word of prose, every
reference solution and every assertion is written by hand; what lives here is
only the part that is mechanical and easy to get subtly wrong — the exact
`contract.yaml` shape the strict schema accepts, the folded `task:` scalar, the
`demonstration`-versus-`acceptance` split that distinguishes a `bug_fix` from a
`function_implementation`, and the `meta.json` sidecar that belongs to the ts
arm alone.

Getting those wrong costs a gate rejection per problem, and the f1 band's
remaining tranches are a few hundred problems. The 40 problems of b228-b267
were emitted through this and all 40 were admitted on the first pass.

A spec is a plain dict. The keys are deliberately the same words the brief and
the gate use, so a spec can be read against either:

    {
      "id": "b228-tide-marks",
      "type": "function_implementation",     # or "bug_fix"
      "file_shape": "single_definition",     # or "multi_symbol"
      "shape": "numeric",
      "steering_band": "f1",
      "prose_ts": "...", "prose_py": "...",  # same problem, idiomatic names
      "iface_ts": "...", "iface_py": "...",
      "stop": "one genuine boundary the prose leaves unstated",
      "ref_ts": "...", "ref_py": "...",
      "acc_ts": "...", "acc_py": "...",
      "buggy_ts": "...", "buggy_py": "...",  # bug_fix only -> target_content
      "target_symbol": {"ts": "...", "py": "..."},   # multi_symbol only
      "risk": "low",
    }

`tools/bench/admit.py` remains the arbiter of whether a candidate is admitted:
it executes both checkers, degrades the declared target, and screens the prose.
The two screens below are not a second gate. They catch the two authoring
mistakes the gate is *structurally unable* to see, because in both the material
is perfectly correct — it is correct about the wrong thing.

**The divergence screen (:func:`divergences`).** A paired problem is one problem
twice, so it is only a fair pair if both languages answer its boundaries the
same way. Some do not. `round(4.5)` is `4` in Python — half-to-even, to keep a
column of rounded figures unbiased — and `5` in JavaScript. A problem stating
"a half rounds up" is therefore two different problems, and the idiomatic
solution passes ts and fails py while both references sail through the gate.
The arm difference then reads as a language finding that is really a defect in
the material. This is the same class as the `ValueError`-versus-`Error` checker
defect that made every past ts-vs-py contrast unreadable.

**The sibling screen (:func:`siblings`).** The gate screens *prose* at 0.55
Jaccard, which catches a problem restated in similar words. It cannot catch a
problem restated in a different domain, and that is the easy mistake to make:
"the next fan speed, wrapping to the first" and "who takes the next shift,
wrapping to the first" share almost no vocabulary and are one problem. What
they do share is the shape of their reference. So this screens the *reference's
token skeleton* — identifiers, literals and types erased, control flow and
operations kept — against every problem already in the tree.

Neither screen can be bypassed by an argument to :func:`emit`. A screen with an
override is a screen that gets overridden at the exact moment it matters.

Usage — author a module holding your specs and call :func:`emit` on each::

    from tools.bench.emit import emit
    emit(spec)                       # writes into tools/bench/tasks/
    emit(spec, root=tmp_path)        # or anywhere else

Or read the screens against what already exists, which is the cheaper order —
authoring against a sibling you have not read costs a whole problem::

    python tools/bench/emit.py --audit          # both screens over the tree
    python tools/bench/emit.py --near b228-tide-marks
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import textwrap
import token as _token
import tokenize
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
RESERVE = HERE / "reserve"

#: Per arm: directory name, reference filename, solution name, checker name and
#: the command the contract declares. The command is what the rig runs, so it
#: is stated here once rather than repeated in every spec.
ARMS = (
    ("ts", "reference.ts", "solution.ts", "accept.mjs", "node accept.mjs"),
    ("py", "reference.py", "solution.py", "accept.py", "python accept.py"),
)


def fold(prose: str) -> str:
    """The `task:` prose as a YAML folded scalar, wrapped and indented two."""
    body = " ".join(prose.split())
    return "\n".join("  " + line for line in textwrap.wrap(body, 68))


def contract(spec: dict[str, Any], arm: str, solution: str, command: str) -> str:
    """One arm's `contract.yaml`.

    A `bug_fix` declares its command under ``demonstration`` rather than
    ``acceptance`` because it must fail on the task's own starting file by
    design (#183); the gate reads that distinction, so it is derived from
    ``type`` here rather than left to the author to remember.
    """
    key = "demonstration" if spec["type"] == "bug_fix" else "acceptance"
    lines = [
        f"id: {spec['id']}",
        f"task_type: {spec['type']}",
        "task: >-",
        fold(spec[f"prose_{arm}"]),
        f"target: {solution}",
    ]
    buggy = spec.get(f"buggy_{arm}")
    if buggy is not None:
        lines.append("target_content: |")
        lines += ["  " + ln if ln.strip() else "" for ln in buggy.splitlines()]
    lines += [
        f'interface: "{spec[f"iface_{arm}"]}"',
        "stop_conditions:",
        f"  - {spec['stop']}",
        f'{key}: ["{command}"]',
        f"risk: {spec.get('risk', 'low')}",
        "scope:",
        f'  allow: ["{solution}"]',
    ]
    return "\n".join(lines) + "\n"


class EmitError(Exception):
    """A spec that must not be written as it stands."""


class Finding(NamedTuple):
    """One screen's complaint. ``fatal`` findings refuse the write."""

    screen: str
    fatal: bool
    detail: str


# --- screen one: constructs the two languages disagree about ---------------

#: ``(arm, pattern, fatal, what it costs)``. Fatal entries disagree on inputs a
#: problem is likely to test at all; the rest are latent — they part company
#: only outside ASCII or below zero, so they are reported and left to the
#: author, who may know the checker never goes there.
DIVERGENCES: tuple[tuple[str, str, bool, str], ...] = (
    (
        "py",
        r"\bround\s*\(",
        True,
        "python's round() is half-to-even (round(4.5) == 4) and JavaScript's "
        "Math.round is half-up (5). A problem whose prose says how a half "
        "rounds is two different problems. State the rounding as floor or "
        "ceiling, which agree, or compute it without the built-in in both arms",
    ),
    (
        "ts",
        r"\bMath\.round\s*\(",
        True,
        "Math.round is half-up and python's round() is half-to-even, so the "
        "idiomatic py answer fails a half that the idiomatic ts answer passes",
    ),
    (
        "ts",
        r"\bMath\.trunc\s*\(",
        False,
        "Math.trunc cuts toward zero and python's // floors toward minus "
        "infinity; they part company on negative values only",
    ),
    (
        "py",
        r"\.is(alpha|digit|alnum|space|upper|lower)\s*\(",
        False,
        "python's str.is*() are Unicode-aware and the ts twin will be an ASCII "
        "character class, so a non-ASCII input separates the arms",
    ),
    (
        "ts",
        r"\.localeCompare\s*\(",
        False,
        "localeCompare orders by locale and python's sorted() orders by code "
        "point; they part company on case and on accents",
    ),
)

#: A negative literal passed *into* a call — not merely expected back from one,
#: since a sentinel `-1` return never reaches the operator.
_NEGATIVE_ARGUMENT = re.compile(r"[A-Za-z_$][\w$]*\s*\([^()]*(?<![\w.])-\s*\d")

#: ``((x % n) + n) % n`` — the idiom that already makes a remainder agree across
#: the two languages. A reference carrying it has answered the divergence.
_NORMALISED = re.compile(r"%[^%()]*\)\s*\+\s*[\w.]+\s*\)\s*%")

#: ``.sort()`` with no comparator. What it was called on is read backwards by
#: :func:`_receiver`, since a regex cannot balance ``Object.keys(m).sort()``.
_BARE_SORT = re.compile(r"\.sort\s*\(\s*\)")


def _receiver(source: str, dot: int) -> str:
    """The expression a ``.sort()`` at ``dot`` was called on, read backwards."""
    end = dot
    while end and source[end - 1].isspace():
        end -= 1
    i = end
    while i:
        char = source[i - 1]
        if char in ")]":
            shut, open_ = char, "(" if char == ")" else "["
            depth = 0
            while i:
                i -= 1
                if source[i] == shut:
                    depth += 1
                elif source[i] == open_:
                    depth -= 1
                    if depth == 0:
                        break
        elif char.isalnum() or char in "_$.":
            i -= 1
        else:
            break
    return source[i:end].strip()


def _remainder(spec: dict[str, Any]) -> list[Finding]:
    """``%`` possibly reached by a negative, where the two languages differ.

    Raised as a warning and never as a refusal, because whether a negative
    actually *reaches* the operator is a dataflow question and this is a
    regex. ``Math.abs`` upstream, a divisibility test against zero, or an
    addend chosen to keep the numerator positive all make it safe, and none of
    those is decidable here. The obvious suppressions are applied so the
    warning stays worth reading.
    """
    checkers = (spec.get("acc_ts") or "") + (spec.get("acc_py") or "")
    if not _NEGATIVE_ARGUMENT.search(checkers):
        return []
    # Only the ts arm can be wrong. Python's % already takes the sign of the
    # divisor, which is the answer these problems want; it is JavaScript that
    # needs the normalising idiom written out.
    source = spec.get("ref_ts") or ""
    for line in source.splitlines():
        if not re.search(r"[^%]%[^%=]", line):
            continue
        if re.search(r"%[^;]*[=!]==?\s*0", line):  # a divisibility test
            continue
        if "Math.abs" in line or _NORMALISED.search(line):
            continue
        return [
            Finding(
                "divergence",
                False,
                "ref_ts takes a remainder and a checker passes in a negative: "
                "-7 % 3 is 2 in python and -1 in JavaScript. If a negative can "
                "reach it, write ((x % n) + n) % n",
            )
        ]
    return []


def _bare_sort(spec: dict[str, Any]) -> list[Finding]:
    """``.sort()`` with no comparator — a divergence only over numbers.

    JavaScript's bare sort orders by string, so ``[2, 10]`` becomes
    ``[10, 2]`` while python's ``sorted`` keeps ``[2, 10]``. Over strings the
    two agree, and sorting keys is the commonest correct use in this tree, so
    the finding is raised only where the receiver is visibly numeric.
    """
    source = spec.get("ref_ts") or ""
    found: list[Finding] = []
    for match in _BARE_SORT.finditer(source):
        receiver = _receiver(source, match.start())
        if "Object.keys(" in receiver or ".keys(" in receiver:
            continue
        name = re.split(r"[.(\[]", receiver)[0]
        # No name to look up means no evidence either way, and an unnamed
        # receiver must never be reported as visibly numeric — an empty
        # pattern matches every type annotation in the file.
        numeric = bool(name) and re.search(
            rf"\b{re.escape(name)}\s*:\s*number\s*\[\]", source
        )
        stringly = bool(name) and re.search(
            rf"\b{re.escape(name)}\s*:\s*string\s*\[\]", source
        )
        if stringly and not numeric:
            continue
        found.append(
            Finding(
                "divergence",
                bool(numeric),
                f"ref_ts sorts {receiver} with no comparator: JavaScript orders "
                "by string, so [2, 10] sorts to [10, 2] while python's sorted() "
                "keeps it. Pass a comparator",
            )
        )
    return found


def divergences(spec: dict[str, Any]) -> list[Finding]:
    """Constructs whose two languages do not answer a boundary the same way."""
    found: list[Finding] = []
    for arm, pattern, fatal, why in DIVERGENCES:
        for key in (f"ref_{arm}", f"acc_{arm}"):
            if re.search(pattern, spec.get(key) or ""):
                found.append(
                    Finding("divergence", fatal, f"{key} matches /{pattern}/: {why}")
                )
                break
    return found + _remainder(spec) + _bare_sort(spec)


# --- screen two: a problem already asked in another costume ----------------

REFUSE_AT = 0.70
WARN_AT = 0.55

_PY_KEEP = frozenset(
    {
        "if",
        "else",
        "elif",
        "for",
        "while",
        "return",
        "in",
        "not",
        "and",
        "or",
        "def",
        "break",
        "continue",
        "is",
        "lambda",
        "raise",
        "try",
        "except",
        "len",
        "range",
        "sorted",
        "sum",
        "min",
        "max",
        "abs",
        "set",
        "dict",
        "list",
        "str",
        "int",
        "enumerate",
        "zip",
        "reversed",
        "append",
        "join",
        "split",
        "strip",
        "lower",
        "upper",
        "keys",
        "items",
        "values",
        "add",
    }
)
_TS_KEEP = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "return",
        "of",
        "in",
        "const",
        "let",
        "function",
        "export",
        "break",
        "continue",
        "throw",
        "new",
        "typeof",
        "length",
        "push",
        "Math",
        "floor",
        "ceil",
        "round",
        "min",
        "max",
        "abs",
        "Set",
        "Map",
        "Object",
        "keys",
        "has",
        "add",
        "includes",
        "indexOf",
        "slice",
        "split",
        "join",
        "filter",
        "map",
        "sort",
        "toLowerCase",
        "toUpperCase",
        "startsWith",
        "endsWith",
        "String",
        "Number",
    }
)
_TS_TOKEN = re.compile(
    r"[A-Za-z_$][A-Za-z0-9_$]*|\d+|\"[^\"]*\"|'[^']*'|[^\sA-Za-z0-9_$]"
)


def _py_tokens(source: str) -> list[str]:
    out: list[str] = []
    skip = {
        _token.COMMENT,
        _token.NL,
        _token.NEWLINE,
        _token.INDENT,
        _token.DEDENT,
        _token.ENDMARKER,
    }
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in skip:
                continue
            if tok.type == _token.STRING:
                out.append("S")
            elif tok.type == _token.NUMBER:
                out.append("N")
            elif tok.type == _token.NAME:
                out.append(tok.string if tok.string in _PY_KEEP else "v")
            else:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return []
    return out


def _ts_tokens(source: str) -> list[str]:
    source = re.sub(r"//.*|/\*.*?\*/", " ", source, flags=re.S)
    out: list[str] = []
    for raw in _TS_TOKEN.findall(source):
        if raw[0] in "\"'":
            out.append("S")
        elif raw[0].isdigit():
            out.append("N")
        elif raw[0].isalpha() or raw[0] in "_$":
            out.append(raw if raw in _TS_KEEP else "v")
        else:
            out.append(raw)
    return out


def skeleton(source: str, arm: str) -> frozenset[tuple[str, ...]]:
    """A reference's shape: identifiers and literals erased, as 3-grams.

    Trigrams rather than a whole-file digest because a sibling is rarely a
    copy — it is the same control flow with a statement moved.
    """
    tokens = _py_tokens(source) if arm == "py" else _ts_tokens(source)
    if len(tokens) < 3:
        return frozenset()
    return frozenset(tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2))


def _overlap(a: frozenset[Any], b: frozenset[Any]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


_CACHE: dict[tuple[str, int], frozenset[tuple[str, ...]]] = {}


def corpus(roots: tuple[Path, ...] = (TASKS, RESERVE)) -> dict[str, dict[str, Any]]:
    """Every problem already in the tree, as ``{id: {arm: skeleton}}``."""
    out: dict[str, dict[str, Any]] = {}
    for root in roots:
        for arm, reference, _solution, _checker, _command in ARMS:
            for directory in sorted((root / arm).glob("b*")):
                path = directory / reference
                if not path.is_file():
                    continue
                key = (str(path), path.stat().st_mtime_ns)
                if key not in _CACHE:
                    _CACHE[key] = skeleton(path.read_text(encoding="utf-8"), arm)
                out.setdefault(directory.name, {})[arm] = _CACHE[key]
    return out


def siblings(
    spec: dict[str, Any], known: dict[str, dict[str, Any]] | None = None
) -> list[tuple[float, str, str]]:
    """Existing problems whose reference has this one's shape, nearest first."""
    known = corpus() if known is None else known
    scored: list[tuple[float, str, str]] = []
    for arm in ("ts", "py"):
        mine = skeleton(spec.get(f"ref_{arm}") or "", arm)
        for name, arms in known.items():
            if name == spec.get("id") or arm not in arms:
                continue
            scored.append((_overlap(mine, arms[arm]), name, arm))
    scored.sort(reverse=True)
    return scored


def check(
    spec: dict[str, Any], known: dict[str, dict[str, Any]] | None = None
) -> list[Finding]:
    """Both screens. Fatal findings mean the spec must be rewritten, not waived."""
    found = divergences(spec)
    for score, name, arm in siblings(spec, known)[:1]:
        if score >= WARN_AT:
            found.append(
                Finding(
                    "sibling",
                    score >= REFUSE_AT,
                    f"the {arm} reference is {score:.2f} of {name}'s shape — "
                    "read that problem before keeping this one; a different "
                    "domain is not a different problem",
                )
            )
    return found


def emit(spec: dict[str, Any], root: Path | None = None) -> list[Path]:
    """Write both arms plus the ts arm's sidecar; return what was written.

    Runs :func:`check` first and refuses on a fatal finding. Warnings go to
    stderr and are the author's to answer.
    """
    for finding in check(spec):
        line = f"{spec.get('id')}: {finding.screen}: {finding.detail}"
        if finding.fatal:
            raise EmitError(line)
        print(f"warning: {line}", file=sys.stderr)

    into = TASKS if root is None else root
    written: list[Path] = []
    for arm, reference, solution, checker, command in ARMS:
        directory = into / arm / spec["id"]
        directory.mkdir(parents=True, exist_ok=True)
        for name, text in (
            (reference, spec[f"ref_{arm}"]),
            (checker, spec[f"acc_{arm}"]),
            ("contract.yaml", contract(spec, arm, solution, command)),
        ):
            (directory / name).write_text(text, encoding="utf-8")
            written.append(directory / name)

    meta: dict[str, Any] = {
        "file_shape": spec["file_shape"],
        "shape": spec["shape"],
        "steering_band": spec["steering_band"],
    }
    if spec["file_shape"] == "multi_symbol":
        meta["target_symbol"] = spec["target_symbol"]
    sidecar = into / "ts" / spec["id"] / "meta.json"
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    written.append(sidecar)
    return written


def _spec_from_tree(name: str) -> dict[str, Any] | None:
    """Rebuild just enough of a written problem's spec to re-screen it."""
    spec: dict[str, Any] = {"id": name}
    for root in (TASKS, RESERVE):
        for arm, reference, _solution, checker, _command in ARMS:
            directory = root / arm / name
            if (directory / reference).is_file():
                spec[f"ref_{arm}"] = (directory / reference).read_text("utf-8")
                spec[f"acc_{arm}"] = (directory / checker).read_text("utf-8")
    return spec if "ref_ts" in spec or "ref_py" in spec else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="run both screens over every problem in the tree",
    )
    parser.add_argument(
        "--near", metavar="ID", help="the problems nearest one id in shape"
    )
    args = parser.parse_args(argv)

    known = corpus()
    if args.near:
        spec = _spec_from_tree(args.near)
        if spec is None:
            print(f"no such problem: {args.near}", file=sys.stderr)
            return 2
        for score, name, arm in siblings(spec, known)[:10]:
            print(f"{score:.3f}  {arm}  {name}")
        return 0

    if not args.audit:
        parser.print_help()
        return 0

    worst = 0
    for name in sorted(known):
        spec = _spec_from_tree(name)
        if spec is None:
            continue
        for finding in check(spec, known):
            mark = "REFUSE" if finding.fatal else "warn  "
            print(f"{mark}  {name}  {finding.screen}: {finding.detail}")
            worst = max(worst, 2 if finding.fatal else 1)
    return 0 if worst == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
