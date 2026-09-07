"""The in-process floor: rename a symbol across every file that references it.

The one deterministic task type that is not a program on PATH. Every other
member of the floor hands a file to ``ruff`` or ``prettier`` and reads an exit
code; ``rename_symbol`` fans across files, which no formatter does, and the
thing that already knows where a name occurs is mcgyvr's own index (#47). That
is the whole of the catalog's warrant for calling this type deterministic —
"the index already resolved the references, so this fans across files without a
model" — and until now nothing implemented it, so a contract of this type
validated and then reached ``error``.

**What is rewritten, and what is not.** The index reports each occurrence as a
path and a 1-based line. Only those lines are touched, and within them only
whole-word matches of the old name, so ``fetch_pages`` and ``prefetch_page``
survive a rename of ``fetch_page`` and a comment on an unindexed line is not
quietly edited. That is narrower than a project-wide textual substitution on
purpose: the guarantee is about references the index *resolved*, and a rewrite
that went beyond them would be making a claim the index never made.

**Scope is the gate's question, not this one.** The rename fans wherever the
index found the name, and a contract whose ``scope.allow`` does not cover those
files is rejected by the gate's scope rung with the paths named. That is the
visible failure; narrowing the rewrite to the allowed paths would instead leave
a tree that half-renamed and still passed.

**What is reported.** Occurrences the index could not attribute to a file it
holds — a skipped file, a binary, a language with no extractor — are counted
and named rather than silently dropped, because the catalog's guarantee is
explicit that "references the index could not resolve are reported, not
silently left behind". A rename that renamed nothing is a failure and says so:
a symbol the index does not know is far more likely to be a typo in the
contract than a symbol with no occurrences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.orchestrator.index import build_index

#: What ``to`` has to look like. The floor rewrites text, so a replacement that
#: is not an identifier produces a tree that no longer parses while reporting
#: that it worked.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RenameError(Exception):
    """The rename could not be carried out, and nothing was written."""


@dataclass(frozen=True)
class RenameReport:
    """What the rename touched, in the currency the floor reports in."""

    old: str
    new: str
    files: tuple[str, ...] = ()
    occurrences: int = 0
    unresolved: tuple[str, ...] = field(default=())

    def summary(self) -> str:
        lines = [
            f"renamed {self.old} -> {self.new}: "
            f"{self.occurrences} occurrence(s) in {len(self.files)} file(s)"
        ]
        lines.extend(f"  {path}" for path in self.files)
        if self.unresolved:
            lines.append(
                f"{len(self.unresolved)} reference(s) the index could not "
                "resolve, left as they were:"
            )
            lines.extend(f"  {where}" for where in self.unresolved)
        return "\n".join(lines)


def apply(workspace: Path, old: str, new: str) -> RenameReport:
    """Rename ``old`` to ``new`` throughout ``workspace``; return what moved.

    Writes only inside ``workspace``, which under the floor is always a sandbox
    — the same boundary every other writer in the project runs behind, and the
    reason a contract's own words can never reach the user's checkout.

    Raises :class:`RenameError` before writing anything when the pair is not
    usable or the symbol is not one the index knows. Refusing up front matters
    more here than in a single-file type: a rename that half-applied across
    eight files and then stopped would leave a tree that neither parses nor
    reverts to anything.
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
    # Every kind, not definitions and references alone. An import of the old
    # name is an occurrence of it, and a rename that renamed the definition and
    # left `from pkg.messy import fetch_page` behind produces a tree that does
    # not import — which is worse than the tree it started from and would be
    # reported as a success. An alias survives untouched either way: the
    # substitution is whole-word on the old name, and `as fp` is not it.
    occurrences = [symbol for symbol in index.symbols.all() if symbol.name == old]
    if not occurrences:
        raise RenameError(
            f"the index holds no definition or reference of {old!r} in this "
            f"tree. A symbol with no occurrences at all is a name that is "
            f"spelled wrong in the contract far more often than it is a "
            f"symbol nothing uses."
        )

    held = {file.path for file in index.files}
    unresolved = tuple(
        f"{symbol.path}:{symbol.line}"
        for symbol in occurrences
        if symbol.path not in held
    )
    word = re.compile(rf"\b{re.escape(old)}\b")

    by_file: dict[str, set[int]] = {}
    for symbol in occurrences:
        if symbol.path in held:
            by_file.setdefault(symbol.path, set()).add(symbol.line)

    changed: list[str] = []
    count = 0
    for path in sorted(by_file):
        target = workspace / path
        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        touched = 0
        for number in sorted(by_file[path]):
            if not 1 <= number <= len(lines):
                # The index and the file on disk disagree about how long the
                # file is. Nothing is rewritten on a line nobody can point at.
                continue
            rewritten, hits = word.subn(new, lines[number - 1])
            lines[number - 1] = rewritten
            touched += hits
        if touched:
            target.write_text("".join(lines), encoding="utf-8")
            changed.append(path)
            count += touched

    return RenameReport(
        old=old,
        new=new,
        files=tuple(changed),
        occurrences=count,
        unresolved=unresolved,
    )
