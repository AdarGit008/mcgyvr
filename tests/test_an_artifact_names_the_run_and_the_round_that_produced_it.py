"""Gate 6: an artifact says which run made it, and under which product round.

``srv1-vllm-arms.tsv`` opens with ``### WORKLOAD``, ``### START`` and ``### RIG``
(``records/evidence/2026-09-02-srv1-kernel-arms/srv1-vllm-arms.tsv:1-3``) and
nothing in it says which invocation produced it or which revision of the
product was checked out when it did. A file produced through the door carries
both: ``### START ... run_id=<RUN_ID>`` (from ``start_stamp``) and a
``### ROUND id=<round> product_sha256=<hex>`` stamp (from ``round_stamp``, new
in ``_common.sh``, fed by the two values gate 1 exported as ``RUN_ROUND`` and
``RUN_PRODUCT_SHA256``).

The parser holds the pair together: ``rows.read`` exposes ``sweep.round`` and
raises when a ``### START`` carries ``run_id=`` but no ``### ROUND`` follows —
a door-produced file with no round is a broken emitter, not an old file. Files
without ``run_id=`` are the legacy shape and parse exactly as before; their
``round`` is empty. A file with ``run_id=`` is also held to the stamp rules at
read time (a loose token in ``### END`` is a parse error, not a truncation),
which is what gate 8 relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor

LEGACY = (
    onedoor.REPO
    / "records"
    / "evidence"
    / "2026-09-02-srv1-kernel-arms"
    / "srv1-vllm-arms.tsv"
)

STAMPED_STEP = (
    "#!/usr/bin/env bash\n"
    "# RUN_ARTIFACTS: stamped.tsv\n"
    "set -euo pipefail\n"
    '[ -n "${RUN_ID:-}" ] || { echo "stamped: RUN_ID is unset; start me through '
    'tools/runs/run.sh" >&2; exit 2; }\n'
    '. "${RUN_REPO:?}/tools/runs/_common.sh"\n'
    "{\n"
    "microbench_stamp\n"
    "start_stamp\n"
    "round_stamp\n"
    "rig_stamp\n"
    f"row probe CONFIG img=sha256:{onedoor.LOCAL_ID_HEX}\n"
    "end_stamp\n"
    '} > "${RUN_OUT_DIR:?}/stamped.tsv"\n'
)


def test_a_step_run_through_the_door_stamps_run_id_and_round(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-stamped.sh", STAMPED_STEP)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs)
    result = onedoor.door(root, ["alpha", "stamped", "--host", "srv1"], env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    artifact = onedoor.envelope(root, "alpha") / "stamped.tsv"
    assert artifact.is_file(), onedoor.written_under_records(root)
    rows = onedoor.rows_module()
    sweep = rows.read(artifact)
    start = sweep.stamp("START")
    assert start.get("run_id", "").startswith("2026-09-02-alpha-stamped"), start
    assert start.get("pl1_source") == "constraint_0_power_limit_uw", start
    assert sweep.round == {
        "id": onedoor.ROUND_ID,
        "product_sha256": onedoor.PRODUCT_SHA256,
    }, sweep.stamp("ROUND")
    names = [line.split()[1] for _, line in sweep.markers]
    assert names.index("START") < names.index("ROUND") < names.index("END"), names
    assert sweep.of_kind("CONFIG")[0].host == "srv1"


def _write(path: Path, *lines: str) -> Path:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


START = (
    f"### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
    "pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600"
)
END = (
    f"### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
    "cpu_max_mhz=4600 ram_mt_s=3600"
)
ROW = f"srv1\tprobe\tCONFIG\timg=sha256:{onedoor.LOCAL_ID_HEX}"


def test_a_run_id_with_no_round_is_a_parse_error(tmp_path: Path) -> None:
    rows = onedoor.rows_module()
    path = _write(tmp_path / "noround.tsv", f"{START} run_id=r-x", ROW, END)
    with pytest.raises(ValueError, match="ROUND"):
        rows.read(path)


def test_a_run_id_with_a_round_reads_back_as_sweep_round(tmp_path: Path) -> None:
    rows = onedoor.rows_module()
    path = _write(
        tmp_path / "round.tsv",
        f"{START} run_id=r-x",
        f"### ROUND id={onedoor.ROUND_ID} product_sha256={onedoor.PRODUCT_SHA256}",
        ROW,
        END,
    )
    sweep = rows.read(path)
    assert sweep.round == {
        "id": onedoor.ROUND_ID,
        "product_sha256": onedoor.PRODUCT_SHA256,
    }
    assert sweep.stamp("START")["run_id"] == "r-x"


def test_a_door_produced_file_is_held_to_the_stamp_rules_at_read(
    tmp_path: Path,
) -> None:
    """``srv1-locktest-ling-60min.tsv:1``'s defect — ``uptime_since=2026-09-01
    08:11:08`` — on a file that claims a run id."""
    rows = onedoor.rows_module()
    path = _write(
        tmp_path / "loose.tsv",
        f"{START} run_id=r-x",
        f"### ROUND id={onedoor.ROUND_ID} product_sha256={onedoor.PRODUCT_SHA256}",
        ROW,
        "### END uptime_since=2026-09-01 08:11:08Z pl1_uw=95000000",
    )
    with pytest.raises(ValueError, match="not key=value"):
        rows.read(path)


def test_a_legacy_artifact_parses_as_before_with_an_empty_round() -> None:
    rows = onedoor.rows_module()
    assert LEGACY.is_file()
    sweep = rows.read(LEGACY)
    assert "run_id" not in sweep.stamp("START")
    assert sweep.round == {}
    assert len(sweep.levels()) == 6
    assert sweep.stamp("WORKLOAD")["digest"] == "2f2bb7932a0b660653def819"
