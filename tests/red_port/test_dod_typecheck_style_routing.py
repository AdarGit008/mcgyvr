"""S13 — the type-check branch must route STYLE findings to observations, not the
verdict.

The adapter branch routes every finding through one split — a ``style`` check
lands in ``observations`` and is reported without rejecting, everything else
lands in ``findings`` and rejects. The type-check branch extends ``findings``
unconditionally, so a style finding it produced would reject the change instead
of being reported as a note. The seam must route the two axes the same way on
both branches, or a style finding's meaning depends on which rung produced it.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.gate import ChangeSet, Finding, Gate
from tests.red_port.conftest import git

GOOD = """def fetch(url):\n    return url\n"""


class _StyleOnlyTypeCheck:
    """A type-check rung that produced one style finding and no verdict.

    Stands in for a checker whose output is demoted to ``style``, so the routing
    of that finding is what is under test, not how a checker produced it.
    """

    def run(self, changeset: ChangeSet) -> list[Finding]:
        return [Finding(check="style", path="src/pkg/fetch.py", message="a note")]


def _worker_wrote(repo: Path) -> ChangeSet:
    (repo / "src" / "pkg" / "fetch.py").write_text(GOOD, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def test_a_style_finding_from_the_typecheck_rung_is_observed_not_rejecting(
    repo: Path,
) -> None:
    """One split on both branches: style is said out loud, never fatal."""
    changed = _worker_wrote(repo)

    result = Gate().run(changed, typecheck=_StyleOnlyTypeCheck())  # type: ignore[arg-type]

    assert result.accepted, (
        f"a style finding from the type-check rung rejected the change: "
        f"{result.findings}"
    )
    assert not result.findings, (
        f"the style finding was folded into the verdict: {result.findings}"
    )
    assert any(f.check == "style" for f in result.observations), (
        "the style finding never reached observations, so it was neither "
        f"reported nor kept outside the verdict: {result.observations}"
    )
