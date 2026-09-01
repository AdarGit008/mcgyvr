"""Assembling what a worker is sent: a measured bundle and a contract.

Two messages, and the split is the finding rather than a convention. CLM-0004
varied only the system prompt across its four conditions and kept "the contract
is always the user message" fixed, so that is the shape reproduced here: the
bundle is *how to work*, the contract is *what to do*, and they do not mix.

**The user message is built from :meth:`~mcgyvr.contract.Contract.worker_view`
and nothing else.** That method is the only accessor for worker-facing fields,
which is what makes "orchestrator-only fields never reach the worker prompt"
(#94) a structural property instead of a review item. ``risk``,
``verification``, ``acceptance`` and ``limits`` are how the orchestrator
decides where to run work and whether to believe the result; a worker that
could read them could argue with them. Reaching around ``worker_view()`` to
render a field directly off the contract would quietly cost that property, so
nothing here touches the contract's attributes except through it.

**The target's content is rendered as its own section, and the section says
what it is for.** A worker told to reply with the complete new content of a
file, and shown a file, must not have to infer that the two are the same file —
so the header names the target and says outright that this is the one to change
(#150). The fence is chosen wider than any backtick run inside the content, for
the reason :mod:`mcgyvr.worker.reply` closes a fence only on one at least as
wide: a file that itself contains fences would otherwise end its own block and
hand the worker a truncated target. No language tag is attached — the header
already names the file, extension included, and a tag inferred here would be a
second statement of the same fact with its own way of being wrong.

**``max_input_tokens`` is used, not shown.** It is worker-facing on the schema,
but it is a budget the orchestrator enforces rather than an instruction a model
can act on — telling a worker its own input ceiling spends tokens to say
something the worker cannot use. It is spent here on the fit check instead.

**The fit check is this module's, and it is the first production caller of
:func:`~mcgyvr.gate.preflight.check_prompt_fits`.** The contract declares
``max_input_tokens`` as "the hard ceiling the assembled worker prompt must fit
under", and this is the first point at which an assembled prompt exists to
measure. A prompt that does not fit is returned as a
:class:`~mcgyvr.gate.preflight.PreflightIssue` rather than raised: it is an
orchestration error — the same class of thing as a dirty tree — and preflight's
existing shape already says so. Raising would also deny a caller the assembled
prompt it needs in order to report *what* did not fit.

**A retry says what failed and nothing else.** When an attempt follows a
rejected one, the prompt carries that attempt's failing checks —
:class:`~mcgyvr.escalate.RetryNotes`, whose contents are #43's rule and not
this module's: passing checks, observations the gate did not reject on, and a
tool that was not installed are all excluded there, and rendering is all that
happens here. The section goes last, after the output instruction, because it
is the most specific thing in the prompt and the least useful to read first.

**The estimate is injectable, and the count says which kind it was.** CLM-0011
measured the model-free proxy under-counting by up to 17.9% at the median
depending on the vocabulary, so ``check_prompt_fits`` charges a proxy count a
reserve and an exact count nothing. Passing a real tokenizer here — with
``counted_by=TOKENIZER`` to say so — is how a caller opts out of the reserve.
The seam is also what makes the assembled prompt re-measurable: CLM-0011's band
was measured over prompt *content*, never over a finished prompt, because until
now no finished prompt existed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.contract import Contract
from mcgyvr.escalate import RetryNotes
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.preflight import PreflightIssue, TokenCount, check_prompt_fits
from mcgyvr.orchestrator.read import estimate_tokens
from mcgyvr.worker.bundle import Bundle, bundle_for
from mcgyvr.worker.reply import WHOLE_FILE

# What the worker is told to produce, per declared output schema. The parser and
# this table are two halves of one protocol: whatever shape is described here is
# what `mcgyvr.worker.reply` will accept back, and a schema absent from both is
# absent from both.
_REPLY_INSTRUCTIONS: dict[str, str] = {
    WHOLE_FILE: (
        "Reply with the complete new content of {target}, as one fenced code "
        "block and nothing else. Not a diff, not an excerpt, not the changed "
        "lines — the whole file as it should exist after your change."
    ),
}


class UnsupportedSchemaError(ValueError):
    """The contract declared a shape this port has no instruction or parser for."""


@dataclass(frozen=True)
class WorkerPrompt:
    """One assembled dispatch, with what it cost and whether it fits."""

    system: str
    user: str
    bundle: Bundle | None
    tokens: int
    counted_by: TokenCount
    fit_issue: PreflightIssue | None

    @property
    def fits(self) -> bool:
        """Whether the assembled prompt is inside the contract's ceiling."""
        return self.fit_issue is None


# CommonMark's minimum, and what every bundle instructs.
_MIN_FENCE = 3

_BACKTICK_RUN = re.compile(r"`+")


def _fence_for(content: str) -> str:
    """A fence at least one backtick wider than anything ``content`` contains."""
    runs = (len(run.group()) for run in _BACKTICK_RUN.finditer(content))
    widest = max(runs, default=0)
    return "`" * max(_MIN_FENCE, widest + 1)


def _render_target_content(target: str, content: str) -> str:
    """The target's current content, fenced, under a header that says what it is."""
    body = content if content.endswith("\n") else content + "\n"
    fence = _fence_for(content)
    return (
        f"CURRENT CONTENT OF {target} (this is the file to change):\n"
        f"{fence}\n{body}{fence}"
    )


def _render_deps(deps: Sequence[dict[str, Any]]) -> list[str]:
    lines = []
    for dep in deps:
        note = f"  # {dep['note']}" if dep["note"] else ""
        lines.append(f"- {dep['path']}: {dep['signature']}{note}")
    return lines


def render_user_message(view: dict[str, Any], retry: RetryNotes | None = None) -> str:
    """Render the worker-facing half of a contract as the user message.

    Takes the *view* rather than the contract so that the boundary is visible
    in the signature: this function is incapable of reading a field
    ``worker_view()`` did not hand it. ``retry`` is not a contract field and
    does not reach around that — it is what the *last* attempt was told it got
    wrong, which no contract can know.
    """
    sections: list[str] = [f"TASK ({view['task_type']}): {view['task']}"]
    sections.append(f"TARGET: {view['target']}")
    if view["target_content"]:
        sections.append(_render_target_content(view["target"], view["target_content"]))
    if view["interface"]:
        sections.append(
            f"INTERFACE (the result must expose exactly this):\n{view['interface']}"
        )
    if view["deps"]:
        body = "\n".join(_render_deps(view["deps"]))
        sections.append(
            f"DEPENDENCIES (signatures only — call them, do not reimplement "
            f"them):\n{body}"
        )
    if view["stop_conditions"]:
        body = "\n".join(f"- {c}" for c in view["stop_conditions"])
        sections.append(
            f"STOP AND REPORT BLOCKED IF (do not guess past any of these):\n{body}"
        )
    instruction = _REPLY_INSTRUCTIONS.get(view["output_schema"])
    if instruction is not None:
        sections.append("OUTPUT: " + instruction.format(target=view["target"]))
    if retry is not None:
        sections.append(
            f"YOUR PREVIOUS ATTEMPT WAS REJECTED. Fix exactly these and change "
            f"nothing else — every other check passed:\n{retry.text}"
        )
    return "\n\n".join(sections) + "\n"


def build_prompt(
    contract: Contract,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    estimate: Callable[[str], int] = estimate_tokens,
    counted_by: TokenCount = TokenCount.ESTIMATE,
    retry: RetryNotes | None = None,
) -> WorkerPrompt:
    """Assemble the two messages a worker is sent, and check they fit.

    ``estimate`` defaults to the model-free proxy every other budget in the
    project is spent against; a caller with a real tokenizer passes it here and
    sets ``counted_by=TOKENIZER`` so the fit check stops charging a reserve it
    no longer needs.

    ``retry`` makes this a second attempt on the same contract. It is measured
    with the rest of the prompt rather than appended after the fit check: a
    retry that no longer fits its own contract's ceiling is exactly the case
    where saying so at zero cost is worth most.
    """
    if contract.output_schema not in _REPLY_INSTRUCTIONS:
        raise UnsupportedSchemaError(
            f"output_schema {contract.output_schema!r} has no reply instruction "
            f"and no parser; only {WHOLE_FILE!r} is implemented (ADR-0009). "
            f"Refused before dispatch rather than after it."
        )
    bundle = bundle_for(contract.target, adapters)
    system = bundle.text if bundle is not None else ""
    user = render_user_message(contract.worker_view(), retry)
    tokens = estimate(system + "\n" + user)
    issue = check_prompt_fits(
        tokens,
        contract.max_input_tokens,
        counted_by=counted_by,
    )
    return WorkerPrompt(
        system=system,
        user=user,
        bundle=bundle,
        tokens=tokens,
        counted_by=counted_by,
        fit_issue=issue,
    )
