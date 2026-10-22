"""Assemble the prompt one worker attempt is sent: a system bundle and a user message.

:func:`render_user_message` turns a contract's worker view into the sections a
worker reads — task, target, interface, dependency signatures, numbered sources,
stop conditions, the output rule for the declared schema, and the notes from a
rejected attempt — and leaves out every section the view has nothing to say in.
:func:`build_prompt` puts the use case's bundle in front as the system message,
measures the pair with the caller's estimator, and records whether the result
fits the contract's own `context.max_input_tokens` ceiling. A schema with no
reply instruction here has no parser downstream either, so it is refused here,
before dispatch, rather than after an attempt was paid for.
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

# The output rule stated to the worker, one per schema this module can ask for and
# the reply parser can read back. A schema missing from this table is refused by
# build_prompt instead of being rendered as plain prose, because a worker given no
# output rule and a worker whose reply nothing can parse both spend the attempt
# for nothing. Each rule names the target it is asked about, so `target` is
# substituted in only where the text places it.
_REPLY_INSTRUCTIONS: dict[str, str] = {
    WHOLE_FILE: (
        "Reply with the complete new content of {target}, as one fenced code "
        "block and nothing else. Not a diff, not an excerpt, not the changed "
        "lines — the whole file as it should exist after your change."
    ),
}


class UnsupportedSchemaError(ValueError):
    """Raised when a contract's `output_schema` has no reply instruction here.

    Nothing downstream parses such a schema either, so the refusal is raised
    while the prompt is being assembled rather than after an attempt.
    """


@dataclass(frozen=True)
class WorkerPrompt:
    """One assembled prompt and what the assembly measured about it.

    `system` is the use case's bundle text, empty when no bundle applies to this
    contract; `user` is the rendered message. `tokens` counts the two joined as
    they are sent, and `counted_by` says whose count it is — the model-free
    estimate or a real tokenizer — because only an estimate is charged extra.
    `fit_issue` is the preflight issue for a prompt over its own ceiling, and
    None when it fits (or when no ceiling was checked).
    """

    system: str
    user: str
    bundle: Bundle | None
    tokens: int
    counted_by: TokenCount
    fit_issue: PreflightIssue | None

    @property
    def fits(self) -> bool:
        """Whether the prompt stays within the ceiling it was checked against."""
        return self.fit_issue is None

    @property
    def measured(self) -> str:
        """The text the token count was taken from: system and user as sent.

        Joining is done once here so the count, the recorded prompt and any later
        re-measurement all describe the same bytes.
        """
        return _measured(self.system, self.user)


def _measured(system: str, user: str) -> str:
    """Join a system and a user message the way the count and the record see them.

    The two are separated by one newline, so the measured text is the prompt
    itself rather than a sum of two counts taken apart.
    """
    return system + "\n" + user


# A fence never closes shorter than three backticks; see `_fence_for`.
_MIN_FENCE = 3

_BACKTICK_RUN = re.compile(r"`+")


def _fence_for(content: str) -> str:
    """The shortest fence that can hold `content` without being closed by it.

    The widest run of backticks inside the content decides: one more than that,
    and never fewer than three. A file that itself demonstrates fenced blocks
    therefore arrives inside a wider fence instead of ending it early.
    """
    runs = (len(run.group()) for run in _BACKTICK_RUN.finditer(content))
    widest = max(runs, default=0)
    return "`" * max(_MIN_FENCE, widest + 1)


def _render_target_content(target: str, content: str) -> str:
    """Render the target's current content, fenced, under a header naming the file.

    A trailing newline is added when the content lacks one so the closing fence
    starts its own line; the fence width is chosen from the content as given.
    """
    body = content if content.endswith("\n") else content + "\n"
    fence = _fence_for(content)
    return (
        f"CURRENT CONTENT OF {target} (this is the file to change):\n"
        f"{fence}\n{body}{fence}"
    )


def _render_sources(sources: Sequence[dict[str, Any]]) -> str:
    """Render the sources as numbered blocks, [1], [2], … so a reply can cite them.

    A source whose content is None was not read into the contract, so it is named
    with a note that the tree supplies it when the prompt is sent rather than
    being fenced empty. Blocks are separated by a blank line.
    """
    blocks = []
    for number, source in enumerate(sources, start=1):
        header = f"[{number}] {source['path']}"
        content = source["content"]
        if content is None:
            blocks.append(f"{header} (read from the tree when the prompt is sent)")
            continue
        body = content if content.endswith("\n") or not content else content + "\n"
        fence = _fence_for(content)
        blocks.append(f"{header}\n{fence}\n{body}{fence}")
    return "\n\n".join(blocks)


def _render_deps(deps: Sequence[dict[str, Any]]) -> list[str]:
    lines = []
    for dep in deps:
        note = f"  # {dep['note']}" if dep["note"] else ""
        lines.append(f"- {dep['path']}: {dep['signature']}{note}")
    return lines


def render_user_message(view: dict[str, Any], retry: RetryNotes | None = None) -> str:
    """Render a contract's worker view as the user message a worker is sent.

    Sections are appended in a fixed order and each is omitted when the view has
    nothing for it: task, target, interface, dependency signatures, sources, stop
    conditions, the reply rule for the output schema, and the rejection notes of a
    retried attempt. Sections are separated by blank lines and the message ends
    with one newline.
    """
    sections: list[str] = [f"TASK ({view['task_type']}): {view['task']}"]
    # The target's current content only appears when the contract holds it,
    # otherwise the worker is pointed at the target alone.
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
    if view["sources"]:
        sections.append(
            "SOURCES (the files to work from, numbered — cite one as [n] where "
            "a statement rests on it):\n" + _render_sources(view["sources"])
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
    """Assemble the prompt for one attempt at `contract` and measure it.

    The output schema is checked against the reply instructions first, so an
    unparseable schema costs nothing. The system message is the bundle for the
    contract's use case and language — chosen by `adapters`, or the language
    adapters by default — and empty when no bundle applies. The user message comes
    from the contract's worker view, carrying `retry` notes when the attempt is a
    retry. `estimate` counts the joined prompt and `counted_by` labels that count,
    which decides whether a reserve is charged against it.
    """
    if contract.output_schema not in _REPLY_INSTRUCTIONS:
        raise UnsupportedSchemaError(
            f"output_schema {contract.output_schema!r} has no reply instruction "
            f"and no parser; only {WHOLE_FILE!r} is implemented. Refused before "
            f"dispatch rather than after it."
        )
    bundle = bundle_for(contract.kind.use_case.name, contract.target, adapters)
    system = bundle.text if bundle is not None else ""
    user = render_user_message(contract.worker_view(), retry)
    tokens = estimate(_measured(system, user))
    # The ceiling is the one the contract declared for itself, so a prompt that
    # cannot fit is a contract-level failure found here rather than at dispatch.
    # `check_prompt_fits` adds the estimator's reserve when `counted_by` says the
    # count is an estimate, and compares against an exact count when it is not.
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
