"""``RUN_APPENDS``: the file exists, the door produced it, and the step only appended.

A step that appends to a file another step created (``7-crash.sh`` onto step
6's ``srv1-moe-slots.tsv``) declares it under ``# RUN_APPENDS:``. The first cut
parsed the name and guarded nothing: a step whose only declaration was
``RUN_APPENDS`` was admitted over a legacy file (no ``run_id``), truncated it,
and the door exited 0 — the write-once-on-recorded-history rule the
``RUN_REWRITES`` refusal exists for did not reach this directive.

So gate 5 (``05-envelope.py``) holds an appended file to the ``RUN_REWRITES``
rule minus the move: it must exist, and its ``### START`` must carry a
``run_id`` a step of this campaign minted (a legacy file, or no file, is exit
2 and the step does not start). And gate 8 (``08-parse.py``) checks that the
bytes there before the step are still the file's prefix afterwards, and that
something followed them: a step that rewrote the file, or appended nothing,
is exit 1 naming it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

LEGACY_START = (
    f"### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
    "pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600\n"
    f"srv1\tprobe\tCONFIG\timg=sha256:{onedoor.LOCAL_ID_HEX}\n"
)
OTHER = Scenario("alpha", "1-other.sh")
PROBE = Scenario("alpha", "2-probe.sh")


def appender(env_file: Path) -> str:
    """A step that appends one door-shaped block to ``probe.tsv`` with ``>>``."""
    return (
        "#!/usr/bin/env bash\n"
        "# RUN_APPENDS: probe.tsv\n"
        "set -euo pipefail\n"
        '[ -n "${RUN_ID:-}" ] || { echo "probe: RUN_ID is unset; start me '
        'through python -m mcgyvr.serving.run" >&2; exit 2; }\n'
        f"printf 'RUN_ID=%s\\n' \"$RUN_ID\" > '{env_file}'\n"
        "{\n"
        f"printf '### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 "
        "pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw "
        'cpu_max_mhz=4600 ram_mt_s=3600 run_id=%s\\n\' "$RUN_ID"\n'
        "printf '### ROUND id=%s product_sha256=%s\\n' "
        '"${RUN_ROUND:-}" "${RUN_PRODUCT_SHA256:-}"\n'
        f"printf '%s\\tprobe\\tCRASH\\timg=sha256:{onedoor.LOCAL_ID_HEX}\\tn=2\\n' "
        '"${RUN_HOST:-nohost}"\n'
        f"printf '### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 "
        "pl2_uw=120000000 cpu_max_mhz=4600 ram_mt_s=3600 run_id=%s\\n' "
        '"$RUN_ID"\n'
        '} >> "${RUN_OUT_DIR:?}/probe.tsv"\n'
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    # Step `other` creates probe.tsv through the door; step `probe` appends.
    onedoor.add_step(
        repo, "alpha", "1-other.sh", onedoor.probe_step(tmp_path / "e-other")
    )
    return repo


def _created_by_the_door(root: Path) -> tuple[Path, str]:
    first = onedoor.door(root, OTHER)
    assert first.returncode == 0, (first.stdout, first.stderr)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    return artifact, artifact.read_text(encoding="utf-8")


def test_a_legacy_file_with_no_run_id_is_refused_and_untouched(
    root: Path, tmp_path: Path
) -> None:
    onedoor.add_step(root, "alpha", "2-probe.sh", appender(tmp_path / "e"))
    out_dir = onedoor.envelope(root, "alpha")
    out_dir.mkdir(parents=True)
    (out_dir / "probe.tsv").write_text(LEGACY_START, encoding="utf-8")
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert (out_dir / "probe.tsv").read_text(encoding="utf-8") == LEGACY_START
    assert not (tmp_path / "e").exists(), "the step ran over a file nobody claimed"


def test_a_file_that_is_not_there_cannot_be_appended_to(
    root: Path, tmp_path: Path
) -> None:
    onedoor.add_step(root, "alpha", "2-probe.sh", appender(tmp_path / "e"))
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists()


def test_a_step_that_appended_is_green_and_the_earlier_bytes_lead(
    root: Path, tmp_path: Path
) -> None:
    onedoor.add_step(root, "alpha", "2-probe.sh", appender(tmp_path / "e"))
    artifact, created = _created_by_the_door(root)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    text = artifact.read_text(encoding="utf-8")
    assert text.startswith(created), (
        "the appender's file does not begin with step other's bytes"
    )
    assert f"run_id={onedoor.read_env_file(tmp_path / 'e')['RUN_ID']}" in text


def test_a_step_that_rewrote_the_file_is_exit_1_and_named(
    root: Path, tmp_path: Path
) -> None:
    # probe_step writes with `>`: the step truncates what it declared it appends to.
    onedoor.add_step(
        root,
        "alpha",
        "2-probe.sh",
        onedoor.probe_step(tmp_path / "e", directive="RUN_APPENDS"),
    )
    artifact, created = _created_by_the_door(root)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert not artifact.read_text(encoding="utf-8").startswith(created)


def test_a_step_that_appended_nothing_is_not_green(root: Path, tmp_path: Path) -> None:
    body = appender(tmp_path / "e").replace("{\n", "exit 0\n{\n", 1)
    onedoor.add_step(root, "alpha", "2-probe.sh", body)
    artifact, created = _created_by_the_door(root)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert artifact.read_text(encoding="utf-8") == created
