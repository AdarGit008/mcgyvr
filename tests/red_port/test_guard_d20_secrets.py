"""D20 — the worker's own lines are scanned, the rest are not, and nobody can turn it
off.

GREEN by design. The scan being ported over has fewer patterns and no notion of
an environment the check runs under. This file pins the four properties that make
mcgyvr's version worth keeping, and it pins them one level up from
``tests/test_secrets.py``, which builds its ``FileChange`` objects by hand.

Hand-built changes are the right way to test the patterns — they let a case say
"line 3 was added" without a repository to make it true. They are also exactly
why a port could pass every one of them while regressing: the attribution the
test asserts is the attribution the test supplied. ``added_lines`` is an input
there, so nothing in that file says the added lines were computed correctly, or
that a real diff against a real base produces them at all. So every case here
goes through a real git repository and a real ``ChangeSet.detect``.

Four statements:

* **A credential the worker wrote is a finding, on the line it wrote.** The line
  number matters: a scan that flagged the file would be unactionable and would
  also be indistinguishable from one that had stopped attributing.
* **The same value read from the environment is not.** Asserted with the *same
  secret string* on both sides, so the rule is shown to be about the shape of
  the line and not about the value having become known to the scanner.
* **A credential the worker did not touch is not the worker's.** The credential is
  in the base commit; the worker adds an unrelated line. Nothing is reported —
  which is the difference between a gate and a repository audit, and the reason
  the gate can be a hard stop at all.
* **There is no off switch.** Held two ways, because "no flag exists" is a claim
  about absence and a single assertion cannot carry it. The gate is run with
  every lever it *does* have set to its most permissive, and separately a config
  that tries to declare the check off is refused at load. A port that added a
  toggle would have to break one of the two.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigError
from mcgyvr.config import parse as parse_config
from mcgyvr.gate import Gate
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.secrets import scan_secrets
from mcgyvr.scope import Scope
from tests.red_port.conftest import git

SECRET = "s3cret-pager-password"
TARGET = Path("src") / "pkg" / "fetch.py"

PERMISSIVE_CONFIG = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
"""


def _worker_appends(repo: Path, line: str) -> ChangeSet:
    """Add one line to the target the way a worker's output would, and diff it."""
    target = repo / TARGET
    target.write_text(target.read_text() + line + "\n")
    return ChangeSet.detect(repo)


def test_a_written_credential_is_a_finding_and_an_environment_read_is_not(
    repo: Path,
) -> None:
    """One value, two lines, two verdicts — the shape is what is judged.

    The same secret text appears in both halves. That is the whole design: a
    scanner that had degraded into matching known values would flag both, and a
    scanner that had degraded into matching variable names would flag both too.
    Only one that reads *a literal bound to a credential-shaped name* separates
    them, and separating them is what makes the check usable — a gate that
    rejected every line mentioning a password would be turned off within a week,
    which is the road to having no check at all.

    The line number is asserted because attribution is the feature. A finding
    that named only the file would leave a reviewer diffing by hand.
    """
    hardcoded = _worker_appends(repo, f'password = "{SECRET}"')
    (finding,) = scan_secrets(hardcoded)

    assert finding.check == "secret"
    assert finding.path == str(TARGET), f"attributed to the wrong file: {finding.path}"
    assert finding.line == 3, f"attributed to the wrong line: {finding.line}"

    git(repo, "checkout", "--", str(TARGET))
    from_env = _worker_appends(repo, f'password = os.environ["{SECRET}"]')

    assert scan_secrets(from_env) == [], (
        "reading a credential from the environment was reported as hardcoding one"
    )


def test_a_credential_on_a_line_the_worker_did_not_touch_is_not_the_workers(
    repo: Path,
) -> None:
    """The gate judges a change, not a repository.

    The credential is committed first, so it is real, present, and matched by the
    same pattern that fired above — then the worker adds something innocuous. A
    scan that read the file rather than the diff would reject this change for a
    line that was already there before the worker was asked to do anything, and
    every attempt on this repository would fail forever for a reason no attempt
    could fix.

    The positive control is the test above: the same file, the same pattern, one
    added line, one finding. Without it, an empty result here would also be what
    a scanner that had stopped working entirely would produce.
    """
    target = repo / TARGET
    target.write_text(target.read_text() + f'api_key = "{SECRET}"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a credential that was already here")

    changeset = _worker_appends(repo, "TIMEOUT = 30")

    assert scan_secrets(changeset) == [], (
        "a pre-existing credential was charged to the worker's change"
    )


def test_the_secrets_check_cannot_be_turned_off(repo: Path) -> None:
    """Every lever the gate has, set to permit — and the change is still rejected.

    Scope allows everything, no semantic rung, no acceptance commands, no
    language adapters. Those are the four things a caller can vary, and with all
    four at their most permissive the only verdict the gate can reach is the one
    the secrets scan reached. A check that had acquired a way to be skipped would
    almost certainly acquire it as one of these, or as a config key — hence the
    second half.

    Refusing at config load is the stronger of the two, because it says an
    operator cannot even write the intention down. Asserted through the loader
    rather than by inspecting the schema, since a schema listing is a fact about
    a data structure and the refusal is a fact about what the product accepts.
    """
    changeset = _worker_appends(repo, f'client_secret = "{SECRET}"')

    result = Gate(adapters=[]).run(
        changeset, Scope.of(allow=["**"]), semantic=None, acceptance=None
    )

    assert not result.accepted, (
        "the most permissive gate there is let a credential through"
    )
    assert {f.check for f in result.findings} == {"secret"}, (
        f"rejected, but not for the secret: {result.findings}"
    )

    for attempt in ("gate:\n  secrets: false\n", "secrets:\n  enabled: false\n"):
        with pytest.raises(ConfigError):
            parse_config(PERMISSIVE_CONFIG + attempt)
