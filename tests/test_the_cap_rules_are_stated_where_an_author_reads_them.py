"""The cap rules are stated where an author reads them, and nothing older is.

Owner decision (2026-10-14, e2e run 3 T1) replaced the automatic reply cap
with a cap model decided by task type: model-written `code` states its cap and
is held to its unit's ceiling, `chat` and `agent` are a raw connection with no
limits. The words an author acts on have to say the same thing, or the next
contract is written to the old rule:

* the empty-reply refusal says to raise the contract's cap within the unit's
  ceiling — no longer to leave the cap unset so it is sized from the target,
  nor that a unit's ``output_tokens`` bounds or replaces it;
* the field docs of ``limits.max_output_tokens``, ``units.output_tokens`` and
  ``units.window``, and so the rendered skill and setup reference;
* the shipped example `code` contract states a cap.
"""

from __future__ import annotations

from mcgyvr.config import UNIT_FIELDS
from mcgyvr.contract import LIMITS_FIELDS, loads
from mcgyvr.docgen import EXAMPLES
from mcgyvr.local_pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.worker.reply import empty_at_cap
from tests._paths import REPO

#: What the automatic cap and the replacing unit number were said in.
RETIRED = (
    "sized from the target",
    "sizes it from the target",
    "bounds or replaces",
    "replaces a cap",
    "reasoning allowance",
)


def _doc(fields: tuple, name: str) -> str:  # type: ignore[type-arg]
    return str(next(field.doc for field in fields if field.name == name))


def test_the_empty_reply_refusal_says_raise_the_cap_within_the_ceiling() -> None:
    reply = Completion(
        text="",
        stop_reason=StopReason.TRUNCATED,
        raw_stop_reason="length",
        model="m",
        source="s",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        output_tokens=1024,
        latency_s=0.0,
    )
    refused = empty_at_cap(reply)
    assert refused is not None
    said = str(refused)
    assert "limits.max_output_tokens" in said, said
    assert "within the unit's ceiling" in said, said
    for retired in RETIRED:
        assert retired not in said, (retired, said)


def test_the_field_docs_state_the_cap_model() -> None:
    cap = _doc(LIMITS_FIELDS, "max_output_tokens")
    assert "`mcgyvr run` refuses" in cap, cap
    assert "raw connection" in cap, cap
    assert "ceiling" in cap, cap
    room = _doc(UNIT_FIELDS, "output_tokens")
    assert "ceiling" in room and "never replaces" in room, room
    window = _doc(UNIT_FIELDS, "window")
    assert "setup" in window and "ceiling" in window, window
    for doc in (cap, room, window):
        for retired in RETIRED:
            assert retired not in doc, (retired, doc)


def test_the_example_code_contract_states_a_cap() -> None:
    assert loads(EXAMPLES["code"]).limits.max_output_tokens is not None


def test_the_rendered_documents_carry_no_retired_rule() -> None:
    for path in (
        REPO / "skills" / "mcgyvr" / "SKILL.md",
        REPO / "skills" / "mcgyvr" / "SETUP.md",
        REPO / "skills" / "mcgyvr" / "references" / "examples.md",
    ):
        text = path.read_text(encoding="utf-8")
        for retired in RETIRED:
            assert retired not in text, (path.name, retired)
