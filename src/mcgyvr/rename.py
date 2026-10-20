"""The in-process executor for `rename_symbol`: rewrite one symbol's references.

`apply` builds the tree's index, decides which file holds the symbol's module-level
definition, asks `mcgyvr.orchestrator.references` for a verdict on every spelling of
the old name, splices the ones judged to be that symbol by byte column, and writes
the result. It fails closed: a pair that is not usable, occurrences that cannot be
told apart, a collision with the new name, a path outside the tree, or a rename that
would rewrite nothing each raise `RenameError` before any file is written.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.lines import parser_lines
from mcgyvr.orchestrator.index import Index, IndexedFile, build_index
from mcgyvr.orchestrator.references import (
    Definition,
    Occurrence,
    UnsafeRenameError,
    Verdict,
    definitions,
    resolve,
)
from mcgyvr.orchestrator.symbols import language_of
from mcgyvr.scope import OutsideTreeError, Scope, inside

#: The only shape a rename may write: a plain ASCII identifier. The rewrite is a byte
#: splice rather than a re-parse, so anything else — an expression, a dotted path, a
#: space — would leave text that does not parse while the exit code claims success.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: A star import (Python) or star export (JS/TS) can bring the old name into a file
#: without ever spelling it, so a file holding one is still judged as a reference site.
#: Its keys are also the languages a rename is resolved in: the index extracts symbols
#: from more languages than `mcgyvr.orchestrator.references` can bind, and a symbol
#: defined in any other is refused rather than rewritten by spelling.
_STAR = {
    "python": re.compile(r"\bimport\s+\*"),
    "js/ts": re.compile(r"\bexport\s*\*"),
}


class RenameError(Exception):
    """The rename was refused, so no file was written."""


@dataclass(frozen=True)
class RenameReport:
    """What one rename did: the pair, the files and lines rewritten, and the leftovers.

    `occurrences` counts the spans actually replaced, spread over `files`; `locations`
    gives the rewritten line numbers per file. `unresolved` and `left_alone` hold
    `path:line` renderings of what was deliberately not touched — spellings the
    resolver could not place, or same-named occurrences of another symbol — and
    `summary` renders all of it for the caller's stdout.
    """

    old: str
    new: str
    files: tuple[str, ...] = ()
    occurrences: int = 0
    unresolved: tuple[str, ...] = field(default=())
    locations: tuple[tuple[str, tuple[int, ...]], ...] = field(default=())
    left_alone: tuple[str, ...] = field(default=())

    def summary(self) -> str:
        lines = [
            f"renamed {self.old} -> {self.new}: "
            f"{self.occurrences} occurrence(s) in {len(self.files)} file(s)"
        ]
        lines.extend(
            f"  {path}: line(s) {', '.join(map(str, numbers))}"
            for path, numbers in self.locations
        )
        if self.unresolved:
            lines.append(
                f"{len(self.unresolved)} possible reference(s) that could not "
                "be resolved, left as they were:"
            )
            lines.extend(f"  {where}" for where in self.unresolved)
        if self.left_alone:
            lines.append(
                f"{len(self.left_alone)} same-named occurrence(s) of another "
                "symbol, left alone:"
            )
            lines.extend(f"  {where}" for where in self.left_alone)
        return "\n".join(lines)


def apply(workspace: Path, old: str, new: str, *, target: str = "") -> RenameReport:
    """Rename `old` to `new` across `workspace` and report every rewritten span.

    The pair is rejected before anything is read when either name is empty, when
    `new` is not an identifier, or when the two are equal. `target` is the contract
    path, used only to pick one of several module-level definitions of the name. The
    tree is indexed, the defining module is settled by `_defining_module`, and one
    candidate text per same-language file is handed to `resolve`, whose verdict splits
    the occurrences into rewrites and left-alones. Rewrites are spliced in memory and
    every resulting path is checked with `inside` before the first write, so a refusal
    leaves the tree exactly as it was.
    """
    if not old or not new:
        raise RenameError(
            "rename_symbol needs `rename.from` and `rename.to`. The floor "
            "renames every reference the index resolved across every file "
            "that holds one, and neither name is derivable from `target`: a "
            "pair read out of the `task` prose would be a multi-file rewrite "
            "resting on a guess about English."
        )
    if not _IDENTIFIER.match(new):
        raise RenameError(
            f"rename.to {new!r} is not an identifier. The floor rewrites text, "
            f"so a replacement that is not a name leaves a tree that no longer "
            f"parses and an exit code that says it worked."
        )
    if old == new:
        raise RenameError(
            f"rename.from and rename.to are both {old!r}; a rename that "
            "renames nothing is a contract nobody meant to write."
        )

    index = build_index(workspace)
    held = {file.path: file for file in index.files}
    defining = _defining_module(index, held, old, target)

    # Only files written in the defining module's language are candidates, and of those
    # only ones that could hold a reference: the defining file itself, a file that
    # spells the name as a whole word, or one with a star import/export. Each candidate
    # is handed over as its indexed lines rejoined with "\n", which is the same text
    # `_splice` will later cut into.
    language = language_of(defining) or ""
    word = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
    star = _STAR.get(language)
    if star is None:  # defensive: _defining_module already refused this
        raise _unsupported_language(old, [defining])
    sources: dict[str, bytes] = {}
    for path, file in held.items():
        if language_of(path) != language:
            continue
        text = "\n".join(file.lines)
        if path == defining or word.search(text) or star.search(text):
            sources[path] = text.encode("utf-8", "surrogateescape")

    try:
        resolution = resolve(sources, held, defining, old, new)
    except UnsafeRenameError as refusal:
        raise RenameError(f"the rename is refused: {refusal}") from refusal

    renamed: dict[str, list[Occurrence]] = defaultdict(list)
    others: set[tuple[str, int, str]] = set()
    for occurrence in resolution.occurrences:
        if occurrence.verdict is Verdict.RENAME:
            renamed[occurrence.path].append(occurrence)
        else:
            others.add((occurrence.path, occurrence.line, occurrence.text))

    # Splice in memory: the new bytes, the line numbers touched and any span the
    # parser placed where the old name is not are all settled before the disk is
    # touched, so nothing is half-renamed.
    planned: dict[str, bytes] = {}
    locations: list[tuple[str, tuple[int, ...]]] = []
    missed: list[str] = []
    count = 0
    for path in sorted(renamed):
        spliced = _splice(sources[path], renamed[path], old, new)
        missed.extend(
            f"{path}:{line} (not {old!r} where the parser placed it)"
            for line in spliced.missed
        )
        if spliced.count:
            planned[path] = spliced.data
            locations.append((path, spliced.lines))
            count += spliced.count

    if not count:
        raise RenameError(
            f"the parser found no reference to {old!r} it could rewrite where it "
            f"pointed ({len(missed)} span(s) held something else); nothing was "
            f"renamed, and a rename that renamed nothing is not a success."
        )

    # Containment is checked for every planned path before any of them is written, so
    # a path that climbs out of the workspace, crosses a symlink or touches `.git`
    # refuses the whole rename instead of a part of it.
    targets: dict[str, Path] = {}
    for path in planned:
        try:
            targets[path] = inside(workspace, path)
        except OutsideTreeError as refusal:
            raise RenameError(f"the rename is refused: {refusal}") from refusal
    for path, data in planned.items():
        targets[path].write_bytes(data)

    unheld = tuple(
        f"{symbol.path}:{symbol.line}"
        for symbol in index.symbols.all()
        if symbol.name == old and symbol.path not in held
    )
    return RenameReport(
        old=old,
        new=new,
        files=tuple(planned),
        occurrences=count,
        unresolved=(*unheld, *resolution.unresolved, *missed),
        locations=tuple(locations),
        left_alone=tuple(
            f"{path}:{line} {text}" for path, line, text in sorted(others)
        ),
    )


def _unsupported_language(old: str, paths: list[str]) -> RenameError:
    """The refusal for a symbol defined only in languages no rename is resolved in."""
    languages = ", ".join(sorted({language_of(path) or "unparsed" for path in paths}))
    where = ", ".join(sorted(set(paths)))
    return RenameError(
        f"{old!r} is defined only in {languages} source ({where}). A rename is "
        f"resolved in Python and JS/TS only: in any other language the index finds "
        f"the definition but nothing binds its references, so they cannot be told "
        f"from a same-named other symbol; nothing was renamed."
    )


def _defining_module(
    index: Index, held: dict[str, IndexedFile], old: str, target: str
) -> str:
    """Return the path of the module-level file the rename of `old` starts from.

    The index's definitions of `old` are confirmed against the parser, because only a
    module-level definition fixes which same-named occurrences are this symbol. A name
    with no definition, one defined only in a language other than Python or JS/TS, a
    definition the parser cannot find on the line the index named, and a name defined
    only as a method or nested function are refused. When several
    module-level files define it, each is a different symbol: `target` is treated as a
    scope pattern and must permit exactly one of them, otherwise the rename is refused
    rather than guessed.
    """
    named = index.symbols.definitions(old)
    if not named:
        raise RenameError(
            f"the index holds no definition of {old!r} in this tree. A rename "
            f"starts from the definition — it is what decides which same-named "
            f"occurrences are this symbol — and a name with no definition at "
            f"all is spelled wrong in the contract far more often than it is "
            f"defined outside the tree."
        )

    resolvable = tuple(s for s in named if language_of(s.path) in _STAR)
    if not resolvable:
        raise _unsupported_language(old, [symbol.path for symbol in named])
    named = resolvable

    parsed: dict[str, tuple[Definition, ...] | None] = {}
    confirmed: list[Definition] = []
    for symbol in named:
        file = held.get(symbol.path)
        if file is None:
            continue
        if symbol.path not in parsed:
            source = "\n".join(file.lines).encode("utf-8", "surrogateescape")
            parsed[symbol.path] = definitions(symbol.path, source, old)
        confirmed.extend(
            definition
            for definition in parsed[symbol.path] or ()
            if definition.line == symbol.line
        )

    module_level = sorted({d.path for d in confirmed if d.module_level})
    if not module_level:
        if confirmed:
            where = ", ".join(sorted({f"{d.path}:{d.line}" for d in confirmed}))
            raise RenameError(
                f"{old!r} is defined only as a method or a nested function "
                f"({where}). Which `x.{old}` reaches a method needs the type of "
                f"`x`, which the index does not have, so its references cannot "
                f"be told from a same-named attribute of something else; "
                f"nothing was renamed."
            )
        raise RenameError(
            f"the index named {len(named)} definition(s) of {old!r} and the "
            f"parser found none on the line the index named. The two disagree "
            f"about the file, so neither says what to rewrite; nothing was "
            f"renamed, and a rename that renamed nothing is not a success."
        )
    if len(module_level) == 1:
        return module_level[0]

    chosen = [
        path for path in module_level if target and Scope.of([target]).permits(path)
    ]
    if len(chosen) == 1:
        return chosen[0]
    matched = (
        f"{target!r} matches {len(chosen)} of them."
        if target
        else "the contract names none."
    )
    raise RenameError(
        f"{old!r} is defined at module level in {len(module_level)} files "
        f"({', '.join(module_level)}), and each is a different symbol. The "
        f"contract's `target` must name the one meant; {matched} Nothing was "
        f"renamed."
    )


@dataclass(frozen=True)
class _Spliced:
    data: bytes
    count: int
    lines: tuple[int, ...]
    missed: tuple[int, ...]


def _splice(
    source: bytes, occurrences: list[Occurrence], old: str, new: str
) -> _Spliced:
    """Replace `old` with `new` at each occurrence's byte column in `source`.

    Occurrence columns are byte offsets into their line, so the substitutions on one
    line are applied right to left and the earlier columns stay valid. Each line is
    kept exactly as it was, terminators included, and reassembled without re-splitting,
    so bytes the parser never looked at survive the rewrite. A line outside the file,
    or a column where the bytes are not exactly `old`, is not touched and is reported
    in `missed`; `count` and `lines` cover only the replacements actually made.
    """
    lines = parser_lines(source.decode("utf-8", "surrogateescape"))
    before, after = old.encode("utf-8"), new.encode("utf-8")
    by_line: dict[int, set[int]] = defaultdict(set)
    for occurrence in occurrences:
        by_line[occurrence.line].add(occurrence.column)
    count = 0
    rewritten: set[int] = set()
    missed: set[int] = set()
    for number, columns in by_line.items():
        if not 1 <= number <= len(lines):
            missed.add(number)
            continue
        raw = lines[number - 1].encode("utf-8", "surrogateescape")
        for column in sorted(columns, reverse=True):
            if column < 0 or raw[column : column + len(before)] != before:
                missed.add(number)
                continue
            raw = raw[:column] + after + raw[column + len(before) :]
            rewritten.add(number)
            count += 1
        lines[number - 1] = raw.decode("utf-8", "surrogateescape")
    return _Spliced(
        data="".join(lines).encode("utf-8", "surrogateescape"),
        count=count,
        lines=tuple(sorted(rewritten)),
        missed=tuple(sorted(missed)),
    )
