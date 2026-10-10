"""A single-mode door caller declares its campaign's sibling steps.

The door's ``step`` knows no campaign folder, so a step that appends to a
sibling step's file (``# RUN_APPENDS``) and a ``--suffix`` that would mint a
run id reading as a sibling's step cannot be judged against the sibling by the
door alone. A caller declares those siblings in ``MCGYVR_DOOR_SIBLINGS``: a
JSON list of step file paths. Unset, only the current step qualifies, exactly
as if it were the only step of its campaign.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario


def _appender(env_file: Path) -> str:
    """The probe step, declared under ``RUN_APPENDS`` and appending with ``>>``."""
    body = onedoor.probe_step(env_file, directive="RUN_APPENDS")
    return body.replace('} > "$out"\n', '} >> "$out"\n')


def test_a_declared_sibling_admits_a_cross_step_append(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root, "alpha", "1-other.sh", onedoor.probe_step(tmp_path / "e-other")
    )
    onedoor.add_step(root, "alpha", "2-probe.sh", _appender(tmp_path / "e"))
    first = onedoor.door(root, Scenario("alpha", "1-other.sh"))
    assert first.returncode == 0, first.stderr

    # Without the declaration the door knows only the current step.
    refused = onedoor.door(root, Scenario("alpha", "2-probe.sh"))
    assert refused.returncode == 2, refused.stderr
    assert "names no step of campaign alpha" in refused.stderr

    sibling = root / "steps" / "alpha" / "1-other.sh"
    green = onedoor.door(
        root,
        Scenario("alpha", "2-probe.sh"),
        env_extra={"MCGYVR_DOOR_SIBLINGS": json.dumps([str(sibling)])},
    )
    assert green.returncode == 0, green.stderr


def test_a_declared_sibling_blocks_a_forged_suffix(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e1"))
    onedoor.add_step(
        root, "alpha", "2-probe-again.sh", onedoor.probe_step(tmp_path / "e2")
    )
    sibling = root / "steps" / "alpha" / "2-probe-again.sh"
    result = onedoor.door(
        root,
        Scenario("alpha", "1-probe.sh", suffix="again"),
        env_extra={"MCGYVR_DOOR_SIBLINGS": json.dumps([str(sibling)])},
    )
    assert result.returncode == 2, result.stderr
    assert "--suffix" in result.stderr and "probe-again" in result.stderr
