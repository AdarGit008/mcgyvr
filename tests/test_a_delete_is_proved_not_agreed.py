"""A delete is proved, or it does not happen.

tests/DELETES.tsv records each test claimed to be deletable, the claim's
kind, and the verdict tests/prove_delete.py reached. That tool measures the
expensive half -- which lines of the product each test runs. This re-measures
the cheap half on every run, so a claim cannot quietly stop being true
between the day it was proved and the day it is acted on:

- a `dead` claim's absent name is still absent from the source
- a `redundant` claim's assertions are still a subset of its keeper's
- nothing has been deleted while its verdict is `unproved`
- a proved candidate's keeper has not gone with it

The point of the file is that the second one of those is checkable at all.
The two classification passes each gave a sentence; a sentence is not a
measurement, and six tests were marked for deletion on sentences.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from tests._paths import REPO
from tests.prove_delete import where_it_would_be

LEDGER = REPO / "tests" / "DELETES.tsv"
COLUMNS = ("path", "kind", "keeper", "verdict", "evidence")
KINDS = ("dead", "redundant", "gone-redundant")
#: A claim about a test that was already deleted -- on the agreement this
#: file exists to replace, before it existed. git keeps the file, so the
#: claim is still answerable, and the count may not grow: no delete is made
#: on agreement here. Each of the two repositories has one.
ALREADY_GONE = 1
VERDICTS = ("proved", "proved-in-part", "unproved")


def claims() -> list[dict[str, str]]:
    lines = [
        line
        for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert lines, f"{LEDGER} holds no rows"
    head = tuple(lines[0].split("\t"))
    assert head == COLUMNS, f"{LEDGER} columns are {head}, expected {COLUMNS}"
    found = []
    for number, line in enumerate(lines[1:], start=2):
        field = line.split("\t")
        assert len(field) == len(COLUMNS), (
            f"{LEDGER}:{number} has {len(field)} columns, not {len(COLUMNS)}"
        )
        found.append(dict(zip(COLUMNS, field, strict=True)))
    return found


def _asserts_of(path: Path) -> set[str]:
    """Each assertion the file makes, written one way.

    Normalised through the syntax tree so that whitespace, a renamed local
    or a different quote do not make two readings of one question. This is
    the same reading tests/prove_delete.py takes.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            found.add(ast.unparse(node.test))
    return found


def test_every_claim_is_one_of_the_kinds_with_a_verdict() -> None:
    for claim in claims():
        assert claim["kind"] in KINDS, claim
        assert claim["verdict"] in VERDICTS, claim
        assert claim["evidence"].strip(), (
            f"{claim['path']} has a verdict and no evidence for it"
        )


def test_nothing_is_deleted_while_its_claim_is_unproved() -> None:
    """A test still here is a test whose claim can still be put to a
    measurement. One already gone is recorded as such and counted."""
    gone = [
        claim["path"]
        for claim in claims()
        if claim["kind"] != "gone-redundant"
        and claim["verdict"] == "unproved"
        and not (REPO / claim["path"]).exists()
    ]
    assert not gone, (
        "a test named here is gone while its claim is unproved. Either the "
        "claim was proved and the row not updated, or the test was deleted "
        f"on agreement; if the latter, say so with kind `gone-redundant`: {gone}"
    )


def test_no_further_delete_is_made_on_agreement() -> None:
    """The ratchet. One test was deleted before this file existed, on a
    sentence two readers found persuasive; under measurement its claim does
    not hold. That is recorded, and it is the only one."""
    already = [c for c in claims() if c["kind"] == "gone-redundant"]
    assert len(already) == ALREADY_GONE, (
        f"{len(already)} claims are about a test already deleted, where this "
        f"file expects {ALREADY_GONE}. Higher means another delete was made "
        "on agreement rather than on a proof."
    )
    for claim in already:
        assert not (REPO / claim["path"]).exists(), (
            f"{claim['path']} is marked as already deleted and is still here"
        )


def test_a_proved_claim_did_not_take_its_keeper_with_it() -> None:
    for claim in claims():
        if claim["kind"] != "redundant":
            continue
        keeper = REPO / claim["keeper"]
        assert keeper.exists(), (
            f"{claim['path']} is redundant with {claim['keeper']}, which is "
            "not there: the claim rests on a test that has gone"
        )


def test_a_gone_claim_can_still_be_answered_from_the_history() -> None:
    """The file is gone; git has it. The proof of a delete does not stop
    being takeable because the delete happened."""
    for claim in claims():
        if claim["kind"] != "gone-redundant":
            continue
        found = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--diff-filter=D", "--", claim["path"]],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        commit = found.stdout.strip()
        assert commit, (
            f"no commit in this history removed {claim['path']}, so its "
            "claim cannot be answered from the history. On a shallow "
            "checkout that is what a missing commit looks like: CI fetches "
            "the whole history for this job (fetch-depth: 0) so the check is "
            "taken rather than skipped."
        )
        shown = subprocess.run(
            ["git", "show", f"{commit}^:{claim['path']}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        assert shown.stdout.strip(), f"{claim['path']} comes back empty from git"
        assert commit[:9] in claim["evidence"], (
            f"the row for {claim['path']} does not name the commit its "
            f"evidence was recovered from ({commit[:9]})"
        )


def test_a_dead_claims_absent_name_is_still_absent() -> None:
    """Whether a name is absent is resolved the way an import resolves it,
    by the same function the prover uses -- imported, so there is one of it.
    A substring search would find `propose` in `propose.py` and
    `capacity.py` and call a true claim false.
    """
    for claim in claims():
        if claim["kind"] != "dead":
            continue
        found = where_it_would_be(REPO, claim["keeper"])
        assert not found, (
            f"{claim['path']} is claimed dead because {claim['keeper']} does "
            f"not exist, and it resolves to "
            f"{[str(f.relative_to(REPO)) for f in found]}"
        )


def test_a_proved_claim_has_not_rotted_since_it_was_proved() -> None:
    """A proof is only worth having if it is still true on the day the
    delete is acted on. The assertion half is cheap, so it is re-taken on
    every run; the line half is tests/prove_delete.py's to re-take.

    An `unproved` row claims nothing, so there is nothing here to hold --
    which is the state all three of this repository's claims are in.
    """
    for claim in claims():
        if not claim["verdict"].startswith("proved"):
            continue
        if claim["kind"] not in ("redundant", "gone-redundant"):
            continue
        if not (REPO / claim["path"]).exists():
            continue
        mine = _asserts_of(REPO / claim["path"])
        theirs = _asserts_of(REPO / claim["keeper"])
        alone = mine - theirs
        assert not alone, (
            f"{claim['path']} was proved redundant with {claim['keeper']}, "
            f"and now asks {len(alone)} things the keeper does not: "
            f"{sorted(alone)[:3]}. The proof has rotted; take it again."
        )


def test_the_evidence_says_what_was_measured_not_what_was_thought() -> None:
    """Every row's evidence names a count, which is what a measurement
    leaves behind. A sentence about what a reader found persuasive is the
    thing this file replaces."""
    for claim in claims():
        assert any(ch.isdigit() for ch in claim["evidence"]), (
            f"the evidence for {claim['path']} names no number, so nothing "
            f"was measured: {claim['evidence']!r}"
        )
