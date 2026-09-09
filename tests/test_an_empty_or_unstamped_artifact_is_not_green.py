"""A TSV that parses is not yet this run's: it must open, name its round and close.

``rows.read`` accepts an empty file (no markers, no rows) and a file with no
``###`` line at all, and gate 8 (``08-parse.py``) once called both "parse".
A step that exited 0 having written ``: > probe.tsv`` was a green run with a
zero-byte artifact; one that wrote rows and no stamps was a green run with
rows nobody could tie to a rig, a round or an invocation.

So gate 8 holds the part of every declared ``.tsv`` that this run wrote —
the whole file, or the bytes after gate 5's recorded size for a
``RUN_APPENDS`` file — to three stamps: a ``### START run_id=<RUN_ID>``, the
first of the run's own stamps; a ``### ROUND id=<RUN_ROUND>
product_sha256=<RUN_PRODUCT_SHA256>``; and a ``### END run_id=<RUN_ID>``. A
zero-byte file, or one missing any of them, is exit 1 naming the file and
the missing stamp. A ``.json`` keeps its own rule (``json.loads``) and is
never held to a stamp. ``_common.sh``'s ``end_stamp`` writes ``run_id=`` for
the same reason ``start_stamp`` does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _writes(env_file: Path, body_lines: str) -> str:
    """The probe step with its whole artifact body replaced by ``body_lines``
    (a bash block writing to ``$out``)."""
    text = onedoor.probe_step(env_file)
    head, _, _ = text.partition("{\n")
    return head + body_lines


def test_a_zero_byte_artifact_is_exit_1_and_named(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root, "alpha", "1-probe.sh", _writes(tmp_path / "e", ': > "$out"\n')
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv is empty (0 bytes" in result.stderr, result.stderr
    assert "artifact(s) parse" not in result.stdout


def test_rows_with_no_stamp_at_all_are_exit_1_naming_each_missing_stamp(
    tmp_path: Path,
) -> None:
    body = (
        "{\n"
        f"printf '%s\\tprobe\\tCONFIG\\timg=sha256:{onedoor.LOCAL_ID_HEX}\\n' "
        '"${RUN_HOST:-nohost}"\n'
        '} > "$out"\n'
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", _writes(tmp_path / "e", body))
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    for stamp in (
        "### START run_id=",
        "### ROUND id= product_sha256=",
        "### END run_id=",
    ):
        assert f"probe.tsv carries no `{stamp}` stamp of its own" in result.stderr, (
            stamp,
            result.stderr,
        )


def test_a_start_that_names_no_run_and_an_end_that_names_no_run_are_exit_1(
    tmp_path: Path,
) -> None:
    """Every stamp present, both bare: the legacy shape, written by a step
    that dropped what the door handed it."""
    body = (
        "{\n"
        f"printf '### START uptime_since={onedoor.UPTIME} pl1_uw=95000000\\n'\n"
        "printf '### ROUND id=%s product_sha256=%s\\n' "
        '"${RUN_ROUND:-}" "${RUN_PRODUCT_SHA256:-}"\n'
        f"printf '%s\\tprobe\\tCONFIG\\timg=sha256:{onedoor.LOCAL_ID_HEX}\\n' "
        '"${RUN_HOST:-nohost}"\n'
        f"printf '### END uptime_since={onedoor.UPTIME} pl1_uw=95000000\\n'\n"
        '} > "$out"\n'
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", _writes(tmp_path / "e", body))
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"### START names run_id=None and this run is run_id='{run_id}'" in (
        result.stderr
    ), result.stderr
    assert f"### END names run_id=None and this run is run_id='{run_id}'" in (
        result.stderr
    ), result.stderr


def test_an_end_that_names_no_run_is_exit_1_even_when_start_does(
    tmp_path: Path,
) -> None:
    """The shape every probe step had until 2026-09-05: START carried the run,
    END carried nothing. A run that did not say it closed is not closed."""
    legacy_end = (
        f"### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "cpu_max_mhz=4600 ram_mt_s=3600"
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", end_line=legacy_end),
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "### END names run_id=None" in result.stderr, result.stderr


def test_a_start_that_is_not_the_first_of_the_runs_stamps_is_exit_1(
    tmp_path: Path,
) -> None:
    body = (
        "{\n"
        "printf '### ROUND id=%s product_sha256=%s\\n' "
        '"${RUN_ROUND:-}" "${RUN_PRODUCT_SHA256:-}"\n'
        f"printf '### START uptime_since={onedoor.UPTIME} run_id=%s\\n' \"$RUN_ID\"\n"
        f"printf '%s\\tprobe\\tCONFIG\\timg=sha256:{onedoor.LOCAL_ID_HEX}\\n' "
        '"${RUN_HOST:-nohost}"\n'
        f"printf '### END uptime_since={onedoor.UPTIME} run_id=%s\\n' \"$RUN_ID\"\n"
        '} > "$out"\n'
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", _writes(tmp_path / "e", body))
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "### ROUND precedes this run's first ### START" in result.stderr, (
        result.stderr
    )


def test_a_workload_stamp_before_start_is_the_recorded_convention_and_passes(
    tmp_path: Path,
) -> None:
    """``### WORKLOAD`` opens every recorded artifact; START is the first of the
    run's OWN stamps (START, ROUND, END), not the first ``###`` line."""
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    text = (onedoor.envelope(root, "alpha") / "probe.tsv").read_text(encoding="utf-8")
    assert text.startswith("### WORKLOAD"), text
    assert "1 artifact(s) parse" in result.stdout, result.stdout


@pytest.mark.parametrize("json_text", ["{}", "[]", '{"flips": 0}'])
def test_a_json_artifact_is_held_to_json_and_never_to_a_stamp(
    tmp_path: Path, json_text: str
) -> None:
    body = onedoor.probe_step(tmp_path / "e")
    body = body.replace(
        "# RUN_ARTIFACTS: probe.tsv\n", "# RUN_ARTIFACTS: probe.tsv probe.json\n"
    ).replace(
        '} > "$out"\n',
        '} > "$out"\n'
        + f"printf '%s\\n' '{json_text}' > \"${{RUN_OUT_DIR:?}}/probe.json\"\n",
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", body)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "2 artifact(s) parse" in result.stdout, result.stdout


def test_end_stamp_in_common_sh_names_the_run_and_refuses_without_one(
    tmp_path: Path,
) -> None:
    """``_common.sh``'s emitter, not a hand-written line: a campaign step's
    ``### END`` carries ``run_id=`` from the same variable ``### START`` does."""
    stamped = (
        "#!/usr/bin/env bash\n"
        "# RUN_ARTIFACTS: stamped.tsv\n"
        "set -euo pipefail\n"
        '. "${RUN_ROOT:?}/tools/runs/_common.sh"\n'
        "{\n"
        "microbench_stamp\n"
        "start_stamp\n"
        "round_stamp\n"
        f"row probe CONFIG img=sha256:{onedoor.LOCAL_ID_HEX}\n"
        "end_stamp\n"
        '} > "${RUN_OUT_DIR:?}/stamped.tsv"\n'
    )
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-stamped.sh", stamped)
    result = onedoor.door(root, Scenario("alpha", "1-stamped.sh"))
    assert result.returncode == 0, (result.stdout, result.stderr)
    sweep = onedoor.rows_module().read(onedoor.envelope(root, "alpha") / "stamped.tsv")
    assert sweep.stamp("END")["run_id"] == sweep.stamp("START")["run_id"], sweep.markers
    assert sweep.stamp("END")["run_id"].startswith(f"{onedoor.RUN_DATE}-alpha-stamped")

    bare = onedoor.bash(
        f". '{onedoor.COMMON_SH}'; end_stamp",
        onedoor.bare_env(tmp_path / "stubs", RUN_REPO=str(onedoor.REPO)),
        onedoor.REPO,
    )
    assert bare.returncode != 0
    assert "end_stamp: RUN_ID is unset" in bare.stderr, bare.stderr
    assert bare.stdout == "", "a stamp was written from no run"
