"""The bundle and the assembled prompt.

Three properties carry the weight here. The shipped Python bundle must *be* the
artifact CLM-0004 measured, or the numbers describe a different file. The size
ceiling must be enforced by the loader rather than by a comment, since the
measurement says an oversized bundle degrades the worker it is meant to help.
And the assembled prompt must be reachable only through
:meth:`Contract.worker_view`, because #94's guarantee is structural or it is
nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.preflight import ESTIMATE_RESERVE, TokenCount
from mcgyvr.worker.bundle import (
    MAX_BUNDLE_BYTES,
    BundleMissingError,
    BundleTooLargeError,
    bundle_for,
    load_bundle,
)
from mcgyvr.worker.prompt import build_prompt, render_user_message

REPO = Path(__file__).resolve().parent.parent
MEASURED_C2 = (
    REPO
    / "records"
    / "evidence"
    / "local-ai-2026-08-02"
    / "data"
    / "context_exp"
    / "bundles"
    / "c2.md"
)

PY_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
interface: "def fetch(url: str, retries: int = 3) -> bytes"
deps:
  - path: src/pkg/clock.py
    signature: "def sleep(seconds: float) -> None"
    note: Use for the backoff delay.
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
risk: high
scope:
  allow: ["src/**/*.py"]
"""

JS_CONTRACT = """
id: fetch-retry-js
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.ts
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["npm test"]
scope:
  allow: ["src/**/*.ts"]
"""


def contract(text: str) -> Contract:
    return loads(text)


# --- the bundle is the measured artifact -----------------------------------


def test_shipped_python_bundle_is_byte_identical_to_the_measured_one() -> None:
    """A reworded bundle is an unmeasured one, whatever it says in the record."""
    shipped = load_bundle("python")
    assert shipped.text.encode("utf-8") == MEASURED_C2.read_bytes()


def test_the_python_bundle_is_marked_measured_and_the_js_one_is_not() -> None:
    """CLM-0004 covers one language; the flag is how a caller can tell."""
    assert load_bundle("python").measured is True
    assert load_bundle("js/ts").measured is False


def test_the_js_bundle_says_it_is_unmeasured_in_the_file_but_not_in_the_prompt() -> (
    None
):
    """The caveat travels with the file; it is not spent on the worker.

    #25 put the marker in the bundle's text so the caveat could not be lost by
    reading the file alone. #144 found what that cost: the loader was sending
    those 162 bytes to the model as the opening of its system prompt, and
    charging them against the ceiling. The caveat still has to be in the file —
    that half was right — but it is provenance, so it stops at the loader.
    """
    raw = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "mcgyvr"
        / "prompts"
        / "javascript.md"
    ).read_text(encoding="utf-8")
    assert "UNMEASURED" in raw
    assert "UNMEASURED" not in load_bundle("js/ts").text


# --- the ceiling is enforced, not documented -------------------------------


@pytest.mark.parametrize("language", ["python", "js/ts"])
def test_shipped_bundles_are_within_the_measured_ceiling(language: str) -> None:
    assert load_bundle(language).size_bytes <= MAX_BUNDLE_BYTES


def test_an_oversized_bundle_is_refused_by_the_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 8 KB condition measured *worse*. Loading one must fail loudly."""
    monkeypatch.setattr(
        "mcgyvr.worker.bundle._read", lambda _f: "x" * (MAX_BUNDLE_BYTES + 1)
    )
    with pytest.raises(BundleTooLargeError) as caught:
        load_bundle("python")
    assert caught.value.size == MAX_BUNDLE_BYTES + 1
    assert str(MAX_BUNDLE_BYTES) in str(caught.value)


def test_a_bundle_exactly_at_the_ceiling_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limit is a ceiling, not a strict inequality — an off-by-one here
    would silently reject a bundle sized deliberately to the cap."""
    monkeypatch.setattr("mcgyvr.worker.bundle._read", lambda _f: "x" * MAX_BUNDLE_BYTES)
    assert load_bundle("python").size_bytes == MAX_BUNDLE_BYTES


def test_an_unregistered_language_raises_rather_than_substituting() -> None:
    with pytest.raises(BundleMissingError):
        load_bundle("rust")


# --- selection reuses the gate's ownership rules ---------------------------


def test_bundle_is_selected_by_the_adapter_that_owns_the_target() -> None:
    assert bundle_for("src/pkg/fetch.py").language == "python"  # type: ignore[union-attr]
    assert bundle_for("src/pkg/fetch.ts").language == "js/ts"  # type: ignore[union-attr]


def test_a_target_no_adapter_owns_gets_no_bundle() -> None:
    """None is a real answer: another language's standards are worse than none."""
    assert bundle_for("README.md") is None
    assert bundle_for("main.go") is None


def test_a_custom_adapter_set_is_honoured() -> None:
    """The seam exists so a caller can restrict the languages in play."""
    from mcgyvr.gate.adapters import JavaScriptAdapter

    adapters: list[LanguageAdapter] = [JavaScriptAdapter()]
    assert bundle_for("src/pkg/fetch.py", adapters) is None


# --- the worker-view boundary ----------------------------------------------


def test_orchestrator_only_fields_never_reach_the_prompt() -> None:
    """#94, held structurally: risk, acceptance, verification and limits are
    how the orchestrator judges the work, and a worker that could read them
    could argue with them."""
    built = build_prompt(contract(PY_CONTRACT))
    whole = built.system + built.user
    assert "high" not in whole  # risk
    assert "pytest -q" not in whole  # acceptance
    assert "gate_only" not in whole  # verification policy


def test_the_prompt_carries_the_worker_facing_fields() -> None:
    built = build_prompt(contract(PY_CONTRACT))
    assert "Add retry with backoff" in built.user
    assert "src/pkg/fetch.py" in built.user
    assert "def fetch(url: str, retries: int = 3) -> bytes" in built.user
    assert "src/pkg/clock.py" in built.user
    assert "Use for the backoff delay." in built.user
    assert "The retry policy is not stated anywhere in the repo." in built.user


def test_the_input_budget_is_spent_not_shown() -> None:
    """max_input_tokens is worker-facing on the schema but is a budget the
    orchestrator enforces, not an instruction a model can act on."""
    view = contract(PY_CONTRACT).worker_view()
    assert "max_input_tokens" not in render_user_message(view)


def test_the_contracts_identity_is_carried_but_not_rendered() -> None:
    """`id` is in the view — it says which contract the view is of — and is a
    join key for records and telemetry, which is not something a model can act
    on. Being in the view and being in the prompt are different claims."""
    view = contract(PY_CONTRACT).worker_view()
    assert view["id"] == "fetch-retry"
    assert "fetch-retry" not in render_user_message(view)


def test_optional_sections_are_omitted_when_empty() -> None:
    built = build_prompt(contract(JS_CONTRACT))
    assert "INTERFACE" not in built.user
    assert "DEPENDENCIES" not in built.user


# --- the target's current content (#150) -----------------------------------

FIXABLE = """
id: factorial-base-case
task_type: bug_fix
task: The base case only stops at 1, so factorial(0) never terminates.
target: solution.ts
target_content: |
  export function factorial(n: number): number {
    if (n === 1) {
      return 1;
    }
    return n * factorial(n - 1);
  }
stop_conditions:
  - The largest n that must be supported is not stated.
acceptance: ["node accept.mjs"]
scope:
  allow: ["solution.ts"]
"""


def test_the_content_section_names_the_file_and_says_it_is_the_one_to_change() -> None:
    """A worker shown a file and told to return "the complete new content of
    solution.ts" must not have to infer the two are the same file."""
    built = build_prompt(contract(FIXABLE))
    header = "CURRENT CONTENT OF solution.ts (this is the file to change):"
    assert header in built.user
    assert "solution.ts" in built.user.split("OUTPUT:")[1]


def test_the_content_reaches_the_prompt_verbatim() -> None:
    built = build_prompt(contract(FIXABLE))
    assert "return n * factorial(n - 1);" in built.user
    assert contract(FIXABLE).target_content in built.user


def test_the_content_is_absent_from_the_prompt_when_the_contract_states_none() -> None:
    """Nothing renders an empty section, and nothing invents a placeholder: a
    contract for a file that does not exist yet says nothing about its content."""
    built = build_prompt(contract(JS_CONTRACT))
    assert "CURRENT CONTENT" not in built.user


def test_the_content_reaches_the_prompt_only_through_the_worker_view() -> None:
    """#94's property has to survive a field being added to the split.

    Rendering off ``contract.target_content`` would work and would cost the
    guarantee, so this drives the renderer with a view the content was removed
    from — the only way it could still appear is a second accessor.
    """
    view = contract(FIXABLE).worker_view()
    view["target_content"] = ""
    assert "factorial(n - 1)" not in render_user_message(view)


def test_a_fence_inside_the_content_does_not_end_the_block() -> None:
    """CommonMark closes a fence on the first line of at least as many
    backticks. A file containing one — a docstring, a markdown template — would
    otherwise end its own block and hand the worker a truncated target."""
    fenced = FIXABLE.replace(
        "target_content: |\n",
        'target_content: "const readme = `x`;\\n```\\nnested\\n```\\n"\n',
    ).replace(
        """  export function factorial(n: number): number {
    if (n === 1) {
      return 1;
    }
    return n * factorial(n - 1);
  }
""",
        "",
    )
    built = build_prompt(contract(fenced))
    body = built.user.split("CURRENT CONTENT OF solution.ts")[1]
    opening = body.split("\n")[1]
    assert opening.startswith("````")  # wider than the ``` inside
    assert "nested" in built.user
    assert built.user.count(opening) == 2  # opened and closed, exactly once each


def test_content_that_busts_the_ceiling_is_a_preflight_issue() -> None:
    """The content is charged against `max_input_tokens` like everything else,
    so a target too large to send fails at the contract level rather than being
    truncated into a dispatch."""
    small = contract(FIXABLE + "context:\n  max_input_tokens: 4096\n")
    assert build_prompt(small).fits

    huge = contract(
        FIXABLE.replace(
            "  export function factorial",
            "  // " + "padding " * 4000 + "\n  export function factorial",
        )
    )
    built = build_prompt(huge)
    assert not built.fits
    assert built.fit_issue is not None
    assert built.fit_issue.reason == "prompt-too-large"
    assert "padding" in built.user  # assembled, so the caller can say what did not fit


def test_the_reply_instruction_names_the_target_and_the_shape() -> None:
    """The prompt's instruction and the parser are two halves of one protocol."""
    built = build_prompt(contract(PY_CONTRACT))
    assert "one fenced code block" in built.user
    assert "src/pkg/fetch.py" in built.user.split("OUTPUT:")[1]


# --- the system prompt is the bundle ---------------------------------------


def test_the_bundle_is_the_system_message_and_the_contract_the_user_one() -> None:
    """CLM-0004 varied only the system prompt; this is that shape reproduced."""
    built = build_prompt(contract(PY_CONTRACT))
    assert built.bundle is not None
    assert built.system == built.bundle.text
    assert "senior Python engineer" in built.system
    assert "Add retry with backoff" not in built.system


def test_an_unowned_target_dispatches_with_no_system_prompt() -> None:
    """The c0 condition — worst of the four measured, but named rather than
    faked with another language's bundle."""
    built = build_prompt(contract(JS_CONTRACT.replace(".ts", ".go")))
    assert built.bundle is None
    assert built.system == ""


# --- the fit check, check_prompt_fits' first production caller -------------


def test_a_prompt_inside_the_ceiling_reports_no_issue() -> None:
    built = build_prompt(contract(PY_CONTRACT))
    assert built.fits
    assert built.fit_issue is None
    assert built.counted_by is TokenCount.ESTIMATE


def test_a_prompt_over_the_ceiling_is_an_issue_not_an_exception() -> None:
    """A prompt that does not fit is an orchestration error, and the caller
    still needs the assembled prompt in order to report what did not fit."""
    tight = contract(
        PY_CONTRACT
        + "context:\n  max_input_tokens: 64\nlimits:\n  max_output_tokens: 32\n"
    )
    built = build_prompt(tight)
    assert not built.fits
    assert built.fit_issue is not None
    assert built.fit_issue.reason == "prompt-too-large"
    assert built.user  # still assembled


def test_the_estimate_seam_is_injectable_and_the_count_says_which_kind() -> None:
    """CLM-0011's reserve applies to a proxy count and not to a real one, so a
    caller with a tokenizer must be able to say so and stop paying it."""
    huge = 10_000
    tight = contract(PY_CONTRACT + "context:\n  max_input_tokens: 12000\n")

    proxy = build_prompt(tight, estimate=lambda _t: huge)
    assert proxy.tokens == huge
    assert not proxy.fits  # 10000 * 1.32 = 13200 > 12000

    exact = build_prompt(
        tight, estimate=lambda _t: huge, counted_by=TokenCount.TOKENIZER
    )
    assert exact.fits  # 10000 counted exactly, nothing reserved
    assert exact.counted_by is TokenCount.TOKENIZER
    assert ESTIMATE_RESERVE > 0  # the reserve the exact count opted out of


def test_the_estimate_counts_both_messages() -> None:
    """A budget that ignored the system prompt would under-count by the whole
    bundle — about 500 tokens of the 4096 default."""
    seen: list[str] = []

    def recording(text: str) -> int:
        seen.append(text)
        return 10

    built = build_prompt(contract(PY_CONTRACT), estimate=recording)
    assert len(seen) == 1
    assert built.system in seen[0]
    assert built.user in seen[0]
