"""A `unified_diff` contract runs end to end, and is delivered as a whole file is.

``output_schema: unified_diff`` used to pass ``mcgyvr contract`` and then be
refused when the run built its prompt. Now the run asks the model for a diff,
applies the reply onto the target's content, and hands the gate and delivery the
whole resulting file. Driven here through the real attempt, ladder, gate and
``mcgyvr direct``; the one thing substituted is the model, at the ``dispatch``
seam the project is built on.

* A diff reply is delivered to the repository and committed, the same bytes a
  ``whole_file`` reply for the same change is delivered as.
* A diff whose context does not match, or that names another file, is a failed
  attempt — not an exception — and the next attempt is told why.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.escalate import Delivered, escalate
from mcgyvr.local_pool import source_map
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests.drives import LADDER, _driven

TARGET = "src/pkg/fetch.py"

CONTRACT = """
id: strip-url
task_type: code
task: fetch strips surrounding whitespace from the url it returns.
target: src/pkg/fetch.py
output_schema: {schema}
stop_conditions:
  - Whether to strip is not stated by the task.
acceptance: ["sh -c 'grep -q fetch src/pkg/fetch.py'"]
scope:
  allow: ["src/**"]
"""

#: The conftest repository's target, and the one change every reply makes.
BEFORE = "def fetch(url):\n    return url\n"
AFTER = "def fetch(url):\n    return url.strip()\n"

DIFF = f"""Here is the diff.

```diff
--- a/{TARGET}
+++ b/{TARGET}
@@ -1,2 +1,2 @@
 def fetch(url):
-    return url
+    return url.strip()
```
"""

WHOLE = f"```python\n{AFTER}```\n"

#: A diff read off a file that is not the one shown: its removed line is wrong.
MISMATCHED = DIFF.replace("-    return url\n", "-    return uri\n")

#: A diff of a file the contract does not name.
ELSEWHERE = DIFF.replace(TARGET, "src/pkg/other.py")


def _climb(
    repo: Path, monkeypatch: pytest.MonkeyPatch, schema: str, *replies: str
) -> tuple[Delivered, list[str]]:
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT.format(schema=schema))
    sent = _driven(monkeypatch, *replies)
    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )
    assert isinstance(outcome, Delivered), outcome
    return outcome, sent


def test_a_diff_reply_is_accepted_as_the_whole_changed_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, sent = _climb(repo, monkeypatch, "unified_diff", DIFF)

    assert outcome.rung == "local_qwen-7b"
    assert outcome.judgement.accepted is not None
    assert outcome.judgement.accepted.content == AFTER
    assert len(sent) == 1
    assert f"OUTPUT: Reply with a unified diff of {TARGET}" in sent[0]


def test_the_diff_and_the_whole_file_of_one_change_deliver_the_same_bytes(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate and delivery cannot tell the schemas apart: the same change
    reaches the same verdict as the same file."""
    by_diff, _ = _climb(repo, monkeypatch, "unified_diff", DIFF)
    by_file, _ = _climb(repo, monkeypatch, "whole_file", WHOLE)

    assert by_diff.judgement.accepted is not None
    assert by_file.judgement.accepted is not None
    assert by_diff.judgement.accepted.content == by_file.judgement.accepted.content
    assert by_diff.judgement.verdict == by_file.judgement.verdict
    assert by_diff.rung == by_file.rung


@pytest.mark.parametrize(
    ("first", "reason"),
    [
        (MISMATCHED, "diff-does-not-apply"),
        (ELSEWHERE, "diff-outside-contract"),
    ],
    ids=["context-mismatch", "another-file"],
)
def test_a_diff_that_cannot_be_applied_is_retried_with_the_reason(
    repo: Path, monkeypatch: pytest.MonkeyPatch, first: str, reason: str
) -> None:
    """The first attempt fails as an unreadable reply does; the second is told
    the parser's reason and its diff is delivered."""
    outcome, sent = _climb(repo, monkeypatch, "unified_diff", first, DIFF)

    assert outcome.judgement.accepted is not None
    assert outcome.judgement.accepted.content == AFTER
    assert len(sent) == 2
    assert reason in sent[1]
    assert reason not in sent[0]


def test_mcgyvr_direct_commits_a_diff_reply_to_the_repository(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a user reaches it: the contract file, `mcgyvr direct --commit`, and the
    repository holding the applied change in a commit of its own."""
    from mcgyvr.cli import main
    from mcgyvr.config import CONFIG_PATH_ENV

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(LADDER, encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))
    contract = tmp_path / "strip-url.yaml"
    contract.write_text(CONTRACT.format(schema="unified_diff"), encoding="utf-8")
    sent = _driven(monkeypatch, DIFF)
    assert (repo / TARGET).read_text(encoding="utf-8") == BEFORE

    with contextlib.redirect_stdout(io.StringIO()):
        code = main(
            [
                "direct",
                str(contract),
                "--repo",
                str(repo),
                "--sandbox",
                "tempdir",
                "--session",
                "s1",
                "--commit",
            ]
        )

    assert code == 0
    assert len(sent) == 1
    assert (repo / TARGET).read_text(encoding="utf-8") == AFTER
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s", "-1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip().startswith("strip-url:")
    shown = subprocess.run(
        ["git", "-C", str(repo), "show", "HEAD:" + TARGET],
        capture_output=True,
        text=True,
        check=True,
    )
    assert shown.stdout == AFTER
