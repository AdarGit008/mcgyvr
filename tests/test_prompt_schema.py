"""S11 — every output schema a contract may declare is asked for in its own shape.

A contract can declare ``output_schema: unified_diff`` as well as the default
``whole_file``. Each schema the contract field accepts has an output rule in the
user message, and the language bundle's own output rule follows it, so the
system prompt never says "return code" while the user message asks for a diff.
A ``whole_file`` contract is sent exactly what it was before: the same output
rule and the bundle byte for byte, with the standing its sweep found.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.contract import OUTPUT_SCHEMAS, SCHEMA, loads
from mcgyvr.worker.bundle import DIFF_RULE, BundleStanding, load_bundle
from mcgyvr.worker.prompt import _REPLY_INSTRUCTIONS, build_prompt

CONTRACT = """
id: fetch-retry
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
target_content: "def fetch(url):\\n    return url\\n"
output_schema: {schema}
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

#: The whole-file output rule as it was before any other schema was asked for.
WHOLE_FILE_RULE = (
    "OUTPUT: Reply with the complete new content of src/pkg/fetch.py, as one "
    "fenced code block and nothing else. Not a diff, not an excerpt, not the "
    "changed lines — the whole file as it should exist after your change."
)


def _prompt(schema: str) -> Any:
    return build_prompt(loads(CONTRACT.format(schema=schema)))


def test_every_schema_the_contract_accepts_has_an_output_rule() -> None:
    """The field's choices and the prompt's rules are the same set, so no
    contract that validates reaches a prompt with no rule for its reply."""
    (field,) = (f for f in SCHEMA if f.name == "output_schema")
    assert tuple(field.choices or ()) == OUTPUT_SCHEMAS
    assert set(_REPLY_INSTRUCTIONS) == set(OUTPUT_SCHEMAS)


def test_a_unified_diff_contract_is_asked_for_a_diff_of_its_target() -> None:
    """Built, not refused: the user message asks for one fenced diff of the
    target, with headers naming it, and nothing else."""
    prompt = _prompt("unified_diff")

    assert "OUTPUT: Reply with a unified diff of src/pkg/fetch.py" in prompt.user
    assert "```diff" in prompt.user
    assert "--- a/src/pkg/fetch.py" in prompt.user
    assert "+++ b/src/pkg/fetch.py" in prompt.user
    assert "no other file" in prompt.user
    assert WHOLE_FILE_RULE not in prompt.user
    # The current content is still shown: it is what the diff is read against.
    assert "CURRENT CONTENT OF src/pkg/fetch.py" in prompt.user


def test_the_bundle_of_a_diff_contract_asks_for_a_diff_too() -> None:
    """The bundle's output rule is the one line that changes, and the changed
    text is not the measured one, so it is not cited as measured."""
    prompt = _prompt("unified_diff")
    measured = load_bundle("python")

    assert prompt.bundle is not None
    assert DIFF_RULE in prompt.system
    assert "Return ONLY code, in a single ```python fenced block." not in prompt.system
    assert prompt.bundle.standing is BundleStanding.UNMEASURED
    # Everything but that one rule is the measured bundle's text.
    before = measured.text.splitlines()
    after = prompt.system.splitlines()
    assert len(before) == len(after)
    assert [a for a, b in zip(before, after, strict=True) if a != b] == [
        "- Return ONLY code, in a single ```python fenced block."
    ]


def test_a_whole_file_contract_is_sent_what_it_was_sent_before() -> None:
    """The default schema's prompt is unchanged: its rule, and the bundle byte
    for byte with the standing its sweep found."""
    prompt = _prompt("whole_file")
    measured = load_bundle("python")

    assert WHOLE_FILE_RULE in prompt.user
    assert "unified diff" not in prompt.user
    assert prompt.system == measured.text
    assert prompt.bundle == measured
    assert prompt.bundle is not None
    assert prompt.bundle.standing is BundleStanding.MEASURED_REDUNDANT
