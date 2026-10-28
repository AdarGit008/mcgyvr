"""Splitting a typed proposal until it is on one file and jev says it cannot be split.

Classifier authoring proposes once for a request (`delegate.ClassifierProposer`);
`RefiningProposer` then breaks that proposal down again and again, until every
proposal it hands on holds two things: it is on one file, and jev answered that
it cannot be split further.

* A proposal whose `allow` scope names more files than its target is split into
  one proposal per file, without asking: each file's proposal is asked of the
  classifier again with that file as its target and only scope, shown the
  sentences of the request about that file — those that name it or one of its
  definitions, and those that name no file at all. A file no sentence is about
  is not guessed at: the request is declined.
* A proposal on one file is put to jev as one typed yes/no question, `split`:
  can it be split into smaller changes to that file that can each land on their
  own? No makes it a leaf. Yes is followed by one typed Choice, `partition`,
  among the partitions `survey` built and a last option saying none of them
  fits; the parts of the one jev picks are proposed and each is asked again.

`survey` reads its partitions from the proposal's own words and the repository,
never inventing one: the sentences of the words, the definitions of the target
the words name, and those of the failing tests the baseline run attaches to the
proposal as its demonstrations that name its target. A part's task is its own
sentence, or the words with one sentence saying which definition or which
failing test is the part's own. Words with a fragment in them — a heading, a
bare list number, a single word — are not split by sentence at all.

The leaves come back in the order they were reached. A leaf that spells a name
another leaf creates — one its interface declares and the repository does not
define yet, or the new name of a rename its task states — waits on it through
`depends_on`, so the dependency tree (`mcgyvr.tree`) orders them; two leaves on
one file with no such edge are kept apart by their scopes (`Scope.meets`). An
edge that would close a cycle is not inferred: the two are kept apart by their
scopes alone, rather than refused for a cycle nobody stated.

Every split is bounded: one past `max_depth` splits below the request, or into
more than `max_fanout` parts, is a `Refusal` saying which bound to raise, never
a silent stop, and is returned after every proposal so `depends_on` indexes
count proposals only. Where jev declines — an answer it cannot give, a Yes the
survey has no partition for, or none of the partitions picked — nothing is
guessed: the whole request comes back empty, and the prose proposer stands in
for it as before. Every question goes through the classifier's `ask`, which
records the decision in the classifier's shadow sink, when one is wired, with
the model that answered; `mcgyvr delegate` wires none, as for the field
decisions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr.config import MAX_REFINE_DEPTH_DEFAULT, MAX_REFINE_FANOUT_DEFAULT
from mcgyvr.decision import Choice, Noul, Question
from mcgyvr.orchestrator.candidates import (
    CandidateSet,
    FieldCandidate,
    kind_for,
    symbols_of,
)
from mcgyvr.orchestrator.decompose import Evidence, Proposal, Refusal
from mcgyvr.orchestrator.iterate import Classifier, reproposals
from mcgyvr.orchestrator.provides import declared_names, identifiers, renames

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

#: The name the yes/no question is asked under, and the field it is recorded as.
SPLIT = "split"

#: The name the which-split question is asked under, and its recorded field.
PARTITION = "partition"

_SPLIT_INSTRUCTIONS = (
    "The task is one proposed change to {target}. Can it be split into two or "
    "more smaller changes to {target}, each one behaviour change that can land "
    "on its own? Answer No when it is one behaviour change that cannot be split "
    "further."
)

_PARTITION_INSTRUCTIONS = (
    "The task is to be split into separate changes to {target}, one contract "
    "each. Which split keeps each part one behaviour change that can land on "
    "its own?"
)

#: The yes/no question read back as one of two candidates; No is rank 0, the
#: answer a proposal stands on when nothing says it splits.
_SPLIT_SET = CandidateSet(
    field=SPLIT,
    candidates=(
        FieldCandidate(id=f"{SPLIT}:no", value=False, rank=0),
        FieldCandidate(id=f"{SPLIT}:yes", value=True, rank=1),
    ),
)

#: What a part split by definition or by failing test says is its own share.
_ONLY_SYMBOL = "This contract's part of that work is `{symbol}` only."
_ONLY_TEST = "This contract's part of that work is making `{test}` pass."

#: Where one sentence ends inside a line: a full stop, question or exclamation
#: mark, then space, then what starts a sentence. Lines end sentences too.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`'\"(])")

#: A list marker at the start of a line: a bullet, or a number or letter with a
#: full stop or bracket after it.
_ENUMERATOR = re.compile(r"^\s*(?:[-*\u2022]|\(?(?:\d+|[A-Za-z])[.)])\s+")

#: Abbreviations a sentence does not end at.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "cf.")

#: The fewest words a sentence of its own needs (a verb and its object); fewer
#: is a fragment.
_MIN_WORDS = 2

#: The option of the `partition` question that picks none of the splits.
_NONE_FITS = (
    "none of these: a part would not be one behaviour change that can land on its own"
)

#: A path as a request spells one, with whatever punctuation follows it.
_PATH_WORD = re.compile(r"[\w./-]+")


class Asker(Classifier, Protocol):
    """The typed classifier refine drives: it proposes, and it asks one question."""

    def ask(self, state: Any, set: CandidateSet, question: Question) -> Any | None: ...


@dataclass(frozen=True)
class Part:
    """One part of a split: the words it covers and the task its contract states.

    `subject` is what the part is named by in the question (its sentence, its
    definition or its failing test). `symbol` is the definition the part is
    held to, or None for jev to choose; `demonstration` the one failing test it
    demonstrates, when the split is by test.
    """

    subject: str
    words: str
    task: str
    symbol: str | None = None
    demonstration: tuple[str, ...] = ()


@dataclass(frozen=True)
class Partition:
    """One way the survey can split a proposal: by `sentence`, `symbol` or `test`."""

    kind: str
    parts: tuple[Part, ...]

    @property
    def text(self) -> str:
        """The option line jev reads for this split."""
        if self.kind == "sentence":
            return "one contract per sentence: " + " | ".join(
                p.subject for p in self.parts
            )
        if self.kind == "symbol":
            return "one contract per symbol: " + ", ".join(
                p.subject for p in self.parts
            )
        return "one contract per failing test: " + ", ".join(
            p.subject for p in self.parts
        )


def survey(
    evidence: Evidence, proposal: Proposal, words: str, *, scoped: bool = False
) -> tuple[Partition, ...]:
    """The splits the request and repository hold for `proposal`, none invented.

    `words` are the request's words the proposal covers. With failing tests
    attached as its demonstrations — the baseline's red tests, which an
    evidence-derived proposal is emitted with, or one it states — the only
    split offered is one contract per failing test that names the target (its
    module or one of its definitions), and only when two or more do and none
    was stated: any other split would hand every part every test, and no part
    could pass the others'. Otherwise: one contract per sentence of `words`,
    when there are two or more and none is a fragment; and one per definition of
    the target that `words` name, when there are two or more, `words` state no
    rename (which name would be whose is then not read), and the proposal is
    not already a part held to one definition (`scoped`).
    """
    demonstrations = _demonstrations(evidence, proposal)
    if demonstrations:
        if proposal.demonstration or len(demonstrations) < 2:
            return ()
        assert evidence.baseline is not None  # demonstrations came from it
        tested = tuple(
            (test, demonstration)
            for test, demonstration in zip(
                evidence.baseline.red, demonstrations, strict=True
            )
            if _tests_target(evidence, proposal.target, test)
        )
        if len(tested) < 2:
            return ()
        return (
            Partition(
                "test",
                tuple(
                    Part(
                        subject=test,
                        words=words,
                        task=f"{proposal.task} {_ONLY_TEST.format(test=test)}",
                        demonstration=(demonstration,),
                    )
                    for test, demonstration in tested
                ),
            ),
        )
    if scoped:
        return ()
    found: list[Partition] = []
    sentences = _sentences(words)
    if len(sentences) >= 2 and not any(_fragment(s) for s in sentences):
        found.append(
            Partition(
                "sentence",
                tuple(Part(subject=s, words=s, task=s) for s in sentences),
            )
        )
    named = _named(evidence, proposal.target, words)
    if len(named) >= 2 and not renames(words):
        found.append(
            Partition(
                "symbol",
                tuple(
                    Part(
                        subject=name,
                        words=words,
                        task=f"{words} {_ONLY_SYMBOL.format(symbol=name)}",
                        symbol=name,
                    )
                    for name in named
                ),
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class _Node:
    """A proposal being refined: its words, how many splits down, whether held."""

    proposal: Proposal
    words: str
    depth: int
    scoped: bool = False


@dataclass(frozen=True)
class RefiningProposer:
    """The classifier, refined until one file per proposal and jev says no further.

    `classifier` proposes and asks (`delegate.ClassifierProposer`); `max_depth`
    bounds how many splits below the request a proposal may be, `max_fanout`
    how many parts one split may have. As a `Proposer` it returns the leaves,
    then the refusals the bounds made, or nothing when jev declined.
    """

    classifier: Asker
    max_depth: int = MAX_REFINE_DEPTH_DEFAULT
    max_fanout: int = MAX_REFINE_FANOUT_DEFAULT

    def __call__(self, evidence: Evidence) -> Sequence[Proposal | Refusal]:
        """The `Proposer` seam: a decline is `()`, so the prose proposer stands in.

        Evidence carrying refused proposals is a re-proposal: the classifier
        asks each refused field again (`iterate.reproposals`), unrefined.
        """
        if evidence.refused:
            return reproposals(self.classifier, evidence)
        refined = self.refine(evidence)
        return () if refined is None else refined

    def refine(self, evidence: Evidence) -> tuple[Proposal | Refusal, ...] | None:
        """The leaves and the bounds' refusals for `evidence`, or None on a decline."""
        root = self.classifier.propose(evidence)
        if isinstance(root, Refusal):
            return None
        nodes = self._by_file(evidence, root)
        if nodes is None:
            return None
        if isinstance(nodes, Refusal):
            return (nodes,)
        leaves: list[Proposal] = []
        refusals: list[Refusal] = []
        for node in nodes:
            if not self._walk(evidence, node, leaves, refusals):
                return None
        return (*_linked(evidence, leaves), *refusals)

    def _by_file(
        self, evidence: Evidence, root: Proposal
    ) -> list[_Node] | Refusal | None:
        """One node per file the root's scope names, or the root alone on one file."""
        files = tuple(dict.fromkeys((root.target, *root.allow)))
        if len(files) == 1:
            return [_Node(root, root.task, 0)]
        if len(files) > self.max_fanout:
            return Refusal(
                root.target,
                f"the proposal's scope names {len(files)} files, and one contract "
                f"each would be more than `max_refine_fanout` allows "
                f"({self.max_fanout}), so it is not emitted over them all",
                field="allow",
                what_to_change=(
                    f"raise `max_refine_fanout` to {len(files)} or more, or narrow "
                    "the request to fewer files"
                ),
            )
        sentences = _sentences(root.task)
        nodes: list[_Node] = []
        for path in files:
            words = _about(evidence, sentences, path, files)
            if not words:
                return None
            child = self.classifier.propose(
                replace(evidence, prompt=words),
                decided={"task_type": root.task_type, "target": path, "allow": (path,)},
            )
            if isinstance(child, Refusal):
                return None
            nodes.append(_Node(child, child.task, 1))
        return nodes

    def _walk(
        self,
        evidence: Evidence,
        node: _Node,
        leaves: list[Proposal],
        refusals: list[Refusal],
    ) -> bool:
        """Refine `node` into `leaves` and `refusals`; False when jev declined."""
        partitions = survey(evidence, node.proposal, node.words, scoped=node.scoped)
        split = self.classifier.ask(
            _state(evidence, node),
            _SPLIT_SET,
            Noul(instructions=_SPLIT_INSTRUCTIONS.format(target=node.proposal.target)),
        )
        if split is None:
            return False
        if not split:
            leaves.append(node.proposal)
            return True
        if not partitions:
            return False
        if node.depth >= self.max_depth:
            refusals.append(_too_deep(node, self.max_depth))
            return True
        chosen = self._partition(evidence, node, partitions)
        if chosen is None:
            return False
        if len(chosen.parts) > self.max_fanout:
            refusals.append(_too_wide(node, chosen, self.max_fanout))
            return True
        children: list[_Node] = []
        for part in chosen.parts:
            child = self._child(evidence, node, part)
            if child is None:
                return False
            children.append(child)
        return all(self._walk(evidence, c, leaves, refusals) for c in children)

    def _partition(
        self, evidence: Evidence, node: _Node, partitions: tuple[Partition, ...]
    ) -> Partition | None:
        """Ask jev which of `partitions` splits `node`, or None when it declines.

        It is asked even with one partition, since a Yes to `split` says the
        proposal splits, not that it splits this way; the last option picks
        none of them, and is a decline.
        """
        candidates = CandidateSet(
            field=PARTITION,
            candidates=(
                *(
                    FieldCandidate(id=f"{PARTITION}:{p.kind}", value=p, rank=rank)
                    for rank, p in enumerate(partitions)
                ),
                FieldCandidate(
                    id=f"{PARTITION}:none", value=None, rank=len(partitions)
                ),
            ),
        )
        question = Choice(
            instructions=_PARTITION_INSTRUCTIONS.format(target=node.proposal.target),
            options={
                c.id: _NONE_FITS if c.value is None else c.value.text
                for c in candidates.candidates
            },
        )
        chosen = self.classifier.ask(_state(evidence, node), candidates, question)
        return chosen if isinstance(chosen, Partition) else None

    def _child(self, evidence: Evidence, node: _Node, part: Part) -> _Node | None:
        """The proposal for one part, asked again where the part leaves it open.

        A part split by failing test is the proposal itself with the part's task
        and its one test: what else jev chose stands. Any other is asked of the
        classifier with the type, target, scope and task decided, and the
        definition too when the part is held to one.
        """
        parent = node.proposal
        if part.demonstration:
            child = replace(parent, task=part.task, demonstration=part.demonstration)
            return _Node(child, part.words, node.depth + 1, scoped=True)
        decided: dict[str, Any] = {
            "task_type": parent.task_type,
            "target": parent.target,
            "task": part.task,
            "allow": parent.allow,
        }
        if part.symbol is not None:
            decided["symbol"] = part.symbol
        asked = self.classifier.propose(
            replace(evidence, prompt=part.words), decided=decided
        )
        if isinstance(asked, Refusal):
            return None
        return _Node(asked, part.words, node.depth + 1, scoped=part.symbol is not None)


def max_depth(config: Config) -> int:
    """`max_refine_depth` as the config states it, or its default when unset."""
    stated = config.get("max_refine_depth", MAX_REFINE_DEPTH_DEFAULT)
    return MAX_REFINE_DEPTH_DEFAULT if stated is None else int(stated)


def max_fanout(config: Config) -> int:
    """`max_refine_fanout` as the config states it, or its default when unset."""
    stated = config.get("max_refine_fanout", MAX_REFINE_FANOUT_DEFAULT)
    return MAX_REFINE_FANOUT_DEFAULT if stated is None else int(stated)


# Reading the request and the repository.


def _demonstrations(evidence: Evidence, proposal: Proposal) -> tuple[str, ...]:
    """The demonstrations `proposal` is emitted with: its own, else the baseline's.

    The same rule `decompose` fills them by: an evidence-derived type takes the
    baseline's red tests when it states none.
    """
    if proposal.demonstration:
        return proposal.demonstration
    kind = kind_for(proposal.task_type, evidence.vocabulary)
    if kind is None or not kind.evidence_derived or evidence.baseline is None:
        return ()
    return evidence.baseline.demonstrations()


def _sentences(text: str) -> tuple[str, ...]:
    """The sentences of `text`, in order, each once, list markers taken off.

    A line ends a sentence; inside a line one ends at `.`, `?` or `!` before
    what starts the next, never at an abbreviation such as `e.g.`.
    """
    found: list[str] = []
    for line in text.strip().splitlines():
        line = _ENUMERATOR.sub("", line).strip()
        joined: list[str] = []
        for piece in _SENTENCE_END.split(line):
            piece = piece.strip()
            if joined and joined[-1].lower().endswith(_ABBREVIATIONS):
                joined[-1] = f"{joined[-1]} {piece}"
            elif piece:
                joined.append(piece)
        found.extend(joined)
    return tuple(dict.fromkeys(found))


def _fragment(sentence: str) -> bool:
    """Whether `sentence` cannot stand as a part: a heading, or a single word."""
    return sentence.endswith(":") or len(sentence.split()) < _MIN_WORDS


def _tests_target(evidence: Evidence, target: str, test: str) -> bool:
    """Whether the test id `test` names `target`'s module or one of its definitions."""
    names = {PurePosixPath(target).stem} | {
        s.name for s in symbols_of(evidence, target)
    }
    return any(
        re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", test)
        for name in names
    )


def _named(evidence: Evidence, target: str, words: str) -> tuple[str, ...]:
    """The definitions of `target` that `words` name, in index order.

    The target's own path and file name are taken out first, so the parts of a
    path are not read as names.
    """
    text = words
    for spelled in (target, PurePosixPath(target).name):
        text = text.replace(spelled, " ")
    said = identifiers(text)
    return tuple(
        dict.fromkeys(s.name for s in symbols_of(evidence, target) if s.name in said)
    )


def _spells(text: str, path: str) -> bool:
    """Whether `text` names `path`, whole or by its file name."""
    words = {w.rstrip(".,;:!?)") for w in _PATH_WORD.findall(text)}
    return path in words or PurePosixPath(path).name in words


def _about(
    evidence: Evidence, sentences: Sequence[str], path: str, files: Sequence[str]
) -> str:
    """The sentences about `path`, or "" when none names it or what it defines.

    A sentence is about a file when it names the file or one of its
    definitions; one that names no file of `files` and none of their
    definitions is about every file. A file only such sentences are about is
    not one the request says anything of, so it gets none.
    """

    def names(sentence: str, file: str) -> bool:
        return _spells(sentence, file) or bool(_named(evidence, file, sentence))

    own = [s for s in sentences if names(s, path)]
    if not own:
        return ""
    shared = [s for s in sentences if not any(names(s, f) for f in files)]
    return " ".join(s for s in sentences if s in own or s in shared)


def _state(evidence: Evidence, node: _Node) -> Mapping[str, Any]:
    """What the split questions are about: the request and this proposal."""
    proposal = node.proposal
    return {
        "request": evidence.prompt,
        "target": proposal.target,
        "task": proposal.task,
        "symbols": list(_named(evidence, proposal.target, node.words)),
        "demonstrations": list(_demonstrations(evidence, proposal)),
    }


def _linked(evidence: Evidence, leaves: Sequence[Proposal]) -> tuple[Proposal, ...]:
    """The leaves, each waiting on the leaves that create a name it spells.

    A leaf creates the names its interface declares that its target does not
    define yet, and the new name of a rename its task states; it spells the
    names in its task and interface and the symbols it depends on in its own
    file. A name a leaf creates itself is not waited for, and an edge that
    would close a cycle is left out.
    """
    defined: dict[str, frozenset[str]] = {}
    for leaf in leaves:
        if leaf.target not in defined:
            defined[leaf.target] = frozenset(
                s.name for s in symbols_of(evidence, leaf.target)
            )
    creates = [
        (declared_names(leaf.target, leaf.interface) - defined[leaf.target])
        | {new for _, new in renames(leaf.task)}
        for leaf in leaves
    ]
    spells = [
        identifiers(leaf.task, leaf.interface)
        | {dep.symbol for dep in leaf.deps if dep.path == leaf.target}
        for leaf in leaves
    ]
    waits = [list(leaf.depends_on) for leaf in leaves]
    for at in range(len(leaves)):
        for other in range(len(leaves)):
            if (
                other != at
                and other not in waits[at]
                and (creates[other] & spells[at]) - creates[at]
                and not _reaches(waits, other, at)
            ):
                waits[at].append(other)
    return tuple(
        leaf
        if tuple(waited) == leaf.depends_on
        else replace(leaf, depends_on=tuple(waited))
        for leaf, waited in zip(leaves, waits, strict=True)
    )


def _reaches(waits: Sequence[Sequence[int]], start: int, goal: int) -> bool:
    """Whether `start` waits on `goal`, directly or through what it waits on."""
    seen: set[int] = set()
    stack = [start]
    while stack:
        at = stack.pop()
        if at == goal:
            return True
        if at not in seen:
            seen.add(at)
            stack.extend(waits[at])
    return False


def _too_deep(node: _Node, bound: int) -> Refusal:
    """The refusal for a proposal jev would split past `max_refine_depth`."""
    return Refusal(
        node.proposal.target,
        f"jev answered that this proposal can be split further, and it is "
        f"already {node.depth} split(s) below the request, the most "
        f"`max_refine_depth` allows ({bound}), so it is not emitted unsplit",
        field="task",
        what_to_change=(
            f"raise `max_refine_depth` above {bound}, or narrow the request to "
            "fewer behaviour changes"
        ),
    )


def _too_wide(node: _Node, partition: Partition, bound: int) -> Refusal:
    """The refusal for a split into more parts than `max_refine_fanout`."""
    count = len(partition.parts)
    return Refusal(
        node.proposal.target,
        f"jev chose to split this proposal by {partition.kind} into {count} "
        f"parts, more than `max_refine_fanout` allows ({bound}), so it is not "
        "emitted unsplit",
        field="task",
        what_to_change=(
            f"raise `max_refine_fanout` to {count} or more, or narrow the request "
            "to fewer behaviour changes"
        ),
    )
