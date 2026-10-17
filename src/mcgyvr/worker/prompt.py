""

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
from mcgyvr.worker.reply import MEDIA_ARTIFACT, PROSE, WHOLE_FILE

#
#
#
#
_REPLY_INSTRUCTIONS: dict[str, str] = {
    WHOLE_FILE: (
        "Reply with the complete new content of {target}, as one fenced code "
        "block and nothing else. Not a diff, not an excerpt, not the changed "
        "lines — the whole file as it should exist after your change."
    ),
    PROSE: (
        "Reply with the answer as plain prose and nothing else. No fence, no "
        "code block, no preamble."
    ),
    MEDIA_ARTIFACT: (
        "Reply with the media-generation request as plain text and nothing "
        "else. No fence, no code block, no preamble."
    ),
}


class UnsupportedSchemaError(ValueError):
    ""


@dataclass(frozen=True)
class WorkerPrompt:
    ""

    system: str
    user: str
    bundle: Bundle | None
    tokens: int
    counted_by: TokenCount
    fit_issue: PreflightIssue | None

    @property
    def fits(self) -> bool:
        ""
        return self.fit_issue is None

    @property
    def measured(self) -> str:
        ""
        return _measured(self.system, self.user)


def _measured(system: str, user: str) -> str:
    ""
    return system + "\n" + user


#
_MIN_FENCE = 3

_BACKTICK_RUN = re.compile(r"`+")


def _fence_for(content: str) -> str:
    ""
    runs = (len(run.group()) for run in _BACKTICK_RUN.finditer(content))
    widest = max(runs, default=0)
    return "`" * max(_MIN_FENCE, widest + 1)


def _render_target_content(target: str, content: str) -> str:
    ""
    body = content if content.endswith("\n") else content + "\n"
    fence = _fence_for(content)
    return (
        f"CURRENT CONTENT OF {target} (this is the file to change):\n"
        f"{fence}\n{body}{fence}"
    )


def _render_sources(sources: Sequence[dict[str, Any]]) -> str:
    ""
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
    ""
    sections: list[str] = [f"TASK ({view['task_type']}): {view['task']}"]
    #
    #
    if view["output_schema"] != PROSE:
        sections.append(f"TARGET: {view['target']}")
        if view["target_content"]:
            sections.append(
                _render_target_content(view["target"], view["target_content"])
            )
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
    ""
    if contract.output_schema not in _REPLY_INSTRUCTIONS:
        raise UnsupportedSchemaError(
            f"output_schema {contract.output_schema!r} has no reply instruction "
            f"and no parser; only {WHOLE_FILE!r}, {PROSE!r} and "
            f"{MEDIA_ARTIFACT!r} are implemented. Refused before dispatch "
            f"rather than after it."
        )
    bundle = bundle_for(contract.kind.use_case.name, contract.target, adapters)
    system = bundle.text if bundle is not None else ""
    user = render_user_message(contract.worker_view(), retry)
    tokens = estimate(_measured(system, user))
    #
    #
    #
    issue = (
        None
        if contract.is_session
        else check_prompt_fits(
            tokens,
            contract.max_input_tokens,
            counted_by=counted_by,
        )
    )
    return WorkerPrompt(
        system=system,
        user=user,
        bundle=bundle,
        tokens=tokens,
        counted_by=counted_by,
        fit_issue=issue,
    )
