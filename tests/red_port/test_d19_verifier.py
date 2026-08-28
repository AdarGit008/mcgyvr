"""D19 — the verifier policy is complete, and nothing has ever asked a model a question.

This is the cheapest of the three blocking levers because mcgyvr already owns the hard
half. :func:`~mcgyvr.escalate.judge` reads the gate first and returns before
``verifier``
is so much as named on the rejected path; :class:`~mcgyvr.escalate.Opinion` already
distinguishes a refusal from a reply that could not be read;
:attr:`~mcgyvr.escalate.Assurance.VERIFIED` is already reachable only through
:attr:`~mcgyvr.escalate.Opinion.AGREED`; and :func:`~mcgyvr.runner.dispatch_role` is a
finished socket with zero callers. What is missing is the plug: nothing constructs a
:class:`~mcgyvr.escalate.Review`, and no code turns a model's reply into one.

So every statement here is about the missing half, and each is one a port gets wrong in
its own way:

* **A verifier runs at all above the deterministic family.** ``required_policy`` already
  says it must — the upgrade is unconditional — and today that requirement is satisfied
  by labelling the acceptance ``unverified`` forever, which is honest and is not
  verification. Asserted with the policy stated first, so the test says why a verifier
  is owed before asserting that one answered.
* **A model never verifies its own output.** Held with a reviewer that raises if it is
  asked anything at all, rather than by counting calls: a self-review that ran and was
  then discarded is the spend this rule exists to prevent. The control matters as much
  as the refusal — the same setup with a *different* reviewer must produce an opinion,
  or a port that simply never verifies would pass the refusal half.
* **The verifier sees the whole original file and the applied change.** Every non-blank
  line of the pre-change file is asserted present, including one far from the edit. A
  test that only checked the target's name, or that the diff was in there, would pass
  against a prompt carrying a diff's three context lines — which is a reviewer judging
  a function it has not read.
* **M1 — the semantic check stays non-blocking, and its finding reaches the verifier as
  a note.** Both halves, because they are one decision. mcgyvr measured the
  false-positive rate of the resolver and deliberately routed its items to
  ``observations``, which are reported and never rejecting; a port that quietly promoted
  them to ``findings`` would look stricter and would reject correct code. A test that
  only asserted the note reached the prompt would not notice. So the gate is really run,
  with a stand-in for the sandboxed rung, and its verdict asserted before the note is.
* **An unreadable verdict is not an approval.** Three replies that a substring search
  would approve, and one that genuinely does approve — the last is the control, because
  "never approve anything" passes the other three.
* **VERIFIED is unreachable without agreement.** Asserted end to end through
  :func:`~mcgyvr.escalate.judge`, since the policy is only worth as much as the reply
  parser feeding it: a parser that reads "Cannot approve" as agreement makes the
  existing, correct policy report a warrant it never earned.

Nothing here dispatches. The reviewer is a callable, which is the shape the socket
already has, and the assertions are about what it was shown and what its answer became.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.catalog import Family
from mcgyvr.escalate import Assurance, Opinion, judge, required_policy
from mcgyvr.gate import ChangeSet, Finding, Gate, GateResult
from mcgyvr.gate.semantic import SemanticReport
from tests.red_port.conftest import required

BEHAVIOR = (
    "have a fresh-context verifier read a change and turn its reply into a Review"
)

# Any family a model executes in. Rank is what the policy reads, and rank 0 is the
# deterministic family the upgrade exempts.
MODEL_FAMILY = Family(name="local", rank=1, doc="a model on the operator's own machine")

BUILDER = "qwen2.5-coder:7b"
REVIEWER = "qwen2.5-coder:32b"

# The target as it stood before the change. The last line is deliberately far from the
# edit: a diff would not carry it, and a verifier that never saw it cannot say whether
# the change broke the caller two functions down.
ORIGINAL = (
    "import time\n"
    "\n"
    "\n"
    "def fetch(url):\n"
    "    return url\n"
    "\n"
    "\n"
    "def fetch_all(urls):\n"
    "    return [fetch(u) for u in urls]\n"
)

CHANGE = (
    "--- a/src/pkg/fetch.py\n"
    "+++ b/src/pkg/fetch.py\n"
    "@@ -4,2 +4,5 @@\n"
    " def fetch(url):\n"
    "+    for attempt in range(3):\n"
    "+        if attempt:\n"
    "+            time.sleep(2**attempt)\n"
    "     return url\n"
)

APPROVAL = "APPROVE — the retry policy matches the contract and nothing else changed."


def _verify() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.verify", fromlist=["verify"]).verify
    )


def _longest_text(*args: Any, **kwargs: Any) -> str:
    """The prompt out of whatever a caller passed, positionally or by name.

    The port picks the signature; what the reviewer is shown is the behavior. Reading
    the longest string keeps these tests from asserting a parameter name.
    """
    texts = [value for value in (*args, *kwargs.values()) if isinstance(value, str)]
    return max(texts, key=len, default="")


@dataclass
class Reviewer:
    """A stand-in for the model the verifier role reaches, and a record of what it "
    "saw."""

    reply: str = APPROVAL
    prompts: list[str] = field(default_factory=list)

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        self.prompts.append(_longest_text(*args, **kwargs))
        return self.reply

    @property
    def shown(self) -> str:
        assert self.prompts, "the verifier was never asked anything"
        return self.prompts[-1]


def _never_asked(*args: Any, **kwargs: Any) -> str:
    """A reviewer that fails rather than answers. See the self-verification test."""
    raise AssertionError("a model was asked to review the output it had just written")


@dataclass
class _Resolver:
    """Stands in for the sandboxed semantic rung, which needs a provisioned image.

    What M1 settles is not how a call is resolved but what the gate does with an
    unresolvable one, so the rung's answer is supplied and its verdict is asserted.
    """

    finding: Finding

    def run(self, changeset: ChangeSet) -> SemanticReport:
        return SemanticReport(observations=(self.finding,))


def _review(verify: Any, ask: Any, **overrides: Any) -> Any:
    """One verification of the same change, with only what the test varies changed."""
    call: dict[str, Any] = {
        "family": MODEL_FAMILY,
        "gate": GateResult(),
        "change": CHANGE,
        "original": ORIGINAL,
        "builder": BUILDER,
        "reviewer": REVIEWER,
        "ask": ask,
    }
    call.update(overrides)
    return verify(**call)


def test_a_verifier_runs_for_work_above_the_deterministic_family(contract: Any) -> None:
    """The policy already demands one; this asserts one actually answers.

    The premise is stated first and comes from mcgyvr itself: work a model did is owed
    a fresh-context reviewer whatever the contract declared. Today that debt is settled
    by labelling the result unverified, which is honest and is not a verifier.
    """
    assert required_policy(contract, MODEL_FAMILY) == "model", (
        "the premise of this whole file: a model's output is owed a verifier"
    )
    verify = _verify()
    reviewer = Reviewer()

    review = _review(verify, reviewer, contract=contract)

    assert review.opinion is Opinion.AGREED, (
        f"the approval did not read as one: {review}"
    )
    assert contract.task in reviewer.shown, (
        "the verifier was not told what it is judging"
    )


def test_a_model_is_never_asked_to_verify_the_output_it_wrote(contract: Any) -> None:
    """Independence is the whole warrant, and it is asserted before the spend, not
    after.

    The reviewer raises if it is asked anything: a self-review that ran and was then
    thrown away has already cost what this rule exists to save. The second half is the
    control — with a different model the same reply is an approval, so the refusal is
    about identity and not about a verifier that never runs.
    """
    verify = _verify()

    itself = _review(verify, _never_asked, contract=contract, reviewer=BUILDER)

    assert itself.opinion is not Opinion.AGREED, "a model approved its own output"
    assert BUILDER in itself.detail, (
        f"the refusal must name the model it would not let judge itself, said: "
        f"{itself.detail!r}"
    )

    other = _review(verify, Reviewer(), contract=contract, reviewer=REVIEWER)
    assert other.opinion is Opinion.AGREED, (
        "control: with a reviewer that is not the builder, the same reply must verify"
    )


def test_the_verifier_is_shown_the_whole_original_file_and_the_applied_change(
    contract: Any,
) -> None:
    """Full pre-change context, not a diff's context lines, plus what was actually done.

    Every non-blank line of the original is asserted, ``fetch_all`` included. It is two
    functions away from the edit and a diff would not carry it, so a reviewer that has
    only the patch cannot say whether the change broke its caller — and would still
    have passed a test that just looked for the target's name.
    """
    verify = _verify()
    reviewer = Reviewer()

    _review(verify, reviewer, contract=contract)

    shown = reviewer.shown
    for line in ORIGINAL.splitlines():
        if line.strip():
            assert line in shown, (
                f"the verifier was not shown the original line {line!r}"
            )
    assert "+    for attempt in range(3):" in shown, (
        "the verifier was not shown the change it is judging"
    )


def test_a_semantic_finding_stays_non_blocking_and_reaches_the_verifier_as_a_note(
    repo: Path, contract: Any
) -> None:
    """M1 — a settled decision, held on both halves because they are one decision.

    An unresolvable call is real information and a thin sample: mcgyvr routes it to
    ``observations``, which are reported and never rejecting, and hands the judgement to
    a reviewer instead. A port that quietly promoted it to a ``finding`` would look
    stricter while rejecting correct code, and a test that only checked the note reached
    the prompt would not notice. So the gate is really run first and its verdict
    asserted, and only then the note.
    """
    (repo / "src" / "pkg" / "fetch.py").write_text(
        "import time\n\n\ndef fetch(url):\n    time.sleep_backoff(1)\n    return url\n"
    )
    unresolvable = Finding(
        check="semantic",
        path="src/pkg/fetch.py",
        message="time.sleep_backoff does not resolve in this environment",
        line=5,
    )

    gate = Gate().run(
        ChangeSet.detect(repo),
        contract.scope,
        # A stand-in, not a SemanticCheck: this test is about what the gate does
        # with a finding, not about staging the real resolver into a sandbox.
        semantic=_Resolver(unresolvable),  # type: ignore[arg-type]
    )

    assert gate.accepted, f"an unresolvable call rejected the change: {gate.findings}"
    assert unresolvable not in gate.findings, "the semantic rung was made blocking"
    assert unresolvable in gate.observations, (
        "the semantic finding was not reported at all"
    )

    verify = _verify()
    reviewer = Reviewer()

    _review(verify, reviewer, contract=contract, gate=gate)

    assert unresolvable.message in reviewer.shown, (
        "the finding the gate declined to reject on never reached the verifier, so "
        "nothing in the run ever judges it"
    )


def test_a_verdict_that_cannot_be_read_is_not_an_approval(contract: Any) -> None:
    """Three replies a substring search approves, and one real approval as the control.

    Each unreadable reply is a different way of being wrong: a refusal that contains the
    word, a conditional that contains the word, and an agreement that contains no
    verdict
    at all. Without the fourth case, a parser that approves nothing ever would pass.
    """
    verify = _verify()
    unreadable = (
        "Cannot approve this change: the retry loop has no ceiling.",
        "I would APPROVE if the retry loop were bounded.",
        "Sure, this looks fine to me.",
    )

    for reply in unreadable:
        review = _review(verify, Reviewer(reply=reply), contract=contract)
        assert review.opinion is not Opinion.AGREED, (
            f"a reply that states no verdict was read as an approval: {reply!r}"
        )

    approving = _review(verify, Reviewer(reply=APPROVAL), contract=contract)
    assert approving.opinion is Opinion.AGREED, (
        "control: a reply that does approve must read as an approval"
    )


def test_the_verified_assurance_is_unreachable_unless_a_review_agreed(
    contract: Any,
) -> None:
    """The existing policy is only as good as the parser feeding it.

    ``judge`` already reaches VERIFIED through ``AGREED`` alone, so this asserts the
    half
    the port adds: a reply that asked for changes, and a reply that said nothing
    legible,
    must both leave the acceptance short of verified — while a real approval reaches it,
    or the label is unreachable and the policy is decoration.
    """
    verify = _verify()

    def assurance_for(reply: str) -> Assurance | None:
        return judge(
            contract,
            MODEL_FAMILY,
            GateResult(),
            value="def fetch(url):\n    return url\n",
            verifier=lambda: _review(verify, Reviewer(reply=reply), contract=contract),
        ).assurance

    assert assurance_for(APPROVAL) is Assurance.VERIFIED, (
        "a verifier ran and agreed, and the acceptance was not labelled verified"
    )
    assert assurance_for("REMEDIATE — bound the retry loop.") is not Assurance.VERIFIED
    assert assurance_for("Cannot approve this change.") is not Assurance.VERIFIED
