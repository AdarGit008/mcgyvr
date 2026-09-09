"""RED tests: the skill an agent reads to author a contract stops explaining
mcgyvr's local model ladder (plan v4, actions 19-26, ruled 2026-09-09).

The frontmatter `description` is in every session's context whether or not
the skill is invoked, so it is the highest-value line to stop naming the
ladder from (19). `limits.max_output_tokens` keeps its one sentence on what
the work is worth and drops the sentence about what a backend needs and
about `ladder.tiers.*.output_tokens` overriding it -- deleted, not reworded;
the override itself still lives in code, at gate/preflight.py:376-378 and
config.py:365 (20). `limits.max_window_fraction` stops saying `rung` (21).
`verification.policy` names a fresh-context reviewer without naming
`verifier` as a rung (22). `task_type`, and the four other rows a reader
meets it through, state what evidence a contract must carry rather than
which family or tier may start the work (23). Every `outcome` value the
result file can carry is glossed -- read from `escalate.Outcome` itself,
each with the distinct remedy `escalate.disposition` already states for it,
in words that do not name the ladder; Step 4 replans from these, and the
two `reassignable=False` outcomes no different contract can move say so
and point at `skills/mcgyvr/SETUP.md` (24). Backend
words are absent from SKILL.md except a closed, three-item exception list:
`ladder_spent` (escalate.py:191), `tier: deterministic`
(telemetry.py:468, SKILL.md:339), and `` `rung` `` as the result-file field
name (result.py:42,82) (25). `rung` itself is never renamed in
`result.py` -- a second word for the same concept would be new vocabulary,
and old journal rows and tests already say `rung` (26).

Nothing here is implemented; every test below fails until the corresponding
action lands.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SKILL_MD = REPO / "skills" / "mcgyvr" / "SKILL.md"


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "frontmatter must open the file"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    assert end is not None, "frontmatter must be closed by a second ---"
    doc = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(doc, dict), "frontmatter must be a YAML mapping"
    return doc


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def _row(body: str, key: str) -> str:
    """The full Keys-table row for one top-level or nested key."""
    pattern = re.compile(rf"^\|\s*`{re.escape(key)}`\s*\|.*$", re.M)
    match = pattern.search(body)
    assert match is not None, f"no table row found for `{key}`"
    return match.group(0)


# --- action 19 --------------------------------------------------------------


def test_frontmatter_description_does_not_name_the_local_model_ladder() -> None:
    # SKILL.md:3 is the line every session carries whether or not the skill
    # is invoked, so it is the first thing to stop explaining the ladder.
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    description = str(_frontmatter(SKILL_MD).get("description", ""))
    assert "local model ladder" not in description


# --- action 20 ---------------------------------------------------------------


def test_max_output_tokens_states_worth_without_backend_or_override() -> None:
    # Keeps the one sentence on what the work is worth; loses the sentence
    # about what a backend needs and about `ladder.tiers.*.output_tokens`
    # overriding it. The override itself is unaffected -- it still lives in
    # gate/preflight.py:376-378 and is stated on config.py:365.
    row = _row(_body(SKILL_MD), "limits.max_output_tokens").lower()
    assert "worth" in row
    assert "backend" not in row
    assert not re.search(r"\bladder", row)
    assert not re.search(r"\brung", row)


# --- action 21 ----------------------------------------------------------------


def test_max_window_fraction_never_names_a_rung() -> None:
    row = _row(_body(SKILL_MD), "limits.max_window_fraction").lower()
    assert not re.search(r"\brung", row)


# --- action 22 -----------------------------------------------------------------


def test_verification_policy_names_a_reviewer_not_a_verifier() -> None:
    # `verifier` is a config lever (config.py's VERIFIER_FIELDS, the
    # `verifier.enabled`/`verifier.source` keys) as well as a rung-adjacent
    # role name; `reviewer` is the word the source already uses to describe
    # what that role does (verify.py's module docstring and `reviewer_for`).
    row = _row(_body(SKILL_MD), "verification.policy").lower()
    assert "verifier" not in row
    assert "reviewer" in row


# --- action 23 -------------------------------------------------------------------

_TASK_TYPE_ADJACENT_KEYS = (
    "task_type",
    "target",
    "target_content",
    "stop_conditions",
    "rename",
)


def test_task_type_rows_state_evidence_not_family_or_tier() -> None:
    body = _body(SKILL_MD)
    for key in _TASK_TYPE_ADJACENT_KEYS:
        row = _row(body, key).lower()
        assert not re.search(r"\btier\b", row), key
        assert not re.search(r"\bfloor\b", row), key
        assert not re.search(r"\bfamily\b", row), key
    task_type_row = _row(body, "task_type").lower()
    assert "evidence" in task_type_row


# --- action 24 --------------------------------------------------------------------


def _outcome_section(body: str) -> str:
    """The `outcome` bullet and its nested per-outcome glosses."""
    start = body.index("- `outcome`")
    end = body.index("- `attempts[]`")
    return body[start:end]


_GLOSS = re.compile(r"^  - `([a-z_]+)` — (.*(?:\n    +\S.*)*)$", re.M)


def _glosses(section: str) -> dict[str, str]:
    """Each outcome literal mapped to its gloss, continuation lines joined."""
    return {
        literal: " ".join(gloss.split()) for literal, gloss in _GLOSS.findall(section)
    }


def test_every_outcome_value_is_glossed_in_escalate_pys_own_words() -> None:
    """Every outcome the result file can carry is glossed, distinctly.

    Read from ``escalate.Outcome`` itself rather than from a hardcoded list,
    so an eighth member added there and left unglossed fails here — the
    failure action 24 exists to force ("Step 4 replans from these; an
    unglossed token cannot be replanned from"). The two literals the runner
    writes that are not ``Outcome`` members are taken from ``cli`` for the
    same reason. Each gloss must say something, and no two may say the same
    thing: a shared gloss is what let ``escalation_ceiling`` and
    ``attempt_ceiling`` sit behind one phrase that distinguished neither.
    """
    from mcgyvr import cli, escalate

    section = _outcome_section(_body(SKILL_MD))
    glosses = _glosses(section)

    literals = [member.value for member in escalate.Outcome]
    literals += [cli.DELIVERY_REFUSED, "rejected"]
    for literal in literals:
        assert literal in glosses, (
            f"`{literal}` is not glossed in SKILL.md's outcome list; an "
            "orchestrator cannot replan from a token the skill never explains"
        )
        assert len(glosses[literal]) >= 20, f"`{literal}` has an empty gloss"

    duplicated = {
        literal
        for literal in literals
        for other in literals
        if other != literal and glosses[other] == glosses[literal]
    }
    assert duplicated == set(), f"outcomes sharing one gloss: {sorted(duplicated)}"


def test_the_two_unfixable_outcomes_send_the_reader_to_setup_md() -> None:
    """``nothing_to_run`` and ``declined_throughout`` are ``reassignable=False``
    in ``escalate.disposition`` for the same reason: "moving the contract only
    relocates the same answer". Step 4 tells an agent to write a *different*
    contract when the outcome is not ``accepted``; without this the two
    outcomes no contract can move send it round that loop forever.
    """
    from mcgyvr import escalate

    body = _body(SKILL_MD)
    # ACCEPTED and LADDER_SPENT are `reassignable=False` too, but for reasons
    # that are not this one: accepted has no work left to move, and
    # ladder_spent's own remedy in escalate.py IS a narrower contract. These
    # two are the pair whose remedy is not a contract at all.
    set_aside = (escalate.Outcome.ACCEPTED, escalate.Outcome.LADDER_SPENT)
    unmovable = [
        member.value
        for member in escalate.Outcome
        if not escalate.disposition(member).reassignable and member not in set_aside
    ]
    assert set(unmovable) == {"nothing_to_run", "declined_throughout"}
    step4 = body[body.index("## Step 4") :]
    for literal in unmovable:
        assert literal in step4, (
            f"Step 4 never mentions `{literal}`, which no different contract "
            "can move; an agent that hits it rewrites contracts forever"
        )
    assert "skills/mcgyvr/SETUP.md" in step4, (
        "Step 4 must name where the remedy for those two outcomes lives"
    )


# --- action 25 -----------------------------------------------------------------

# `vram`, `gpu` and `quantiz` measure zero in SKILL.md today. They are listed
# anyway: a word-ban that only lists the words already present stops nothing
# from adding them tomorrow, which is the whole point of the list.
BACKEND_WORDS = (
    "rung",
    "ladder",
    "floor",
    "tier",
    "family",
    "backend",
    "host",
    "vram",
    "gpu",
    "quantiz",
)

# The closed exception list. Anything a backend word does that is not one of
# these three exact patterns is a leak.
_EXCEPTIONS = (
    re.compile(r"ladder_spent"),  # escalate.py:191
    re.compile(r"`tier: deterministic`"),  # telemetry.py:468, SKILL.md:339
    re.compile(r"`rung`"),  # result.py:42,82 -- the field name
)


def _scrub_exceptions(text: str) -> str:
    for pattern in _EXCEPTIONS:
        text = pattern.sub("", text)
    return text


def _backend_leaks(text: str) -> list[str]:
    scrubbed = _scrub_exceptions(text)
    return [
        word
        for word in BACKEND_WORDS
        if re.search(rf"\b{word}", scrubbed, re.IGNORECASE)
    ]


def test_skill_names_no_backend_word_outside_the_closed_exception_list() -> None:
    # Proof by construction, before trusting the scrub on the real file: a
    # bare backend word survives right next to the exact sanctioned pattern
    # that must not. A bare `"ladder" not in body` could never pass once
    # action 24 puts `ladder_spent` in the file -- this shows the exception
    # list is what makes that possible without also hiding a real leak.
    assert _backend_leaks("the `ladder_spent` outcome") == []
    assert _backend_leaks("ladder_spent, but also the ladder itself") == ["ladder"]
    assert _backend_leaks("a journal row naming `tier: deterministic`") == []
    assert _backend_leaks("`tier: deterministic`, yet still the top tier") == ["tier"]
    assert _backend_leaks("attempts[]: `rung`, `attempt`, `verdict`") == []
    assert _backend_leaks("`rung`, and also every rung tried") == ["rung"]

    leaks = _backend_leaks(SKILL_MD.read_text(encoding="utf-8"))
    assert leaks == [], f"backend words leaked outside the exception list: {leaks}"


# --- action 26 -------------------------------------------------------------------


def _field_comment(source: str, class_name: str, field: str) -> str:
    """The ``#:`` comment block attached to one dataclass field.

    Read as the lines immediately above the annotation, which is where a
    ruling about a field name has to live to be seen by whoever renames it.
    """
    lines = source.splitlines()
    header = re.compile(rf"^class {class_name}\b")
    at = next(i for i, line in enumerate(lines) if header.match(line))
    end = next(
        i for i in range(at + 1, len(lines)) if re.match(rf"^\s+{field}\s*:", lines[i])
    )
    comment: list[str] = []
    i = end - 1
    while i >= at and lines[i].strip().startswith("#:"):
        comment.insert(0, lines[i].strip().removeprefix("#:").strip())
        i -= 1
    return " ".join(comment)


def test_result_py_rules_out_a_second_name_for_rung() -> None:
    """`rung` stays the field name on both AttemptResult and RunResult.

    No rename: a second word for one concept is new vocabulary, and old
    journal rows and tests already say `rung`. The ruling is asserted where
    it has to be written to do any work — in the field's own ``#:`` comment,
    not merely somewhere in the module. A proximity search over the whole
    source passes on incidental co-occurrence of "rung" and "rename", which
    is exactly what a future editor adding a synonym would leave behind.
    """
    from mcgyvr import result

    source = inspect.getsource(result)
    classes = ((result.AttemptResult, "AttemptResult"), (result.RunResult, "RunResult"))
    for cls, name in classes:
        assert "rung" in {f.name for f in dataclasses.fields(cls)}, name
        comment = _field_comment(source, name, "rung")
        assert re.search(r"renam", comment, re.I), (
            f"{name}.rung's own comment does not rule out a rename; the "
            "ruling has to sit next to the field it protects: " + repr(comment)
        )
