"""The live proposer — a reply is proposals or a recorded refusal, never an exception.

`#365 <https://github.com/AdarGit008/mcgyvr/issues/365>`_, item 2. Off-SURFACE:
the product pin (``tools/bench/product.py --check``) does not move for this file.

:func:`mcgyvr.orchestrator.decompose.decompose` takes a :data:`Proposer` and has
exactly one binding in the tree — :class:`RecordedProposer`, which returns a
fixed list. The judgment step has never been asked of a model. #365 flips the
tables: a real commit is the task, the spec is its issue body, and the pool
rung is asked what units of work it would emit. This module is the seam's
first live binding, and the defect it prevents is the obvious one: **a model's
reply is text, and text that is not proposals must become a record rather
than a traceback.** A campaign of 475 tasks (the ``tasks_admitted`` rows with
a spec) cannot stop on the first rung that answers in prose, and it must not
lose the fact that it did — the prose *is* the finding.

Three rules, each one a function below.

1. *The reply is read as a document, in a fixed order, and nothing else is
   tried.* :func:`parse_proposals` accepts ``{"proposals": [...]}``, a bare
   JSON list, or a single ```` ```json ```` fenced block inside prose — the
   three shapes a model told to answer in JSON actually produces. Anything
   else is a :class:`~mcgyvr.orchestrator.decompose.Refusal` whose ``reason``
   says which shape was seen. There is no fourth attempt that scrapes a path
   out of prose: a proposal recovered by guessing would look like a plan.
2. *An item is a :class:`~mcgyvr.orchestrator.decompose.Proposal` or the
   whole reply is refused.* The fields are the dataclass's own, read off it
   rather than copied here, so this module cannot drift from the seam it
   feeds. A missing required field, a wrong type, or a key ``Proposal`` does
   not have refuses the reply **by name** — the last case on purpose, because
   the key a model invents is exactly the one the seam exists to keep out
   (ADR-0007: ``signature``, ``content``). Dropping it silently would permit
   the sixth field the guard did not name. One bad item refuses the reply,
   not the item: a list with a hole in it is not the plan the model stated.
3. *The prompt is a constant, so the record can hash it.* :data:`SYSTEM` and
   :data:`USER` are module constants and :func:`prompt_digest` is their
   digest; a record that names which prompt produced its proposals is
   comparable across a month's runs, and one that does not is not (ADR-0026
   lens 3: a record states the property).

**Where the exception classes are.** Every refusal is a named exception with
the offending thing in its message — :class:`ReplyNotJSONError`,
:class:`ReplyShapeError`, :class:`ProposalFieldError` — but none crosses
:func:`parse_proposals`: it catches its own and returns the ``Refusal``. The
names exist so the *cause* is typed rather than a string prefix, and so a
caller that wants to raise can call :func:`read_proposals` instead.

**What a transport failure is not.** :class:`LiveProposer` records a reply
that is not proposals; it does not swallow a rung that did not reply.
:class:`~mcgyvr.runner.RunnerError` propagates, because "the model answered
in prose" and "srv2 was down" are different findings and a refusal that
folded them together would be the finding nobody could read.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import MISSING, Field, dataclass, field, fields
from typing import Any

from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Refusal
from mcgyvr.pool import Endpoint
from mcgyvr.runner import Request, runner_for

#: The system half of the prompt. Short on purpose: the evidence carries the
#: repository, this carries only the reply shape and the seam's rule — name
#: files and symbols, never state what they look like. ``stop_conditions`` is
#: named as required because the contract schema requires it for every type
#: that runs on a model (``contract._cross_validate``: "name at least one
#: condition"); a prompt that called it optional invited a proposal the seam
#: would refuse on arrival, and the refusal would read as the model's.
SYSTEM = (
    "You are the decomposition step of a coding tool. You are given a request "
    "and what a deterministic pass found in the repository. Reply with JSON "
    'only: {"proposals": [...]}. Each proposal is one unit of work with fields '
    "task_type (one of the listed types), target (a file path the repository "
    "holds), task (what to do, one paragraph), stop_conditions (required: a "
    "list of strings with at least one entry — the situations in which the "
    "worker must report BLOCKED rather than guess), and optionally interface "
    "(the signature to produce), deps (a list of {path, symbol, note} "
    "references — name the symbol, do not state its signature), allow, forbid, "
    "acceptance, demonstration (lists of strings), risk. Use no other fields. "
    "Propose the smallest well-scoped units. If nothing can be proposed, reply "
    '{"proposals": []}.'
)

#: The user half, rendered by :func:`render` with ``str.format``. The four
#: placeholders are the four parts of :class:`Evidence` a proposer may see.
USER = (
    "Request:\n{prompt}\n\n"
    "Servable task types:\n{vocabulary}\n\n"
    "Resolution ({verdict}):\n{candidates}\n\n"
    "Reads:\n{reads}\n"
)

# How much of an unreadable reply a refusal quotes. Enough to see what the
# model did instead, short enough that the record's reason stays a sentence.
_EXCERPT_CHARS = 200

# A single fenced block, ```json or bare ```, with the fence on its own line.
_FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


def _no_default(f: Field[Any]) -> bool:
    """Whether a dataclass field must be supplied — no default, no factory."""
    return f.default is MISSING and f.default_factory is MISSING


#: The item keys the seam accepts: exactly ``Proposal``'s fields, read off the
#: dataclass so a field added there is accepted here without an edit.
FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Proposal))

#: The keys with no default on ``Proposal``. Read, not listed, for the reason
#: above.
REQUIRED: tuple[str, ...] = tuple(f.name for f in fields(Proposal) if _no_default(f))

_DEP_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(DepRef))
_DEP_REQUIRED: tuple[str, ...] = tuple(f.name for f in fields(DepRef) if _no_default(f))

# The tuple-of-strings fields, by shape rather than by name.
_LIST_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(Proposal) if str(f.type) == "tuple[str, ...]"
)


class ProposeError(Exception):
    """A reply that is not proposals. Caught by :func:`parse_proposals`.

    ``subject`` is what the refusal is of — ``"reply"`` for the whole thing,
    ``proposals[i]`` for one item — and ``reason`` says why, in the words a
    :class:`~mcgyvr.orchestrator.decompose.Refusal` will carry.
    """

    def __init__(self, reason: str, subject: str = "reply") -> None:
        super().__init__(f"{subject}: {reason}")
        self.reason = reason
        self.subject = subject


class ReplyNotJSONError(ProposeError):
    """The reply is prose, or JSON that does not parse."""


class ReplyShapeError(ProposeError):
    """The reply is JSON, but not ``{"proposals": [...]}`` or a list."""


class ProposalFieldError(ProposeError):
    """An item is missing a field, carries one ``Proposal`` lacks, or mistypes one."""


def prompt_digest() -> str:
    """The digest of both prompt halves — what a record names as its prompt."""
    material = json.dumps([SYSTEM, USER])
    return hashlib.blake2b(material.encode("utf-8"), digest_size=8).hexdigest()


def parse_proposals(text: str) -> list[Proposal] | Refusal:
    """The reply as proposals, or the refusal it is. Never raises.

    ``Refusal.subject`` is ``"reply"`` for a reply that could not be read at
    all and ``proposals[i]`` for an item that could not be a ``Proposal``, so
    a run's refusals read as an account of what each rung actually sent.
    """
    try:
        return read_proposals(text)
    except ProposeError as exc:
        return Refusal(exc.subject, exc.reason)


def read_proposals(text: str) -> list[Proposal]:
    """The reply as proposals, raising a named :class:`ProposeError` otherwise.

    The raising form of :func:`parse_proposals`, for a caller that would
    rather stop than record.
    """
    document = _document_of(text)
    items = _items_of(document)
    return [_proposal_of(i, item) for i, item in enumerate(items)]


def _document_of(text: str) -> object:
    """The JSON in a reply: the whole text, else the one fenced block in it."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    blocks = _FENCE.findall(stripped)
    if len(blocks) > 1:
        raise ReplyNotJSONError(
            f"the reply carries {len(blocks)} fenced blocks and this reader "
            f"takes exactly one — reply with a single JSON document"
        )
    if blocks:
        try:
            return json.loads(blocks[0])
        except ValueError as exc:
            raise ReplyNotJSONError(
                f"the reply's fenced block is not JSON ({exc}): {_excerpt(blocks[0])!r}"
            ) from exc
    raise ReplyNotJSONError(
        f"the reply is not JSON and carries no fenced block — it reads as "
        f"prose: {_excerpt(stripped)!r}"
    )


def _items_of(document: object) -> list[object]:
    """The proposal items: the list under ``proposals``, or the bare list."""
    if isinstance(document, list):
        return list(document)
    if not isinstance(document, dict):
        raise ReplyShapeError(
            f"the reply is JSON {type(document).__name__}, not an object with "
            f"a 'proposals' list or a bare list"
        )
    if "proposals" not in document:
        keys = ", ".join(sorted(str(k) for k in document)) or "(none)"
        raise ReplyShapeError(
            f"the reply is a JSON object without a 'proposals' key. Keys "
            f"present: {keys}"
        )
    items = document["proposals"]
    if not isinstance(items, list):
        raise ReplyShapeError(
            f"'proposals' is JSON {type(items).__name__}, not a list of items"
        )
    return list(items)


def _proposal_of(i: int, item: object) -> Proposal:
    """One item as a ``Proposal``, refusing by field name at the first fault."""
    subject = f"proposals[{i}]"
    if not isinstance(item, dict):
        raise ProposalFieldError(
            f"item is JSON {type(item).__name__}, not an object", subject
        )
    keys = {str(k) for k in item}
    unknown = sorted(keys - set(FIELDS))
    if unknown:
        raise ProposalFieldError(
            f"field {unknown[0]!r} is not a Proposal field (Proposal has: "
            f"{', '.join(FIELDS)}) — the seam names references, it does not "
            f"state facts",
            subject,
        )
    missing = [name for name in REQUIRED if name not in keys]
    if missing:
        raise ProposalFieldError(f"required field {missing[0]!r} is missing", subject)

    values: dict[str, Any] = {}
    for name in FIELDS:
        if name not in item:
            continue
        value = item[name]
        if name == "deps":
            values[name] = _deps_of(value, subject)
        elif name in _LIST_FIELDS:
            values[name] = _strings_of(name, value, subject)
        else:
            values[name] = _string_of(name, value, subject, required=name in REQUIRED)
    return Proposal(**values)


def _deps_of(value: object, subject: str) -> tuple[DepRef, ...]:
    if not isinstance(value, list):
        raise ProposalFieldError(
            f"field 'deps' is JSON {type(value).__name__}, not a list", subject
        )
    refs: list[DepRef] = []
    for j, dep in enumerate(value):
        where = f"{subject}.deps[{j}]"
        if not isinstance(dep, dict):
            raise ProposalFieldError(
                f"dependency is JSON {type(dep).__name__}, not an object", where
            )
        keys = {str(k) for k in dep}
        unknown = sorted(keys - set(_DEP_FIELDS))
        if unknown:
            raise ProposalFieldError(
                f"field {unknown[0]!r} is not a dependency field (a dependency "
                f"has: {', '.join(_DEP_FIELDS)}) — name the symbol, do not "
                f"state what it looks like",
                where,
            )
        missing = [name for name in _DEP_REQUIRED if name not in keys]
        if missing:
            raise ProposalFieldError(f"required field {missing[0]!r} is missing", where)
        refs.append(
            DepRef(
                path=_string_of("path", dep["path"], where, required=True),
                symbol=_string_of("symbol", dep["symbol"], where, required=True),
                note=_string_of("note", dep.get("note", ""), where, required=False),
            )
        )
    return tuple(refs)


def _strings_of(name: str, value: object, subject: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProposalFieldError(
            f"field {name!r} must be a list of strings, got JSON "
            f"{type(value).__name__}",
            subject,
        )
    return tuple(value)


def _string_of(name: str, value: object, subject: str, *, required: bool) -> str:
    if not isinstance(value, str):
        raise ProposalFieldError(
            f"field {name!r} must be a string, got JSON {type(value).__name__}",
            subject,
        )
    if required and not value.strip():
        raise ProposalFieldError(f"required field {name!r} is empty", subject)
    return value


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat[:_EXCERPT_CHARS] + ("…" if len(flat) > _EXCERPT_CHARS else "")


# --- the proposer ------------------------------------------------------------


def render(evidence: Evidence) -> tuple[str, str]:
    """The prompt pair for one piece of evidence: ``(system, user)``.

    Everything in the user half is something exploration already found — the
    candidates with their scores and the bounded reads with their line
    ranges. Nothing here reads the tree, which is ADR-0001 boundary 2 kept on
    this side of the seam as well.
    """
    vocabulary = "\n".join(f"- {t.name}: {t.guarantee}" for t in evidence.vocabulary)
    candidates = "\n".join(
        f"- {c.path} (score {c.score:.2f}; {'; '.join(c.evidence)})"
        for c in evidence.resolution.candidates
    )
    reads = "\n\n".join(
        f"--- {r.path}:{r.start}-{r.end} ({r.reason})\n{r.text}"
        for r in evidence.exploration.reads
    )
    user = USER.format(
        prompt=evidence.prompt,
        vocabulary=vocabulary or "(none)",
        verdict=evidence.resolution.verdict.value,
        candidates=candidates or "(none)",
        reads=reads or "(none)",
    )
    return SYSTEM, user


@dataclass
class LiveProposer:
    """A proposer that asks a rung — :data:`Proposer`'s first live binding.

    ``dispatch`` is ``(system, user) -> reply text``; :func:`runner_dispatch`
    builds one over the product runner, and a test hands in a lambda. Calling
    the proposer renders the evidence, dispatches, and reads the reply. What
    it keeps is what a record needs: every raw reply in ``replies`` and every
    reply that was not proposals in ``refusals``, in call order, so the
    campaign can put the model's actual output beside the spec (#365 item 5)
    without this module deciding what it meant.

    ``__call__`` conforms to :data:`Proposer` — a refusal is recorded and an
    empty sequence returned, which ``decompose`` reports as a refusal of the
    request. :meth:`propose` is the same step returning the refusal itself.
    """

    dispatch: Callable[[str, str], str]
    replies: list[str] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)

    def propose(self, evidence: Evidence) -> list[Proposal] | Refusal:
        """Render, dispatch, read. The reply is kept whatever it was."""
        system, user = render(evidence)
        reply = self.dispatch(system, user)
        self.replies.append(reply)
        out = parse_proposals(reply)
        if isinstance(out, Refusal):
            self.refusals.append(out)
        return out

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        out = self.propose(evidence)
        return () if isinstance(out, Refusal) else out


#: The reply ceiling a proposal dispatch is built with. It is not the
#: measurement rigs' ``MAX_OUTPUT_TOKENS`` (768, a whole-file reply ceiling):
#: a proposal list for one commit is a few hundred tokens but can run past
#: 768 on a wide commit. The cap is there so a rung that loops cannot run the
#: campaign's clock, and a reply that hits it parses as a refusal naming the
#: JSON it could not finish.
PROPOSAL_MAX_OUTPUT_TOKENS = 2048


def runner_dispatch(
    endpoint: Endpoint,
    model: str,
    *,
    max_output_tokens: int = PROPOSAL_MAX_OUTPUT_TOKENS,
    timeout_s: float | None = None,
) -> Callable[[str, str], str]:
    """A ``dispatch`` over the product runner, bound to one endpoint and model.

    The runner is chosen by the endpoint's protocol through
    :func:`mcgyvr.runner.runner_for`, which is the only place that choice is
    made; this binds the two things a rung resolves to and nothing else, so
    ``run.py`` can build one per pool rung from its source map. Temperature
    is the request's default, 0.0 — the reply is judged, not sampled.
    """
    runner = runner_for(endpoint)

    def dispatch(system: str, user: str) -> str:
        request = (
            Request(prompt=user, system=system, max_output_tokens=max_output_tokens)
            if timeout_s is None
            else Request(
                prompt=user,
                system=system,
                max_output_tokens=max_output_tokens,
                timeout_s=timeout_s,
            )
        )
        return runner.generate(model, request).text

    return dispatch
