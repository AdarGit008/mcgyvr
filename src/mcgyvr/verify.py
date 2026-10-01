"""Independent verification: what a reviewer is shown, and what its reply becomes.

:mod:`mcgyvr.escalate` owns the policy half of this lever:
:func:`~mcgyvr.escalate.judge` reads the gate first and returns before
``verifier`` is so much as named on the rejected path;
:class:`~mcgyvr.escalate.Opinion` separates a refusal from a reply that could
not be read; and :attr:`~mcgyvr.escalate.Assurance.VERIFIED` is reachable only
through :attr:`~mcgyvr.escalate.Opinion.AGREED`. This module is the mechanism
between a model and that enum: it assembles the prompt, reads the reply and
constructs the :class:`~mcgyvr.escalate.Review`, dispatching through
:func:`~mcgyvr.runner.dispatch_role`.

**The reviewer is shown the whole pre-change file, not a diff's context lines.**
A patch carries three lines either side of an edit, which is enough to see that
a change is syntactically plausible and not enough to see that it broke the
caller two functions down. So :func:`build_prompt` takes the target's full
content as it stood before the change, and a reviewer that was not given one is
told so in the prompt rather than left to assume it saw everything.

**A model never verifies its own output, and the refusal happens before the
spend.** Identity is checked ahead of assembling anything, because a
self-review that ran and was then discarded has already cost what the rule
exists to save. The comparison is on the weights the two names point at, not on
the two strings — a rule the config file can defeat by capitalising a model
differently, appending a registry's ``:latest``, or pasting in a provider
prefix is not a rule, and neither is one a zero-width space defeats.
:func:`model_identity` is that reading, and it normalises only what a registry
itself treats as noise. Two models from one family are *not* the same model:
``qwen2.5-coder:32b`` reviewing ``qwen2.5-coder:7b`` is the ordinary local
setup, and refusing it would leave most installs with no verifier at all.

**The verdict must be the exact first token of the reply.** ``Cannot approve``
contains the word and is a refusal; ``I would APPROVE if …`` contains it and is
a condition; ``Sure, this looks fine`` is an agreement carrying no verdict at
all. A substring search reads the first two as approvals, which is the single
failure this whole path is shaped around, so :func:`read_verdict` anchors at the
start of the first non-empty line and returns ``None`` for everything else.
``None`` is not a refusal — see the next paragraph — and it is certainly not an
approval.

**The typed verdict is the default, and prose is the fallback.** Every
:class:`Reviewer` carries a typed seam, so the verdict is first asked as a
single :class:`~mcgyvr.decision.Noul` read from next-token probabilities — no
prose, no anchor, no substring to misread — and :func:`read_typed_verdict`
reads it. A reviewer whose unit answers without probabilities, or refuses the
request that asks for them, is asked in prose instead, through
:func:`read_verdict`. A reviewer that could not be reached is not asked twice:
that is a reviewer-side failure, whichever way it would have been asked.

**Who reviews.** ``verifier.unit`` names the reviewer outright. With no unit
named, :func:`reviewer_rung` picks one per builder: the next rung of the climb
dearer than the builder's whose model is not the builder's. Where there is none
— the builder is the dearest rung, or every dearer rung serves the builder's
model — there is no independent reviewer, and :class:`NoReviewer` says so in
words :func:`~mcgyvr.escalate.judge` puts on the acceptance.

**A reviewer-side failure is never charged to the builder.** An unreadable
reply, an unreachable backend, a review stopped at its output cap and a reviewer
that is the builder are all :attr:`~mcgyvr.escalate.Opinion.UNUSABLE`, which is
what :attr:`~mcgyvr.escalate.Judgement.reviewer_failed` exists to keep
distinguishable from a change that was actually judged and found wanting. A
truncated review is unusable even when it opens with ``APPROVE``: the notes a
cap cut off may be the condition the approval was given under.

**The semantic rung's non-blocking items arrive here as notes.**
:class:`~mcgyvr.gate.GateResult` splits what a rung saw into
``findings``, which reject, and ``observations``, which are real,
line-attributed and deliberately outside the verdict. That is only honest if
something still judges those items, which is what :func:`gate_summary` is for:
it hands them to the reviewer *labelled as not having failed anything*.
Promoting them into ``findings`` — here or in the gate — is a policy flip that
must be argued for, not a tidy-up.

**What is deliberately not here.** Which family a task climbs to next, and what
a refused review costs it, are :mod:`mcgyvr.escalate`'s — this module hands back
one :class:`~mcgyvr.escalate.Review` and has no opinion about who tries next,
which is why an ``ESCALATE`` verdict is a refusal here rather than a routing
instruction. Whether the assembled prompt fits a budget is
:func:`~mcgyvr.gate.preflight.check_prompt_fits`'s question and belongs to the
caller that owns the ceiling, which can ask it because :func:`build_prompt`
returns the text instead of dispatching it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import (
    BoolAnswer,
    Decision,
    DecisionError,
    Noul,
    Question,
    classify_role,
    classify_rung,
)
from mcgyvr.escalate import GATE_ONLY, Opinion, Review, required_policy
from mcgyvr.gate.jev import JEV_QUESTIONS, JevCheck, jev_check_for
from mcgyvr.route import by_family
from mcgyvr.runner import Completion, Request, dispatch, dispatch_role
from mcgyvr.weights import WEIGHTS_SUFFIXES

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from mcgyvr.capacity import Capacity
    from mcgyvr.catalog import Family
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.pool import SourceMap

#: What the pool calls the reviewer. One name, in one place, because a role that
#: is spelled differently here than in :mod:`mcgyvr.pool` is a role that is
#: silently never found.
VERIFIER_ROLE = "verifier"

#: What a review is allowed to write. The protocol is one token and brief notes,
#: so a large ceiling buys an essay nobody reads. A review that reaches it is
#: unusable rather than read: the verdict is the first word, but the notes the
#: cap cut off may be what the verdict was conditional on.
#: :class:`~mcgyvr.runner.Request` refuses an uncapped dispatch outright, so
#: this is a number someone had to choose rather than a default inherited from a
#: backend.
REVIEW_OUTPUT_TOKENS = 512

#: What the reviewer is asked, given the prompt. One string in, one string out:
#: everything about *where* it runs is the seam's business, which is what lets
#: every rule in this module be asserted without a backend.
type Ask = Callable[[str], str]

#: The typed-verdict seam: the assembled state in, a
#: :class:`~mcgyvr.decision.Decision` out. Built by :func:`decider_for` from the
#: verifier role, and the new default for a reviewer whose unit serves
#: next-token probabilities. The free-text :data:`Ask` path remains for the
#: installs that still bind a prose reviewer.
type Decide = Callable[[Any], Decision]

#: The answer key a typed verdict is read from, and the single
#: :class:`~mcgyvr.decision.Noul` asked for it.
VERDICT_KEY = "verdict"
VERDICT_QUESTION = Noul(
    "Should this change be approved against the contract it was written for?"
)

#: What a typed ask raises when the reviewer *answered* but not with
#: probabilities: a reply with no logprobs, or none of the labels among them.
#: That says the unit does not serve a typed verdict, which is the one reason
#: to ask it in prose instead. An HTTP error status is not on the list: it is
#: raised for a rate limit, a model still loading and a server fault alike,
#: and asking the backend that just answered one a second way only spends a
#: second request on it — so it is unusable, like an unreachable reviewer, and
#: it is not remembered: the next ask may find the backend recovered.
_NOT_TYPED: tuple[type[Exception], ...] = (DecisionError,)


class ReviewerUnavailableError(RuntimeError):
    """The verifier role had a binding and then had nothing to dispatch to.

    Named rather than folded into a generic failure because the two states it
    sits between mean opposite things: an install with *no* verifier role is an
    ordinary configuration that :func:`~mcgyvr.escalate.judge` answers with
    ``UNVERIFIED``, while a role that was bound and then could not serve is a
    reviewer-side fault in the middle of a task.
    """


class ReviewTruncatedError(RuntimeError):
    """A review stopped at its output cap, so its verdict is not read.

    Raised inside the ask, where :func:`verify` turns every failure into
    :attr:`~mcgyvr.escalate.Opinion.UNUSABLE`: a capped review is the
    reviewer's failure, and it is never an approval.
    """


class ReviewOutcome(StrEnum):
    """The four words a review may open with, and nothing else.

    Named distinctly from :class:`mcgyvr.escalate.Outcome` — which says how a
    whole *task* ended — so the two never share a bare import name on the
    composition path. These are the vocabulary one reviewer is given: a closed
    set is what makes "the verdict is the first token" checkable at all, where
    free prose would have to be interpreted.
    """

    APPROVE = "APPROVE"
    APPROVE_WITH_NOTES = "APPROVE_WITH_NOTES"
    REMEDIATE = "REMEDIATE"
    ESCALATE = "ESCALATE"


# Four outcomes onto three opinions, and both collapses are decisions.
# APPROVE_WITH_NOTES is an approval — a reviewer who wanted the change altered
# had REMEDIATE to say so with, and the notes ride along in `Review.detail`.
# ESCALATE is a refusal and not an unusable answer, because the reviewer did
# give a verdict; who should try next is `mcgyvr.escalate`'s to decide from a
# failed attempt, and a review that could route work would be deciding it twice.
_OPINION: dict[ReviewOutcome, Opinion] = {
    ReviewOutcome.APPROVE: Opinion.AGREED,
    ReviewOutcome.APPROVE_WITH_NOTES: Opinion.AGREED,
    ReviewOutcome.REMEDIATE: Opinion.REFUSED,
    ReviewOutcome.ESCALATE: Opinion.REFUSED,
}


@dataclass(frozen=True)
class ReviewVerdict:
    """A reply that could be read: the outcome it opened with, and its notes."""

    outcome: ReviewOutcome
    notes: str = ""

    def as_review(self) -> Review:
        """This verdict as the answer :func:`~mcgyvr.escalate.judge` reads.

        The outcome word is kept in ``detail`` alongside the notes rather than
        dropped once it has chosen an opinion: ``judge`` renders that detail
        into a retry note, and "the verifier refused" is not something a worker
        can act on where "REMEDIATE: the retry loop has no ceiling" is.
        """
        word = self.outcome.value
        detail = f"{word}: {self.notes}" if self.notes else word
        if _OPINION[self.outcome] is Opinion.AGREED:
            return Review.agreed(detail)
        return Review.refused(detail)


# Longest first: APPROVE is a prefix of APPROVE_WITH_NOTES, so a table tried in
# declaration order would read the fuller verdict as a bare approval with an odd
# suffix. `[ _]` accepts the spaced spelling, which is what a model writes when
# it repeats the token back as English.
_TOKENS: tuple[tuple[ReviewOutcome, re.Pattern[str]], ...] = tuple(
    (outcome, re.compile(outcome.value.replace("_", "[ _]") + r"\b", re.IGNORECASE))
    for outcome in sorted(ReviewOutcome, key=lambda o: -len(o.value))
)

#: Punctuation a model puts between its verdict and its reasons. Stripped from
#: the front of the notes so the notes start at the first word of the argument,
#: and never from the back, where it is the model's own sentence. The en dash is
#: escaped rather than written because ruff reads a literal one as a confusable
#: hyphen (RUF001), and it is in the set precisely because models write it.
_NOTE_SEPARATORS = " \t:;.,-—\u2013"


def read_verdict(reply: str) -> ReviewVerdict | None:
    """The verdict a reply opens with, or ``None`` when it opens with none.

    Anchored at the start of the first non-empty line, and nowhere else: a
    token found later in the reply is a model discussing the vocabulary, not
    using it. ``None`` is the whole safety property — a reply this function
    cannot read is handed on as :attr:`~mcgyvr.escalate.Opinion.UNUSABLE`, which
    fails the attempt without ever being mistaken for agreement.

    Case is ignored, as in local-ai, because a lowercase ``approve`` at the head
    of the reply is the same act as an uppercase one; what is not ignored is
    position, which is the part a chatty reply gets wrong.
    """
    lines = reply.strip().splitlines()
    for index, line in enumerate(lines):
        opening = line.strip()
        if not opening:
            continue
        for outcome, pattern in _TOKENS:
            found = pattern.match(opening)
            if found is None:
                continue
            head = opening[found.end() :].lstrip(_NOTE_SEPARATORS)
            tail = "\n".join(lines[index + 1 :]).strip()
            return ReviewVerdict(
                outcome=outcome,
                notes="\n".join(part for part in (head, tail) if part),
            )
        # Only the first non-empty line may carry the verdict. Reading on would
        # find the token in "I would APPROVE if …" a paragraph later and call a
        # condition an approval.
        return None
    return None


def read_typed_verdict(decision: Decision) -> Review:
    """A typed verdict as the :class:`Review` :func:`~mcgyvr.escalate.judge` reads.

    A :class:`~mcgyvr.decision.Noul` is answered as a single ``Yes``/``No``
    token read from next-token probabilities, so there is no prose to anchor
    and no substring to misread. ``Yes`` is agreement, ``No`` is refusal, and
    anything else — an answer key that is absent, an answer that is not a
    :class:`~mcgyvr.decision.BoolAnswer` — is unusable rather than a guess.
    """
    answer = decision.answers.get(VERDICT_KEY)
    if not isinstance(answer, BoolAnswer):
        return Review.unusable(
            "the typed verdict carried no readable answer; a review with no "
            "readable answer is not an approval."
        )
    detail = "typed verdict: approve" if answer.value else "typed verdict: refuse"
    detail += (
        f" (probability of approval {answer.probability_true:.2f}, "
        f"confidence {answer.confidence:.2f})"
    )
    return Review.agreed(detail) if answer.value else Review.refused(detail)


# --- what the reviewer is shown --------------------------------------------


def gate_summary(gate: GateResult) -> str:
    """The deterministic run, written for a reviewer that did not watch it.

    Three channels, and they are kept apart because they mean different things
    to someone deciding whether to approve. A finding failed the change. An
    observation is real and was deliberately not rejected on — the reviewer
    is told exactly that, so it weighs the item without treating it as settled.
    An environment issue is a bar that never applied, which a reviewer has to
    know before reading a clean gate as a strong signal.

    Inconclusive rungs need no channel of their own: the gate already renders
    each one into ``environment_issues``, so they arrive with the rest.

    Findings are rendered with
    :meth:`~mcgyvr.gate.findings.Finding.for_model`, which is the same boundary
    :func:`_contract_block` holds one function below: a reviewer that cannot be
    shown ``acceptance`` cannot be shown it inside a finding's path either, and
    an acceptance finding's path is the command.
    """
    verdict = "accepted" if gate.accepted else "rejected"
    lines = [f"The deterministic gate {verdict} this change."]
    if gate.findings:
        lines.append("Failed:")
        lines.extend(f"- {finding.for_model()}" for finding in gate.findings)
    if gate.observations:
        lines.append(
            "Reported without rejecting. These did not fail the change and no "
            "check is asking for them to be fixed; judging them is yours:"
        )
        lines.extend(f"- {finding.for_model()}" for finding in gate.observations)
    if gate.environment_issues:
        lines.append("Could not run, so this change was never checked for it:")
        lines.extend(f"- {issue}" for issue in gate.environment_issues)
    return "\n".join(lines)


def verdict_state(
    contract: Contract,
    gate: GateResult,
    change: str,
    original: str | None = None,
) -> dict[str, Any]:
    """The structured state a typed verdict is asked over.

    The same material the free-text prompt carries — the contract's worker
    view, the deterministic gate's run, and the change — as JSON the decision
    primitive serializes. Nothing about how the change was written reaches it,
    for the same reason :func:`build_prompt` shows none.
    """
    view = contract.worker_view()
    pre = original if original is not None else view["target_content"]
    return {
        "task_type": view["task_type"],
        "task": view["task"],
        "target": view["target"],
        "interface": view["interface"],
        "deterministic_gate": gate_summary(gate),
        "original": pre,
        "change": change,
    }


def _contract_block(view: dict[str, Any]) -> str:
    """The brief the builder worked from, rendered for someone judging it.

    Built from :meth:`~mcgyvr.contract.Contract.worker_view` because it is the
    only accessor for worker-facing fields, so a reviewer cannot be shown
    ``risk``, ``verification`` or ``acceptance`` — the orchestrator's own
    reasons for believing a result, which a reviewer that could read them could
    argue with instead of judging the code.

    Not :func:`~mcgyvr.worker.prompt.render_user_message`, which renders the
    same view: that one ends with the worker's OUTPUT instruction, and telling a
    reviewer to reply with the complete new content of the target contradicts
    the one-token protocol this prompt closes with. ``target_content`` is left
    out for a plainer reason — the pre-change file has a section of its own
    below, and paying for it twice buys nothing.
    """
    lines = [
        f"task ({view['task_type']}): {view['task']}",
        f"target: {view['target']}",
    ]
    if view["interface"]:
        lines.append(f"the result must expose exactly: {view['interface']}")
    for dep in view["deps"]:
        note = f"  # {dep['note']}" if dep["note"] else ""
        lines.append(f"may call: {dep['path']}: {dep['signature']}{note}")
    for condition in view["stop_conditions"]:
        lines.append(f"was told to stop rather than guess if: {condition}")
    return "\n".join(lines)


def _original_block(original: str | None, target: str) -> str:
    """The pre-change file, or a sentence saying which kind of absence this is.

    ``""`` and ``None`` are different absences and local-ai already spelled the
    difference: an empty string is a change that creates a file, and there is
    genuinely nothing to show; ``None`` is a caller that did not supply one. The
    second is stated rather than omitted, because a reviewer given no original
    and no notice has no way to know it is judging a change against a file it
    never saw.
    """
    if original:
        return f"ORIGINAL FILE before the change ({target}), in full:\n{original}"
    if original == "":
        return "ORIGINAL FILE: none — the change creates a new file."
    return (
        f"ORIGINAL FILE: not supplied. You are seeing the change to {target} "
        f"and not the file it changed; judge only what the change itself shows, "
        f"and say so if that is not enough."
    )


def build_prompt(
    contract: Contract,
    *,
    gate: GateResult,
    change: str,
    original: str | None = None,
) -> str:
    """Fresh context: the contract, the gate's run, the whole file, the change.

    Fresh is the whole warrant. Nothing about *how* the change was written
    reaches this prompt — no transcript, no reasoning, no earlier attempt — so
    the reviewer agrees with the code or it agrees with nothing. That is also
    why the material comes before the instruction: the last thing the model
    reads is the one sentence that fixes the shape of its reply.

    ``original`` defaults to the contract's own ``target_content`` when the
    caller does not pass one, since that field is exactly the pre-change target
    where a contract carries it, and a reviewer left without a file the
    orchestrator already had is a cost paid for nothing.
    """
    view = contract.worker_view()
    pre = original if original is not None else view["target_content"]
    outcomes = " | ".join(outcome.value for outcome in ReviewOutcome)
    return "\n\n".join(
        [
            "You are an independent code verifier. Judge the change below "
            "against the contract it was written for. You did not write it, you "
            "cannot edit it, and nothing about how it was written is shown to "
            "you.",
            f"CONTRACT:\n{_contract_block(view)}",
            f"DETERMINISTIC CHECKS (already run, before you were asked):\n"
            f"{gate_summary(gate)}",
            _original_block(pre, view["target"]),
            f"CHANGE as applied to {view['target']}:\n{change}",
            f"Evaluate: contract compliance, correctness, regression risk, "
            f"scope expansion, unnecessary complexity.\n"
            f"Your reply MUST START with exactly one outcome token "
            f"({outcomes}) as the first word of the first line, then brief "
            f"notes. A reply that starts with anything else is discarded "
            f"unread.",
        ]
    )


# --- which weights a name points at -----------------------------------------

# Latin letters that another script spells with the same pixels. Applied after
# ``casefold``, so only the lowercase forms are needed. Deliberately short: it
# covers the Cyrillic and Greek letters that appear in Latin-looking model
# names, and it is not a general confusable table — the goal is that two names
# nobody could tell apart on screen compare equal, not that every pair of
# code points with a shared glyph does.
_CONFUSABLES = str.maketrans(
    {
        # Cyrillic
        "\u0430": "a",  # CYRILLIC SMALL LETTER A
        "\u0435": "e",  # CYRILLIC SMALL LETTER IE
        "\u043a": "k",  # CYRILLIC SMALL LETTER KA
        "\u043c": "m",  # CYRILLIC SMALL LETTER EM
        "\u043d": "h",  # CYRILLIC SMALL LETTER EN
        "\u043e": "o",  # CYRILLIC SMALL LETTER O
        "\u0440": "p",  # CYRILLIC SMALL LETTER ER
        "\u0441": "c",  # CYRILLIC SMALL LETTER ES
        "\u0442": "t",  # CYRILLIC SMALL LETTER TE
        "\u0443": "y",  # CYRILLIC SMALL LETTER U
        "\u0445": "x",  # CYRILLIC SMALL LETTER HA
        "\u0455": "s",  # CYRILLIC SMALL LETTER DZE
        "\u0456": "i",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
        "\u0458": "j",  # CYRILLIC SMALL LETTER JE
        "\u0501": "d",  # CYRILLIC SMALL LETTER KOMI DE
        "\u051b": "q",  # CYRILLIC SMALL LETTER QA
        "\u051d": "w",  # CYRILLIC SMALL LETTER WE
        # Greek
        "\u03b1": "a",  # GREEK SMALL LETTER ALPHA
        "\u03b2": "b",  # GREEK SMALL LETTER BETA
        "\u03b5": "e",  # GREEK SMALL LETTER EPSILON
        "\u03b9": "i",  # GREEK SMALL LETTER IOTA
        "\u03ba": "k",  # GREEK SMALL LETTER KAPPA
        "\u03bd": "v",  # GREEK SMALL LETTER NU
        "\u03bf": "o",  # GREEK SMALL LETTER OMICRON
        "\u03c1": "p",  # GREEK SMALL LETTER RHO
        "\u03c4": "t",  # GREEK SMALL LETTER TAU
        "\u03c5": "u",  # GREEK SMALL LETTER UPSILON
        "\u03c7": "x",  # GREEK SMALL LETTER CHI
    }
)

# Characters that separate words inside a model name and carry no identity of
# their own. Removed rather than folded to one, so ``qwen2.5-coder`` and
# ``qwen2_5_coder`` are the same name. Every dash goes with them, by category
# rather than by listing: NFKC leaves U+2011 NON-BREAKING HYPHEN and most of
# the ``Pd`` block exactly as typed, and a hyphen nobody can see the difference
# in is the same defeat as a zero-width space.
_SEPARATORS = "-_. \t\u2212"
_SEPARATOR_CATEGORY = "Pd"

# The tag a registry supplies when a name carries none, so ``qwen2.5-coder``
# and ``qwen2.5-coder:latest`` are one pull of one blob. Every *other* tag is
# part of the identity: ``:7b`` and ``:32b`` are different weights.
_DEFAULT_TAG = ":latest"

# llama.cpp's tail on the first shard of a split weights file,
# ``-00001-of-00002``: the server is handed that file and the model is the
# stem without it. Read only where a weights suffix was actually removed, the
# same narrowness :func:`mcgyvr.weights.is_model` keeps.
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")


def model_identity(name: str) -> str:
    """The weights ``name`` points at, as a string two names can be compared on.

    The comparison this exists for decides whether a model is about to review
    its own output, and both directions of getting it wrong are expensive. Read
    two spellings of one model as two models and the refusal is defeated by a
    tag, a prefix or an invisible character. Read two models as one and the
    ordinary local install — a big model reviewing a small one from the same
    family — loses its verifier entirely.

    So this normalises only what a registry itself treats as noise, and never
    guesses at similarity:

    * **NFKC, then invisibles removed.** A zero-width space, a soft hyphen or a
      bidi mark is not part of a name; it is a way to write one name twice.
    * **Confusables folded to Latin.** A Cyrillic ``U+043E`` is the same pixels
      as a Latin ``o`` in every config file a person will ever read.
    * **The routing prefix dropped.** ``registry/qwen2.5-coder`` and
      ``hf.co/Qwen/qwen2.5-coder`` say where to fetch the same blob. Only the
      last path segment names it, and a Windows ``\\`` separates segments as
      ``/`` does.
    * **A weights file read as the model it holds.** ``/weights/x.gguf`` is how
      llama.cpp names the model ``x`` (:mod:`mcgyvr.weights`), so one weights
      suffix comes off, and with it the ``-00001-of-00002`` tail of a split
      file. Only where the suffix was there: ``x.v2`` is not ``x``.
    * **A trailing** ``:latest`` **dropped**, because a registry appends
      exactly that to an untagged name. No other tag is touched.
    * **Separators removed**, so ``qwen2.5-coder``, ``qwen2_5_coder`` and
      ``qwen25coder`` are one name.

    What it does *not* do is edit-distance, prefix matching or family
    grouping. ``mistral`` and ``mixtral`` are one letter apart and are two
    models; a rule that collapsed them would refuse a review nobody asked it to
    refuse.

    Returns ``""`` for a name that is empty or holds nothing but noise — which
    is an unnamed model, and :func:`_independence_fault` answers it as one
    rather than as a match against another empty name.
    """
    folded = unicodedata.normalize("NFKC", name)
    folded = "".join(
        char
        for char in folded
        if unicodedata.category(char) not in {"Cc", "Cf", "Zl", "Zp", "Zs"}
    )
    folded = folded.casefold().translate(_CONFUSABLES)
    folded = folded.replace("\\", "/").rpartition("/")[2]
    for suffix in WEIGHTS_SUFFIXES:
        if folded.endswith(suffix):
            folded = _SHARD.sub("", folded[: -len(suffix)])
            break
    if folded.endswith(_DEFAULT_TAG):
        folded = folded[: -len(_DEFAULT_TAG)]
    return "".join(
        char
        for char in folded
        if char not in _SEPARATORS and unicodedata.category(char) != _SEPARATOR_CATEGORY
    )


# --- one verification -------------------------------------------------------


def _independence_fault(builder: str, reviewer: str) -> str | None:
    """Why this pairing cannot produce an independent review, or ``None``.

    Both anonymous cases are faults. A reviewer or a builder that was not named
    leaves independence unestablished, and an unestablished independence is not
    a weaker warrant than a broken one — it is the same warrant, missing.

    The names are compared through :func:`model_identity` and reported as the
    operator wrote them. A message quoting the normalised form would send
    someone looking for a config line that does not exist.
    """
    if not model_identity(builder) or not model_identity(reviewer):
        return (
            f"independence cannot be established: the change was written by "
            f"{builder!r} and the reviewer is {reviewer!r}, and a review is "
            f"only worth the distance between those two names."
        )
    if model_identity(builder) == model_identity(reviewer):
        return (
            f"the reviewer is {reviewer!r}, the model that wrote this change "
            f"({builder!r}). A model does not verify its own output, so nothing "
            f"was asked and nothing was spent."
        )
    return None


def independent(builder: str, reviewer: str) -> bool:
    """Whether ``reviewer`` is a model other than ``builder``, both named.

    The one rule :func:`verify` refuses a review by, asked before anything else
    is asked of a reviewer: which rung reviews (:func:`reviewer_rung`), and
    whether the gate's typed checks may be put to it.
    """
    return _independence_fault(builder, reviewer) is None


def verify(
    contract: Contract,
    *,
    family: Family,
    gate: GateResult,
    change: str,
    builder: str,
    reviewer: str,
    ask: Ask,
    original: str | None = None,
    decide: Decide | None = None,
) -> Review:
    """Ask one independent reviewer about one applied change.

    Meant to be the body of the ``verifier`` callable
    :func:`~mcgyvr.escalate.judge` takes, which is why it returns a
    :class:`~mcgyvr.escalate.Review` and never a bare boolean: ``judge`` reaches
    :attr:`~mcgyvr.escalate.Assurance.VERIFIED` through
    :attr:`~mcgyvr.escalate.Opinion.AGREED` alone, so everything this function
    decides is decided by which of the three opinions it returns.

    Nothing is dispatched until both refusals have had their say — the family's
    policy, then the identity of the reviewer — because each of them exists to
    prevent a spend, and a check that runs after the request has already been
    sent prevents nothing.

    ``decide`` is the typed verdict: when it is supplied the verdict is read
    as a :class:`~mcgyvr.decision.Noul` through
    :func:`~mcgyvr.decision.classify`, and ``ask`` is used only if the
    reviewer answered without probabilities (:data:`_NOT_TYPED`). When it is
    ``None`` the free-text ``ask`` path is used, unchanged.
    """
    if required_policy(contract, family) == GATE_ONLY:
        # The deterministic family, on a contract that asked for nothing more:
        # the gate is the whole bar there, and a review would be a warrant the
        # policy does not describe. `judge` never routes here in that case, so
        # reaching this is a caller's mistake and it is answered without spend.
        return Review.unusable(
            f"no verifier is owed: work in the {family.name!r} family under a "
            f"{GATE_ONLY!r} contract is accepted on the deterministic gate, so "
            f"no model was asked."
        )

    fault = _independence_fault(builder, reviewer)
    if fault is not None:
        return Review.unusable(fault)

    if decide is not None:
        typed = _typed_verdict(contract, gate, change, reviewer, original, decide)
        if typed is not None:
            return typed

    prompt = build_prompt(contract, gate=gate, change=change, original=original)
    try:
        reply = ask(prompt)
        verdict = read_verdict(reply)
    except Exception as exc:
        # Deliberately everything the seam can raise: a transport error, a
        # backend that answered rubbish, a quality caveat, a reply that is not
        # even text. They differ in how they are fixed and not in what they
        # mean here, which is that the reviewer produced no verdict — a
        # reviewer-side failure, never the builder's, and `judge` records it as
        # exactly that. The read sits inside the same protection as the ask, so
        # a reply that cannot be read is the same category as a reply that
        # never arrived.
        return Review.unusable(f"the reviewer {reviewer!r} could not be asked: {exc}")

    if verdict is None:
        opening = next((line for line in reply.splitlines() if line.strip()), "")
        return Review.unusable(
            f"the reply from {reviewer!r} states no verdict — it opens "
            f"{opening.strip()[:120]!r}, and a reply that names no outcome is "
            f"not an approval."
        )
    return verdict.as_review()


def _typed_verdict(
    contract: Contract,
    gate: GateResult,
    change: str,
    reviewer: str,
    original: str | None,
    decide: Decide,
) -> Review | None:
    """Read a typed verdict through ``decide``, under the same protection as prose.

    The identity check has already run (:func:`verify` refuses a self-review
    before this is reached), so this is only the ask and the read. A ``decide``
    that raises is a reviewer-side failure — the builder is never charged —
    except where it raised because the reviewer serves no probabilities
    (:data:`_NOT_TYPED`): that is ``None``, and the caller asks in prose.
    """
    state = verdict_state(contract, gate, change, original)
    try:
        decision = decide(state)
    except _NOT_TYPED:
        return None
    except Exception as exc:
        return Review.unusable(f"the reviewer {reviewer!r} could not be asked: {exc}")
    return read_typed_verdict(decision)


def decider_for(
    source_map: SourceMap,
    *,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
    capacity: Capacity | None = None,
) -> Decide | None:
    """The install's verifier role as a typed-verdict seam, or ``None``.

    Mirrors :func:`reviewer_for` one seam over: where that one dispatches a
    prose reply, this one reads a typed :class:`~mcgyvr.decision.Decision`
    through :func:`~mcgyvr.decision.classify_role`. ``None`` is an ordinary
    answer — an install with no verifier role bound has no verifier — and a
    role declared but unusable raises the same way :func:`reviewer_for` does.
    """
    if source_map.role_model(VERIFIER_ROLE) is None:
        return None

    def decide(state: Any) -> Decision:
        decision = classify_role(
            source_map,
            VERIFIER_ROLE,
            state,
            {VERDICT_KEY: VERDICT_QUESTION},
            capacity=capacity,
            timeout_s=timeout_s,
        )
        if decision is None:  # the role was bound a moment ago
            raise ReviewerUnavailableError(
                f"the {VERIFIER_ROLE!r} role has no source to dispatch to"
            )
        return decision

    return decide


def reviewer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    max_output_tokens: int = REVIEW_OUTPUT_TOKENS,
) -> Ask | None:
    """The install's verifier role as something :func:`verify` can ask, or ``None``.

    ``None`` mirrors :meth:`~mcgyvr.pool.SourceMap.role` and is an ordinary
    answer: an install with no verifier role bound has no verifier, which
    :func:`~mcgyvr.escalate.judge` answers by labelling the acceptance
    ``UNVERIFIED`` rather than by failing it. Callers get that path by passing
    ``verifier=None``, so the absence is decided here, once, instead of being
    discovered inside a dispatch.

    The request is not marked ``quality_sensitive``. That flag means "this
    output will be read as a measurement of the model" and refuses a
    quality-caveated backend outright (CAV-01); a review is work, and refusing
    would turn the ordinary local install into one with no verifier at all
    while telling the operator nothing.
    """
    # ``role_model`` rather than ``role``: this is a presence check, and a
    # ``RoleBinding`` would hand this module an endpoint and its
    # ``credential()`` to answer a yes/no question. Dispatch stays with
    # ``dispatch_role``, below the seam, where the endpoint belongs.
    if source_map.role_model(VERIFIER_ROLE) is None:
        return None

    def ask(prompt: str) -> str:
        completion = dispatch_role(
            source_map,
            VERIFIER_ROLE,
            Request(prompt=prompt, max_output_tokens=max_output_tokens),
            capacity=capacity,
        )
        if completion is None:  # the role was bound a moment ago
            raise ReviewerUnavailableError(
                f"the {VERIFIER_ROLE!r} role has no source to dispatch to"
            )
        return _review_text(completion, f"the {VERIFIER_ROLE!r} role")

    return ask


def _review_text(completion: Completion, who: str) -> str:
    """The text of a review, or :class:`ReviewTruncatedError` for one that was cut.

    The cap is :data:`REVIEW_OUTPUT_TOKENS`, and a review that reached it is not
    read at all: ``APPROVE`` followed by notes the cap cut off is an approval
    whose conditions nobody saw. Raised rather than returned, so it lands where
    every other reviewer-side failure does — unusable, never the builder's.
    """
    if completion.truncated:
        raise ReviewTruncatedError(
            f"the review from {who} stopped at its output cap of "
            f"{completion.max_output_tokens} tokens, so its verdict is not read"
        )
    return completion.text


# --- who reviews -------------------------------------------------------------


@dataclass(frozen=True)
class Reviewer:
    """One reviewer, resolved: the model it is, and the ways it is asked.

    ``ask`` is the prose seam :func:`verify` falls back to; ``decide`` the
    typed verdict, asked first; ``jev`` the gate's typed-question rung
    (:class:`~mcgyvr.gate.jev.JevCheck`) bound to the same reviewer. ``where``
    says which part of the config chose it, for the sentence an operator reads.
    ``unit`` is the unit every one of those dispatches to, so the driver can
    send them through its waker as it sends the builder's
    (:meth:`mcgyvr.wake.Waker.dispatching`).
    """

    model: str
    ask: Ask
    decide: Decide | None = None
    jev: JevCheck | None = None
    where: str = ""
    unit: str | None = None


@dataclass(frozen=True)
class NoReviewer:
    """There is no independent reviewer for this builder, and why, in words."""

    reason: str


#: Which reviewer judges the work of one builder rung, named by the rung.
type Reviewers = Callable[[str], Reviewer | NoReviewer]


def reviewer_rung(config: Config, source_map: SourceMap, builder: str) -> str | None:
    """The rung that reviews ``builder``'s work when no unit is named, or ``None``.

    The next rung of the climb dearer than ``builder`` — families in rank
    order, rungs in the order the ladder writes them, the order
    :func:`~mcgyvr.route.by_family` gives — whose model is not the builder's
    by :func:`model_identity`. A dearer rung serving the builder's model under
    another unit name or another spelling is passed over, because a review is
    only worth the distance between the two models. Only usable rungs count;
    ``None`` is the dearest rung, a rung the pool does not offer, or a ladder
    above the builder that serves nothing but the builder's model.
    """
    grouped = by_family(config, source_map)
    climb = [
        rung
        for family in sorted(grouped, key=lambda family: family.rank)
        for rung in grouped[family]
    ]
    names = [rung.name for rung in climb]
    if builder not in names:
        return None
    built_with = climb[names.index(builder)].model
    for rung in climb[names.index(builder) + 1 :]:
        if independent(built_with, rung.model):
            return rung.name
    return None


def reviewers_for(
    config: Config,
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Reviewers:
    """Who reviews each builder's work under ``config``.

    Three answers, read once. ``verifier.enabled: false`` is no reviewer for
    anyone, said as that. A named ``verifier.unit`` is the one reviewer for
    everyone — asked about its model here, so a role declared on a source that
    cannot serve raises :class:`~mcgyvr.pool.SourceUnavailableError` now,
    while refusing is still free. Otherwise each builder's reviewer is
    :func:`reviewer_rung`'s pick, and a builder with none gets a
    :class:`NoReviewer` that says why.

    Every reviewer carries a typed seam that remembers a unit that does not
    serve probabilities, so the prose fallback costs one refused request per
    reviewer and not one per question.
    """
    if not config.get("verifier.enabled", True):
        off = NoReviewer("review is switched off by `verifier.enabled: false`")
        return lambda builder: off

    unit = config.get("verifier.unit")
    if unit is not None:
        model = source_map.role_model(VERIFIER_ROLE)
        ask = reviewer_for(source_map, capacity=capacity)
        decide = decider_for(source_map, timeout_s=timeout_s, capacity=capacity)
        jev = jev_check_for(
            source_map, VERIFIER_ROLE, timeout_s=timeout_s, capacity=capacity
        )
        if model is None or ask is None:
            unbound = NoReviewer(
                f"`verifier.unit` names {unit!r} and the {VERIFIER_ROLE!r} role "
                f"has no model to ask"
            )
            return lambda builder: unbound
        memory = _TypedMemory()
        named = Reviewer(
            model=model,
            ask=ask,
            decide=memory.guard(decide) if decide is not None else None,
            jev=JevCheck(decide=memory.guard(jev.decide)) if jev is not None else None,
            where=f"`verifier.unit` {unit!r}",
            unit=str(unit),
        )
        return lambda builder: named

    picked: dict[str, Reviewer | NoReviewer] = {}

    def pick(builder: str) -> Reviewer | NoReviewer:
        if builder not in picked:
            picked[builder] = _on_rung(
                config, source_map, builder, capacity=capacity, timeout_s=timeout_s
            )
        return picked[builder]

    return pick


def _on_rung(
    config: Config,
    source_map: SourceMap,
    builder: str,
    *,
    capacity: Capacity | None,
    timeout_s: float,
) -> Reviewer | NoReviewer:
    """The reviewer :func:`reviewer_rung` picks for ``builder``, made askable."""
    rung = reviewer_rung(config, source_map, builder)
    offered = source_map.get(rung) if rung is not None else None
    if rung is None or offered is None:
        return NoReviewer(
            f"no rung dearer than {builder!r} serves a model other than the "
            f"builder's, so there is no independent reviewer"
        )

    def ask(prompt: str) -> str:
        completion = dispatch(
            source_map,
            rung,
            Request(prompt=prompt, max_output_tokens=REVIEW_OUTPUT_TOKENS),
            capacity=capacity,
        )
        return _review_text(completion, f"rung {rung!r}")

    def by_rung(state: Any, questions: Mapping[str, Question]) -> Decision:
        return classify_rung(
            source_map,
            rung,
            state,
            questions,
            capacity=capacity,
            timeout_s=timeout_s,
        )

    memory = _TypedMemory()

    def decide(state: Any) -> Decision:
        return by_rung(state, {VERDICT_KEY: VERDICT_QUESTION})

    def checks(state: Any) -> Decision:
        return by_rung(state, JEV_QUESTIONS)

    return Reviewer(
        model=offered.model,
        ask=ask,
        decide=memory.guard(decide),
        jev=JevCheck(decide=memory.guard(checks)),
        where=f"rung {rung!r}",
        unit=rung,
    )


class _TypedMemory:
    """One reviewer's typed seams, refusing at once after its unit showed it
    serves no probabilities.

    The gate's typed checks ask per changed file and per gate run, and the
    verdict asks again: against a unit that answers without logprobs every one
    of those is a request that cannot succeed. The first refusal of the
    :data:`_NOT_TYPED` kind is kept, for every seam guarded by the same memory,
    and raised again without a request.
    """

    def __init__(self) -> None:
        self.refused: Exception | None = None

    def guard(self, decide: Decide) -> Decide:
        def guarded(state: Any) -> Decision:
            if self.refused is not None:
                raise self.refused
            try:
                return decide(state)
            except _NOT_TYPED as exc:
                self.refused = exc
                raise

        return guarded
