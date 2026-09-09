"""The ``run_id`` and round a file stamps must be the ones the door exported.

Gate 8 (``08-parse.py``) once checked that a ``### START`` carried SOME
``run_id=`` and that a ``### ROUND`` followed. A step that copied another
run's stamps — or hard-coded last week's — produced a file that parsed, named
a run the door never started, and was filed green under this run's envelope.
Nothing tied the artifact to the invocation that produced it.

So every ``### START`` and ``### END`` in this run's portion of a declared
TSV must carry ``run_id=<RUN_ID>``, and every ``### ROUND`` must carry
``id=<RUN_ROUND> product_sha256=<RUN_PRODUCT_SHA256>`` — the values the door
exported to the step — or gate 8 exits 1 naming both the stamped value and
the run's own. For a ``RUN_APPENDS`` file only the bytes this run appended
are held to this run's id: the creator's stamps stay the creator's.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario
from tests.test_an_appending_step_may_only_append_to_a_file_the_door_produced import (
    appender,
)

PROBE = Scenario("alpha", "1-probe.sh")
FOREIGN = "2026-09-01-alpha-probe-lastweek"


def _stamping(env_file: Path, start_id: str, end_id: str, round_line: str) -> str:
    """The probe step with its three stamps spelled by the test. The stamp
    lines are double-quoted, so ``$RUN_ID`` and ``${RUN_ROUND:-}`` in them
    are the door's values and a literal id is a literal id."""
    body = onedoor.probe_step(env_file)
    head, _, _ = body.partition("{\n")
    return head + (
        "{\n"
        f'printf "### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 '
        f'run_id={start_id}\\n"\n'
        f'printf "{round_line}\\n"\n'
        f"printf '%s\\tprobe\\tCONFIG\\timg=sha256:{onedoor.LOCAL_ID_HEX}\\n' "
        '"${RUN_HOST:-nohost}"\n'
        f'printf "### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 '
        f'run_id={end_id}\\n"\n'
        '} > "$out"\n'
    )


OWN_ROUND = "### ROUND id=${RUN_ROUND:-} product_sha256=${RUN_PRODUCT_SHA256:-}"


def test_a_start_naming_another_run_is_exit_1_naming_both(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _stamping(tmp_path / "e", FOREIGN, "$RUN_ID", OWN_ROUND),
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert run_id != FOREIGN
    assert (
        f"### START names run_id='{FOREIGN}' and this run is run_id='{run_id}'"
        in result.stderr
    ), result.stderr
    assert "not this run's evidence" in result.stderr, result.stderr


def test_an_end_naming_another_run_is_exit_1_naming_both(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _stamping(tmp_path / "e", "$RUN_ID", FOREIGN, OWN_ROUND),
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert (
        f"### END names run_id='{FOREIGN}' and this run is run_id='{run_id}'"
        in result.stderr
    ), result.stderr


def test_a_round_that_is_not_the_one_gate_1_checked_is_exit_1_naming_both(
    tmp_path: Path,
) -> None:
    """The round is hard-coded to a digest the tree does not have: exactly
    the artifact that would compare a measurement against the wrong code."""
    root = onedoor.fixture_repo(tmp_path)
    foreign_round = f"### ROUND id=r1-old product_sha256={onedoor.PRODUCT_SHA256}"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _stamping(tmp_path / "e", "$RUN_ID", "$RUN_ID", foreign_round),
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    round_id, digest = onedoor.pinned(root)
    assert (
        f"### ROUND names id='r1-old' product_sha256='{onedoor.PRODUCT_SHA256}' "
        f"and this run measured under id='{round_id}' product_sha256='{digest}'"
    ) in result.stderr, result.stderr


def test_stamps_that_name_this_run_and_its_round_are_green(tmp_path: Path) -> None:
    """The control: the same step with the door's own values passes."""
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _stamping(tmp_path / "e", "$RUN_ID", "$RUN_ID", OWN_ROUND),
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "1 artifact(s) parse" in result.stdout


def test_an_appended_block_is_held_to_this_run_and_the_creators_block_is_not(
    tmp_path: Path,
) -> None:
    """Step ``other`` created the file under its own run id; step ``probe``
    appends a block naming a foreign id. The creator's START is not this
    run's to answer for; the appended START and END are."""
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root, "alpha", "1-other.sh", onedoor.probe_step(tmp_path / "e-other")
    )
    first = onedoor.door(root, Scenario("alpha", "1-other.sh"))
    assert first.returncode == 0, (first.stdout, first.stderr)
    creator = onedoor.read_env_file(tmp_path / "e-other")["RUN_ID"]

    body = appender(tmp_path / "e").replace(
        'run_id=%s\\n\' "$RUN_ID"', f"run_id={FOREIGN}\\n'"
    )
    onedoor.add_step(root, "alpha", "2-probe.sh", body)
    result = onedoor.door(root, Scenario("alpha", "2-probe.sh"))
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"run_id='{FOREIGN}' and this run is run_id='{run_id}'" in result.stderr, (
        result.stderr
    )
    assert creator not in result.stderr.split("names run_id=", 1)[1], (
        "the creator's stamp was judged as this run's"
    )

    # The control: the same file — the creator's block and the refused run's
    # foreign block both in its history now — takes a block that names its
    # run, and only THAT block is this run's to answer for.
    onedoor.add_step(root, "alpha", "2-probe.sh", appender(tmp_path / "e"))
    green = onedoor.door(root, Scenario("alpha", "2-probe.sh", suffix="pass2"))
    assert green.returncode == 0, (green.stdout, green.stderr)
    text = (onedoor.envelope(root, "alpha") / "probe.tsv").read_text(encoding="utf-8")
    assert text.count("### START") == 3 and f"run_id={FOREIGN}" in text, text
