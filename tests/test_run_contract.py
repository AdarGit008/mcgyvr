"""The run contract's four checks, named by ADR-0038 before the code exists.

ADR-0037 rule 1 is why this file is here rather than a paragraph: a decision
that states a property states it as a check. Rule 3 is why it is here *now* —
the resolver at ``tests/test_finding_is_a_check.py`` refuses a decision record
that names a check the suite does not hold, and it refused ADR-0038 the moment
it was written. That refusal is the mechanism working, not an obstacle to it.

Three of the four are ``xfail(strict=True)`` with a dated reason under rule 2's
grammar. They are not owed rulings — the owner has ruled — they are owed
*code*: `docs/run-contract-2026-08-22.md` is a contract and ADR-0038 is
``Proposed``. ``strict`` is what makes them a schedule rather than a wish: the
commit that implements a clause turns its check XPASS and fails the suite until
the marker comes off in the same commit.

The fourth is green, and it is the one that matters most today, because it is
the only clause of ADR-0038 that could already have been violated: D1 withdraws
ADR-0024's per-machine roles, and a role encoded in a module would have
outlived the record that created it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"

#: Names a module would plausibly use to designate a rig, if a role had ever
#: been encoded. ADR-0024 clauses 1 and 2 lived only in prose; this is the
#: check that keeps it that way now that the prose is withdrawn.
ROLE_NAMES = (
    "measurement_rig",
    "measurement_host",
    "capacity_rig",
    "capacity_host",
    "is_measurement",
    "is_capacity",
)


def _python_sources(root: Path = TOOLS) -> list[Path]:
    """Every module under ``tools/``, excluding any vendored environment."""
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if ".venv" not in path.parts and "site-packages" not in path.parts
    ]


def _bound_names(path: Path) -> set[str]:
    """Every name a module binds — assignments, functions, classes, arguments.

    Parsed rather than grepped, so a role named inside a comment or a docstring
    (where ADR-0024's roles legitimately still appear, as history) is not
    mistaken for one the code acts on.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a broken module is another test's
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def test_no_host_is_barred_from_a_cross_host_contrast() -> None:
    """ADR-0038 D1 — a machine has no role, and no module may give it one.

    ADR-0024 clauses 1 and 2 named srv2 "the measurement rig" and srv1
    "capacity", and forbade comparing rates across hosts. Those clauses were
    withdrawn on 2026-08-22 because both rigs now run one ollama build and one
    vLLM image, and because the roles forbade #329 — the cross-rig question the
    project exists to answer.

    The roles were only ever prose, and this check is what keeps them there. A
    role encoded as a name would outlive the record that created it, and a
    reader would find the behaviour without the reasoning: ADR-0026 lens 3, a
    record that states no property is worse than dead weight, applied to code.

    Names are read from the parse tree, not by grep, so ADR-0024's roles may go
    on being *described* in a docstring — as history — without being *acted on*.
    """
    offenders = {
        path.relative_to(REPO).as_posix(): sorted(found)
        for path in _python_sources()
        if (found := _bound_names(path) & set(ROLE_NAMES))
    }
    assert not offenders, (
        f"ADR-0038 D1 withdrew every per-machine role, and {len(offenders)} "
        f"module(s) bind one as a name: {offenders}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: owed — ADR-0038 D3 is decided and unimplemented. No "
        "module compares two cells' parameters, so nothing can refuse on an "
        "unremarked difference. See docs/run-contract-2026-08-22.md section 5"
    ),
)
def test_a_contrast_refuses_when_any_unremarked_parameter_differs() -> None:
    """ADR-0038 D3 — the check is unaware, and fails on any extra difference.

    Two cells are comparable when every recorded parameter is equal except the
    one under test. The check must not be taught which differences are
    harmless: the knowledge that would let it wave a driver version through is
    the knowledge under test, and a difference waved through never reaches the
    record.
    """
    contrast = REPO / "tools" / "bench" / "serving" / "contrast.py"
    assert contrast.exists(), (
        f"{contrast.relative_to(REPO)} does not exist, so no comparison is "
        "checked and every cross-cell claim is made by hand"
    )
    source = contrast.read_text(encoding="utf-8")
    assert "def compare" in source, "the module names no comparison entry point"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: owed — ADR-0038 D4 is decided and unimplemented. There is "
        "no contrast record, so an ignored difference has nowhere to live "
        "except the cell it must not touch"
    ),
)
def test_an_ignored_difference_is_named_on_the_contrast_and_not_on_the_cell() -> None:
    """ADR-0038 D4 — the ignore is a record, and the cell is immutable.

    A cell is written once and never edited: one taken up by three later
    comparisons must still say exactly what it said when it ran. So the
    declaration that a difference does not bear on a claim belongs to the
    claim, which is created at reading time, and never to the measurement.

    Ignoring is the NORMAL path for a cross-machine contrast, not the
    exception — two cells on different hosts always differ in card, driver and
    hostname — so this record is populated on essentially every such claim, and
    that standing list is the point.
    """
    schema = REPO / "tools" / "baseline" / "schema" / "record.contrast.schema.json"
    assert schema.exists(), (
        f"{schema.relative_to(REPO)} does not exist: no record type describes a "
        "comparison, what it held fixed, or what it chose to ignore"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: owed — ADR-0038 D5 is decided and unimplemented. A cell "
        "is not yet a standalone record, so there is nothing a later contrast "
        "could take up as its second arm"
    ),
)
def test_a_one_armed_cell_is_stored_and_checked_like_any_other() -> None:
    """ADR-0038 D5 — a capability question needs no contrast to be a record.

    "Can these two models co-reside on this card" answers itself. It is
    checked, stored and logged identically to an arm of a comparison, and may
    later become one arm of a comparison nobody planned — which is what makes
    contrasts a reading-time construction rather than an authoring-time one.

    The check is that a cell's record shape does not depend on how many arms
    its header declared.
    """
    contract = REPO / "docs" / "run-contract-2026-08-22.md"
    assert contract.exists(), "the contract this check enforces is not in the tree"
    cells = sorted((REPO / "records" / "evidence").glob("*/*/run.json"))
    assert cells, (
        "no cell has ever been written in the one-directory-per-cell shape the "
        "contract defines, so nothing can be taken up as a later arm"
    )


def test_canary_a_role_bound_as_a_name_is_refused(tmp_path: Path) -> None:
    """The D1 check, shown to reject — a check that cannot fail is a MARKERS table.

    ``tests/test_sink_conformance.py:11-18`` records why this canary is not
    optional: a source-string guard "confirms the thermometer was installed and
    cannot notice that nobody wrote the temperature down".
    """
    (tmp_path / "innocent.py").write_text(
        '"""A docstring naming the measurement_rig is history, not behaviour."""\n'
        "HOSTS = ('srv1', 'srv2')\n",
        encoding="utf-8",
    )
    assert not (_bound_names(tmp_path / "innocent.py") & set(ROLE_NAMES)), (
        "a role named only in a docstring must not be read as one the code acts on"
    )
    (tmp_path / "guilty.py").write_text("measurement_rig = 'srv2'\n", encoding="utf-8")
    assert _bound_names(tmp_path / "guilty.py") & set(ROLE_NAMES), (
        "a role bound as a module-level name must be found"
    )


def test_canary_the_adr_names_every_check_in_this_file() -> None:
    """ADR-0037 rule 3 from the other side: the record and the file agree.

    The resolver proves each named check exists. This proves the file holds no
    check the record forgot to name -- a test that enforces a decision nobody
    can find from the decision is the same loss, mirrored.
    """
    adr = next((REPO / "docs" / "decisions").glob("0038-*.md")).read_text(
        encoding="utf-8"
    )
    named = set(re.findall(r"tests/test_run_contract\.py::(test_\w+)", adr))
    defined = {
        node.name
        for node in ast.parse(Path(__file__).read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and not node.name.startswith("test_canary_")
    }
    assert defined == named, (
        f"ADR-0038 names {sorted(named)}; this file defines {sorted(defined)}"
    )
