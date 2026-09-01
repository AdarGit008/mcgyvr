"""Independent verification: what a reviewer is shown, and what its reply becomes.

mcgyvr owned the policy half of this lever and none of the mechanism.
:func:`~mcgyvr.escalate.judge` reads the gate first and returns before
``verifier`` is so much as named on the rejected path;
:class:`~mcgyvr.escalate.Opinion` already separates a refusal from a reply that
could not be read; :attr:`~mcgyvr.escalate.Assurance.VERIFIED` is reachable only
through :attr:`~mcgyvr.escalate.Opinion.AGREED`; and
:func:`~mcgyvr.runner.dispatch_role` has been a finished socket with nothing
plugged into it. What was missing is everything between a model and that enum:
nothing assembled a prompt, nothing read a reply, and nothing ever constructed a
:class:`~mcgyvr.escalate.Review`. This module is that half (#41, #42), ported
from local-ai's ``mvp/orchestrator/verifier.py``.

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
differently, appending Ollama's own ``:latest``, or pasting in a provider
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

**A reviewer-side failure is never charged to the builder.** An unreadable
reply, an unreachable backend and a reviewer that is the builder are all
:attr:`~mcgyvr.escalate.Opinion.UNUSABLE`, which is what
:attr:`~mcgyvr.escalate.Judgement.reviewer_failed` exists to keep distinguishable
from a change that was actually judged and found wanting. local-ai answered
these by bumping the verifier tier and retrying; mcgyvr's pool binds exactly one
``verifier`` role, so there is no tier to bump — what ports is the rule, and
mcgyvr already had the place to record it.

**M1 — the semantic rung stays non-blocking, and its items arrive here as
notes.** :class:`~mcgyvr.gate.GateResult` splits what a rung saw into
``findings``, which reject, and ``observations``, which are real,
line-attributed and deliberately outside the verdict. The semantic rung reports
into the second because mcgyvr measured its false-positive rate and chose to
buy the correct code it would otherwise have rejected. That decision is only
honest if something still judges those items, which is what
:func:`gate_summary` is for: it hands them to the reviewer *labelled as not
having failed anything*, the way local-ai's verifier receives its gate summary.
Promoting them into ``findings`` — here or in the gate — is a policy flip that
must be argued for, not a tidy-up.

**What is deliberately not here.** Which family a task climbs to next, and what
a refused review costs it, are :mod:`mcgyvr.escalate`'s — this module hands back
one :class:`~mcgyvr.escalate.Review` and has no opinion about who tries next,
which is why an ``ESCALATE`` verdict is a refusal here rather than a routing
instruction. Whether the assembled prompt fits a budget is
:func:`~mcgyvr.gate.preflight.check_prompt_fits`'s question and belongs to the
caller that owns the ceiling; local-ai raised on an over-budget verifier input
rather than truncating, and the same rule is expressible here because
:func:`build_prompt` returns the text instead of dispatching it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from mcgyvr.escalate import GATE_ONLY, Opinion, Review, required_policy
from mcgyvr.runner import Request, dispatch_role

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.catalog import Family
    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.pool import SourceMap

#: What the pool calls the reviewer. One name, in one place, because a role that
#: is spelled differently here than in :mod:`mcgyvr.pool` is a role that is
#: silently never found.
VERIFIER_ROLE = "verifier"

#: What a review is allowed to write. The protocol is one token and brief notes,
#: so a large ceiling buys an essay nobody reads; and truncation cannot hide the
#: verdict, because the verdict is the first word of the reply.
#: :class:`~mcgyvr.runner.Request` refuses an uncapped dispatch outright, so
#: this is a number someone had to choose rather than a default inherited from a
#: backend.
REVIEW_OUTPUT_TOKENS = 512

#: What the reviewer is asked, given the prompt. One string in, one string out:
#: everything about *where* it runs is the seam's business, which is what lets
#: every rule in this module be asserted without a backend.
type Ask = Callable[[str], str]


class ReviewerUnavailableError(RuntimeError):
    """The verifier role had a binding and then had nothing to dispatch to.

    Named rather than folded into a generic failure because the two states it
    sits between mean opposite things: an install with *no* verifier role is an
    ordinary configuration that :func:`~mcgyvr.escalate.judge` answers with
    ``UNVERIFIED``, while a role that was bound and then could not serve is a
    reviewer-side fault in the middle of a task.
    """


class ReviewOutcome(StrEnum):
    """The four words a review may open with, and nothing else.

    Named distinctly from :class:`mcgyvr.escalate.Outcome` — which says how a
    whole *task* ended — so the two never share a bare import name on the
    composition path. These are the vocabulary one reviewer is given, kept
    verbatim from local-ai so that a prompt written against either project
    reads the same: a closed set is what makes "the verdict is the first token"
    checkable at all, where free prose would have to be interpreted.
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


# --- what the reviewer is shown --------------------------------------------


def gate_summary(gate: GateResult) -> str:
    """The deterministic run, written for a reviewer that did not watch it.

    Three channels, and they are kept apart because they mean different things
    to someone deciding whether to approve. A finding failed the change. An
    observation is real and was deliberately not rejected on (M1) — the reviewer
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


def _contract_block(view: dict[str, Any]) -> str:
    """The brief the builder worked from, rendered for someone judging it.

    Built from :meth:`~mcgyvr.contract.Contract.worker_view` for the reason #94
    gives: it is the only accessor for worker-facing fields, so a reviewer
    cannot be shown ``risk``, ``verification`` or ``acceptance`` — the
    orchestrator's own reasons for believing a result, which a reviewer that
    could read them could argue with instead of judging the code.

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

# The tag Ollama supplies when a name carries none, so ``qwen2.5-coder`` and
# ``qwen2.5-coder:latest`` are one pull of one blob. Every *other* tag is part
# of the identity: ``:7b`` and ``:32b`` are different weights.
_DEFAULT_TAG = ":latest"


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
    * **The routing prefix dropped.** ``ollama/qwen2.5-coder`` and
      ``hf.co/Qwen/qwen2.5-coder`` say where to fetch the same blob. Only the
      last path segment names it.
    * **A trailing** ``:latest`` **dropped**, because Ollama appends exactly
      that to an untagged name. No other tag is touched.
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
    folded = folded.rpartition("/")[2]
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


def reviewer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    max_output_tokens: int = REVIEW_OUTPUT_TOKENS,
) -> Ask | None:
    """The install's verifier role as something :func:`verify` can ask, or ``None``.

    ``None`` mirrors :meth:`~mcgyvr.pool.SourceMap.role` and is an ordinary
    answer: a keyless install has no verifier, which
    :func:`~mcgyvr.escalate.judge` already answers by labelling the acceptance
    ``UNVERIFIED`` rather than by failing it. Callers get that path by passing
    ``verifier=None``, so the absence is decided here, once, instead of being
    discovered inside a dispatch.

    The request is not marked ``quality_sensitive``. That flag means "this
    output will be read as a measurement of the model" and refuses a
    quality-caveated backend outright (CAV-01); a review is work, and refusing
    would turn the ordinary Ollama install into one with no verifier at all
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
        # A truncated review is still readable: the verdict is the first token,
        # so the cap can only cost notes. Nothing is raised for it here.
        return completion.text

    return ask
