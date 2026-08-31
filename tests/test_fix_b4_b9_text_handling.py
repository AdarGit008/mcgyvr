"""Text the port's writers hand to each other, and the places it was mangled.

Three defects from the 2026-08-29 pressure test, all of the same family: a piece
of code that has an idea about what text is, and a neighbour with a different
one. None of them is caught by a type, because every one of them is ``str`` on
both sides.

**B4 — a line is not what ``str.splitlines`` says it is.**
:func:`~mcgyvr.worker.scoped.apply_scoped` splices by AST line span, and AST line
numbers count the three terminators the tokenizer knows: ``\\n``, ``\\r\\n``,
``\\r``. ``str.splitlines`` counts eleven. The eight extra — ``\\x0b \\x0c \\x1c
\\x1d \\x1e \\x85 \\u2028 \\u2029`` — are all legal inside a string literal, and
one of them anywhere above the spliced node shifts every index by one: the head
loses a line and the old node's tail is resurrected under the new one. The file
still parses. That is why this is asserted as whole-file byte equality and not
as "the new body is in there" — the corrupt file contains the new body too,
followed by the old one undoing it.

**B9 — the repo's own byte convention.** mcgyvr reads and writes file content
through ``utf-8``/``surrogateescape`` on purpose, and documents it at
:mod:`mcgyvr.pending`. The writers the port added encoded with strict defaults
instead, so a single undecodable byte — arriving here the way the pressure test
says it arrives, as a ``\\udc80`` escape in a JSON reply, through
:class:`~mcgyvr.runner.Completion` and
:func:`~mcgyvr.worker.reply.parse_reply` — raised ``UnicodeEncodeError`` out of
the writer. The wire path is what is exercised rather than a hand-built string,
because the question these tests answer is whether such content can *reach* the
writers, and a literal in a test file only says what happens once it has.

The refusals are asserted as well as the successes. ``surrogateescape`` is total
over bytes that came off a disk and partial over text that came off the wire: a
lone ``\\ud800`` has no byte form at all, and the honest outcome is the module's
own named refusal rather than a codec traceback three frames up.

**Pattern D — a gate result the gate can return.** ``tidy`` was written for a
change whose only problem is formatting, and could not fire on one: the format
rung emits ``check="format"``, which lands in ``findings`` and rejects, and
``tidy`` refused every rejected change. Its own test passed by hand-building a
:class:`~mcgyvr.gate.GateResult` no :meth:`~mcgyvr.gate.Gate.run` returns. So
every gate result here comes out of a real ``Gate.run`` over a real repository —
which is the only way to state the fix, since the defect was precisely that the
constructed value and the returned one disagreed.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from mcgyvr.cleanup import tidy
from mcgyvr.consensus import best_of
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate import ChangeSet, Finding, Gate, GateResult
from mcgyvr.gate.adapter import ToolFailedError
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.pending import PendingError, stash
from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.sandbox import Sandbox
from mcgyvr.worker.reply import ParsedFile, parse_reply
from mcgyvr.worker.scoped import apply_scoped

TARGET = "src/pkg/fetch.py"

CONTRACT = f"""
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: {TARGET}
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

#: Every character ``str.splitlines`` breaks on and the Python tokenizer does
#: not. Each one is its own parametrisation because they arrive from different
#: places — a form feed from a pasted listing, a NEL from a transcoded file, a
#: line separator from JSON — and a fix that handled seven of them would look
#: exactly like a fix that handled eight.
NOT_LINE_TERMINATORS = (
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    "\u2028",
    "\u2029",
)

#: The three the tokenizer *does* count, asserted alongside so that narrowing
#: the split cannot go one step too far and stop seeing a CRLF file's lines.
LINE_TERMINATORS = ("\n", "\r\n", "\r")

#: What a worker sends back for the node being spliced. Always ``\\n``-ended
#: whatever the file it lands in uses, because ``parse_reply`` normalises line
#: endings before anything sees the content — the variable under test is the
#: source file's terminators, not the reply's.
REPLACEMENT = "def fetch(url):\n    return url.strip()\n"


def _scoped_source(separator: str, newline: str = "\n") -> tuple[str, str, str]:
    """A file with ``separator`` inside a string literal above the spliced node.

    Returned in three pieces — head, node, tail — because the assertion this
    exists for is that the merge equals head + *replacement* + tail. Building
    the expected file out of the same strings the input was built from is what
    makes "and nothing else changed" checkable rather than eyeballed.
    """
    head = (
        f'"""Fetching helpers."""{newline}'
        f"{newline}"
        f'BANNER = "top{separator}bottom"{newline}'
        f"{newline}"
        f"{newline}"
    )
    node = f"def fetch(url):{newline}    return url{newline}"
    tail = f"{newline}{newline}def host(url):{newline}    return url.lower(){newline}"
    return head, node, tail


def _reply(content: str) -> str:
    """``content`` as a worker sends it: one fenced block and nothing else."""
    return f"```python\n{content}```\n"


def _off_the_wire(escape: str) -> str:
    """File content carrying ``escape``, arrived the way the report says it does.

    ``json.loads`` accepts ``\\udXXX`` and produces the lone surrogate;
    :class:`~mcgyvr.runner.Completion` carries it as ``text``, because a
    completion is whatever the backend said; and ``parse_reply`` reads it as a
    :class:`~mcgyvr.worker.reply.ParsedFile`, because nothing in the reply
    protocol is about encodings. Three hops, no validation, and the writer is
    the first code with an opinion.
    """
    body = f'def fetch(url):\\n    return \\"{escape}\\" + url\\n'
    payload = json.loads(f'{{"content": "```python\\n{body}```\\n"}}')
    completion = Completion(
        text=str(payload["content"]),
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder",
        source="local",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.1,
    )
    parsed = parse_reply(completion.text, stop_reason=completion.stop_reason)
    assert isinstance(parsed, ParsedFile), (
        f"the reply protocol refused the surrogate before any writer saw it: {parsed}"
    )
    return parsed.content


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with one commit, so ``ChangeSet.detect`` has a base.

    Real git rather than a constructed :class:`~mcgyvr.gate.ChangeSet`: the
    whole point of the pattern-D tests is that the gate result is one the gate
    produced, and a hand-built change set is the same shortcut one level down.
    """
    work = tmp_path / "work"
    (work / "src" / "pkg").mkdir(parents=True)
    (work / "seed.py").write_text("SEED = 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    return work


@pytest.fixture
def contract() -> Contract:
    """The contract every writer here is asked to carry work for."""
    return load_contract(CONTRACT)


def _gate_over(repo: Path, content: str) -> GateResult:
    """What the real gate says about ``content`` written to the contract's target."""
    (repo / TARGET).write_text(content, encoding="utf-8")
    return Gate().run(ChangeSet.detect(repo))


# --------------------------------------------------------------------------
# B4 — the splice indexes lines the parser does not count
# --------------------------------------------------------------------------


@pytest.mark.parametrize("separator", NOT_LINE_TERMINATORS)
def test_a_character_the_tokenizer_does_not_break_on_does_not_shift_the_splice(
    separator: str,
) -> None:
    """One of these above the node, and the merge writes the wrong file.

    Byte equality against the file rebuilt from its own pieces, because every
    weaker assertion passes on the corrupt output: the new body *is* present,
    the file *does* parse, and the neighbours are *mostly* there. What is wrong
    is that a blank line above the node was eaten and the node's old body came
    back underneath its replacement, undoing the change that was asked for.
    """
    head, node, tail = _scoped_source(separator)

    merged = apply_scoped(
        source=head + node + tail, reply=_reply(REPLACEMENT), node="fetch"
    )

    assert isinstance(merged, str), f"the merge refused instead of splicing: {merged}"
    assert merged == head + REPLACEMENT + tail, (
        f"a {separator!r} inside a string literal shifted the splice: the merge is "
        f"not the file with only its named node replaced"
    )
    assert "return url.strip()" in merged, "the worker's new body did not land"
    assert "    return url\n" not in merged, (
        "the node's old body survived under its replacement, so the change was "
        "applied and then immediately undone"
    )
    ast.parse(merged)  # the corruption this rules out parses; so must the fix


@pytest.mark.parametrize("newline", LINE_TERMINATORS)
def test_the_three_terminators_the_parser_does_count_still_split_the_file(
    newline: str,
) -> None:
    """The other half of B4: narrowing the split must not narrow it to ``\\n``.

    ``ast`` line numbers are assigned after universal-newline translation, so a
    file written with CRLF or with bare CR has exactly the lines the parser
    counts, and the splice has to see the same ones. A fix that split on ``\\n``
    alone would pass every test above and corrupt every file from Windows.
    """
    head, node, tail = _scoped_source("", newline=newline)

    merged = apply_scoped(
        source=head + node + tail, reply=_reply(REPLACEMENT), node="fetch"
    )

    assert merged == head + REPLACEMENT + tail, (
        f"a file whose lines end with {newline!r} was spliced at the wrong offset"
    )


# --------------------------------------------------------------------------
# B9 — the repo's own byte convention, arriving off the wire
# --------------------------------------------------------------------------


def test_a_surrogate_escaped_reply_does_not_crash_the_cleanup(repo: Path) -> None:
    """``tidy`` is best-effort by design, and a codec error is not an effort.

    The module's own claim is that every way a cleanup can fail — an absent
    ruff, a timeout, syntax it cannot parse — comes back as the content
    untouched and the verdict undisturbed. Content it cannot even hand to the
    formatter belongs in that set: ``surrogateescape`` bytes are not valid
    UTF-8, ruff refuses to read them, and the answer is "nothing to apply", not
    an exception out of a function whose contract is that it raises none.
    """
    content = _off_the_wire("\\udc80")

    outcome = tidy(content=content, result=GateResult(), target=TARGET, repo=repo)

    assert outcome.content == content, "a cleanup that could not run rewrote the file"
    assert not outcome.cleaned, "the outcome reports a cleanup that did not happen"
    assert outcome.accepted, "a cleanup that could not run overturned the gate"


def test_the_stash_holds_a_surrogate_escaped_reply_byte_for_byte(
    repo: Path, contract: Contract, tmp_path: Path
) -> None:
    """The store's first documented property, against the bytes that motivate it.

    ``utf-8``/``surrogateescape`` is what the module says it stores through, and
    the assertion is on the bytes on disk rather than on the call returning: a
    stash that wrote a replacement character would also "not crash", and
    re-verifying bytes nobody gated is the failure the store exists to prevent.
    """
    content = _off_the_wire("\\udc80")
    store = tmp_path / "pending"

    record = stash(store=store, repo=repo, contract=contract, content=content)

    want = content.encode("utf-8", "surrogateescape")
    held = [
        path
        for path in sorted(store.rglob("*"))
        if path.is_file() and path.read_bytes() == want
    ]
    assert held, (
        "the stash does not hold the accepted bytes exactly; what was gated and "
        "what would be resumed are not the same file"
    )
    assert record.size == len(want)


def test_the_stash_reports_bytes_it_cannot_write_as_its_own_error(
    repo: Path, contract: Contract, tmp_path: Path
) -> None:
    """A lone high surrogate has no byte form, and that is a store failure.

    ``surrogateescape`` round-trips the bytes a filesystem or a decode produced
    and cannot encode a ``\\ud800`` that only ever existed as a JSON escape. The
    store is the module whose job is turning "this could not be written" into a
    named error, so a caller learns which task is unstashable rather than
    catching a codec exception from three frames down — and nothing is left
    behind in the store on the way out.
    """
    content = _off_the_wire("\\ud800")
    store = tmp_path / "pending"

    with pytest.raises(PendingError):
        stash(store=store, repo=repo, contract=contract, content=content)

    assert [path for path in store.rglob("*")] == [], (
        "a failed stash left an entry behind"
    )


def test_best_of_gates_the_bytes_it_returns(repo: Path, contract: Contract) -> None:
    """The draw the gate judged and the draw that is returned are one file.

    Asserted as the bytes in the workspace at gate time, because that is where
    a substitution would happen: ``write_text`` encodes with the platform's
    preferences and translates newlines, so the winner a caller delivers would
    not be the candidate any verdict was about.
    """
    content = _off_the_wire("\\udc80")
    seen: list[bytes] = []

    def gate(sandbox: Sandbox) -> GateResult:
        seen.append((sandbox.workspace / TARGET).read_bytes())
        return GateResult()

    result = best_of(
        repo=repo, contract=contract, sample=lambda _index: content, gate=gate, n=1
    )

    assert seen == [content.encode("utf-8", "surrogateescape")], (
        "the bytes the gate judged are not the bytes the draw was made of"
    )
    assert result.winner.content == content, "the winner is not the draw that was gated"
    assert result.winner.intact, (
        "and the digest bound to it was taken off the same surrogate-escaped "
        "bytes, so a caller carrying this pair can still tell them apart"
    )


# --------------------------------------------------------------------------
# Pattern D — the state Gate.run actually returns for a formatting problem
# --------------------------------------------------------------------------

#: Valid Python, wrong shape: ruff's formatter has an opinion about every line.
MESSY = "def fetch( url ):\n    return  url\n"

#: Misformatted *and* wrong: an unused import is a lint finding, which no
#: formatter answers, and it arrives in the same ``findings`` tuple.
MESSY_AND_BROKEN = "import  os\n\n\ndef fetch( url ):\n    return  url\n"


def test_the_gate_puts_a_formatting_problem_in_findings_and_rejects(
    repo: Path,
) -> None:
    """The state the cleanup was written for, as the gate actually returns it.

    This is the pinned fact underneath the two tests after it, and it is pinned
    separately so that a change to where the format rung files its complaint
    fails *here*, naming the cause, rather than as a cleanup that quietly stops
    firing.
    """
    result = _gate_over(repo, MESSY)

    assert not result.accepted, "a file ruff would reflow was accepted"
    assert result.observations == (), (
        "the format rung's complaint arrived as an observation, so the cleanup's "
        "bucket-only split would have been right all along"
    )
    assert [finding.check for finding in result.findings] == ["format"], (
        f"the only rejection is expected to be the format rung: {result.findings}"
    )


def test_a_change_the_gate_rejected_only_on_formatting_is_cleaned(repo: Path) -> None:
    """The lever, driven by a verdict the gate produced rather than one built here.

    Four assertions because "cleaned" has three cheap wrong answers: the bytes
    must actually change, the change must be stable, and what the code does must
    survive it. The spend is zero because that is the whole economic argument —
    a cleanup that dispatches is a retry wearing a cheaper name. The last
    assertion is the one that says the cleanup was worth doing: the same gate
    that rejected these bytes accepts the cleaned ones.

    What is *not* asserted is that the outcome calls itself accepted. The gate
    stops before its typecheck, semantic and acceptance rungs the moment
    anything rejects, so a format-only verdict means the contract's own suite
    never ran; an outcome reporting acceptance would be reporting a bar nobody
    applied.
    """
    result = _gate_over(repo, MESSY)

    first = tidy(content=MESSY, result=result, target=TARGET, repo=repo)

    assert first.cleaned, (
        "a change the gate rejected only on formatting was handed back untouched, "
        "so the next attempt spends a model on whitespace"
    )
    assert first.content != MESSY, "nothing was cleaned"
    assert "return url" in first.content, "the cleanup changed what the code does"
    assert first.tokens_spent == 0, (
        f"the cleanup spent {first.tokens_spent} tokens; a cleanup that dispatches "
        f"is a retry wearing a cheaper name"
    )
    assert not first.accepted, (
        "the cleanup claimed an acceptance the gate never gave: the acceptance and "
        "semantic rungs never ran behind the format rejection"
    )
    assert first.regate, (
        "the caller was not told the verdict is stale, so bytes the gate rejected "
        "would be carried forward on a verdict that is no longer about them"
    )

    again = tidy(content=MESSY, result=result, target=TARGET, repo=repo)
    assert again.content == first.content, "the same input cleaned to two files"

    settled = _gate_over(repo, first.content)
    assert settled.accepted, (
        "the cleaned bytes still do not pass the gate that rejected them, so the "
        "cleanup did not remove the reason for the rejection"
    )


def test_a_change_the_gate_also_rejected_on_lint_is_not_cleaned(repo: Path) -> None:
    """Correctness is rejected and never tidied, on a real mixed verdict.

    The lint and format rungs run in the same pass and both file into
    ``findings``, so one change can be rejected both for a reason a formatter
    answers and for one it does not — the case a check-name test gets wrong.
    Rewriting it would hand the next attempt a file the worker never wrote, and
    every retry note about "your change" would be about somebody else's.
    """
    result = _gate_over(repo, MESSY_AND_BROKEN)
    assert {finding.check for finding in result.findings} == {"lint", "format"}, (
        f"this content is meant to be rejected on both rungs: {result.findings}"
    )

    outcome = tidy(content=MESSY_AND_BROKEN, result=result, target=TARGET, repo=repo)

    assert not outcome.cleaned, "a change with a real finding was rewritten"
    assert outcome.content == MESSY_AND_BROKEN, (
        "a rejected change was rewritten; what the next attempt is shown must be "
        "what the worker wrote"
    )
    assert not outcome.accepted


def test_a_rung_that_could_not_say_what_it_applied_is_not_a_formatting_problem(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejection nobody explained is not one the formatter raised.

    ADR-0034's case: the lint rung's tool was there, exited, and said nothing
    readable, so the change is rejected with no finding to point at. Tidying
    that would be treating "we do not know" as "it is only whitespace" —
    rewriting the bytes under a verdict whose remaining bar was never applied,
    which is the hole the ADR exists to keep visible.
    """

    def raise_failed(*_args: object, **_kwargs: object) -> list[Finding]:
        raise ToolFailedError("ruff", 2, "ruff failed: unreadable output")

    monkeypatch.setattr(PythonAdapter, "lint", raise_failed)
    result = _gate_over(repo, MESSY)
    assert [rung.rung for rung in result.inconclusive] == ["lint"], (
        f"this run is meant to leave lint inconclusive: {result.environment_issues}"
    )

    outcome = tidy(content=MESSY, result=result, target=TARGET, repo=repo)

    assert not outcome.cleaned, "a change rejected on an unreadable rung was rewritten"
    assert outcome.content == MESSY


def test_an_accepted_change_is_still_the_ordinary_case(repo: Path) -> None:
    """The path that already worked, held against a real accepting verdict.

    ``tidy`` firing on a rejection is an addition, not a replacement: a gate
    that accepted still gets its formatting tidied, and the two entry states
    have to stay distinguishable in the outcome.
    """
    clean = "def fetch(url):\n    return url\n"
    result = _gate_over(repo, clean)
    assert result.accepted, f"a clean file was rejected: {result.findings}"

    outcome = tidy(content=clean, result=result, target=TARGET, repo=repo)

    assert outcome.accepted
    assert not outcome.cleaned, "already-formatted content was rewritten"
    assert not outcome.regate, "an untouched acceptance was reported as stale"
    assert outcome.content == clean
