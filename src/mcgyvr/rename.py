"""The in-process floor: rename a symbol across every file that references it.

The one deterministic operation that is not a program on PATH. Every other
member of the floor hands a file to ``ruff`` or ``prettier`` and reads an exit
code; ``rename_symbol`` fans across files, which no formatter does, and the
thing that already knows where a name occurs is mcgyvr's own index together
with the parsers it is built on. That is the whole of the catalog's warrant for
calling this operation deterministic: what is a reference is decided by a
parser, so this fans across files without a model.

**What is renamed.** One module-level definition — a Python ``def``/``class``
at module scope, a JS/TS top-level ``function``/``class`` or ``const f = () =>``
— and every token that is a binding of or reference to *it*, rewritten at its
exact span (line and byte column) and nowhere else. The index supplies the
candidates: the files it holds, and where it saw the definition. Which tokens
are references is decided by :mod:`mcgyvr.orchestrator.references`, a
scope-aware walk of every file that mentions the name: imports of it, uses that
resolve to the module binding rather than a local of the same name, ``w.name``
where ``w`` is the defining module, ``global name``, ``__all__`` entries, JS
re-exports. Calls are not special: ``f = name``, ``map(name, xs)`` and
``@name`` are references too. A whole-word substitution over the lines the
index named — what this did until e2e run 2 — renamed ``json.load(f)`` along
with the module's own ``load``, and missed every use that was not a call.

**What is refused, before anything is written.** A name defined only as a
method or a nested function: which ``x.name`` reaches a method needs ``x``'s
type, and nothing here has it. A name defined at module level in several files
when the contract's ``target`` does not single one out. A definition the parser
cannot find on the line the index named it — the index and the file disagree,
and neither can be trusted to say what to rewrite. A scope that binds the name
both to this symbol and to something else; a new name already bound where the
rename would put it, or one that would capture a rewritten reference; a JS
shorthand ``{ name }``, where renaming the variable would change a key. Refusing
up front matters more here than in a single-file type: a rename that
half-applied across eight files and then stopped would leave a tree that
neither parses nor reverts to anything.

**Scope is the gate's question, not this one.** The rename fans wherever the
references are, and a contract whose ``scope.allow`` does not cover those files
is refused, with the paths named, before anything is written to the user's
tree. That is the visible failure; narrowing the rewrite to the allowed paths
would instead leave a tree that half-renamed and still passed.

**What is reported.** Each rewritten file with the lines it changed; every
same-named occurrence judged to be another symbol — ``json.load``,
``self.load``, ``from json import load``, a local that shadows the name — as
left alone, so a reader can check the judgement rather than trust it; and what
could not be judged at all — an index entry in a file it does not hold, a span
whose bytes are not the name, a candidate file that does not parse, a string
that names the symbol — as unresolved. The catalog's guarantee is that
"references the index could not resolve are reported, not silently left
behind", and each of those is one.
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

#: What ``to`` has to look like. The floor rewrites text, so a replacement that
#: is not an identifier produces a tree that no longer parses while reporting
#: that it worked.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: A file that re-exports a whole module need not mention the name, and is
#: still a module through which the name is reachable: a candidate too.
_STAR = {
    "python": re.compile(r"\bimport\s+\*"),
    "js/ts": re.compile(r"\bexport\s*\*"),
}


class RenameError(Exception):
    """The rename could not be carried out, and nothing was written."""


@dataclass(frozen=True)
class RenameReport:
    """What the rename touched, in the currency the floor reports in.

    ``locations`` pairs each rewritten file with the lines rewritten in it.
    ``left_alone`` holds the same-named occurrences judged to be another symbol,
    as ``path:line text``. ``unresolved`` holds what could not be judged and was
    left as it was.
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
    """Rename ``old`` to ``new`` throughout ``workspace``; return what moved.

    Writes only inside ``workspace``, which under the floor is always a sandbox
    — the same boundary every other writer in the project runs behind, and the
    reason a contract's own words can never reach the user's checkout.

    ``target`` is the contract's: a path or a glob, matched by
    :mod:`mcgyvr.scope`'s one matcher, that picks the defining module when the
    name is defined at module level in more than one file. It narrows nothing
    else — the references are wherever they are.

    Raises :class:`RenameError` before writing anything for every refusal the
    module docstring lists.
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

    # The candidates: every held file in the defining module's language that
    # could mention the name or re-export a module that does. The bytes are the
    # ones the index read, rebuilt exactly — its lines are a split on "\n" of
    # the surrogate-escaped text — so the judgement and the splice are made
    # over the same bytes, and nothing is read through a path twice.
    language = language_of(defining) or ""
    word = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
    star = _STAR[language]
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

    # Every file's new bytes are planned before any is written, so a file that
    # cannot be rewritten leaves the tree as it was rather than half-renamed.
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

    # Every path is checked before any is written, so a refusal leaves the tree
    # as it was: a tracked symlink would steer the rewrite off the tree.
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


def _defining_module(
    index: Index, held: dict[str, IndexedFile], old: str, target: str
) -> str:
    """The one file whose module-level definition of ``old`` is being renamed.

    Each definition the index names is confirmed by the precise parser on the
    very line the index named. A definition the parser does not find there is
    not taken on the index's word: the two disagree about the file, and a rename
    that trusted either would rewrite a line nobody can point at.
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
    """``source`` with ``old`` replaced by ``new`` at each occurrence's span.

    Cut where the parser cuts lines, so a line number means what it meant to the
    parser; spliced in bytes, because a column is a byte offset and a line with
    ``café`` before the name is a byte longer than it is characters. Within a
    line the spans are replaced right to left, so a splice never moves the
    column of one still to come. A span whose bytes are not the old name is
    missed — left as it was and reported — rather than guessed at: it is what
    keeps a disagreement between the parser and the file from becoming an edit.
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
