"""A vLLM unit's attention backend is read from its whole log, and the line is kept.

Owner ruling: "fix the reader and record the line". ``rig-id-relock``'s
srv2-03 — a ``read`` of the b-small pair on srv2 — stops with ``STOP srv2-03:
srv2_3b reported no attention_backend`` when both vLLM units file
``attention_backend: null``.

A reader that takes the FIRST line matching ``attention backend`` and looks
for a token in that line alone reads a log that names the backend elsewhere as
``none``. The lock's own method
(``records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py``)
searches the WHOLE log for the same tokens, and so does ``rig-units.sh``.

* The backend is the token the whole log carries, over the same token list.
  Owner ruling B4 holds: a backend is never guessed, so a log naming no token
  anywhere stays ``none``.
* The reader also reports what it saw: ``backend_line=PORT,BASE64`` carries the
  first line it matched, truncated, so a ``none`` names the real wording instead
  of nothing. :mod:`mcgyvr.fleet.read` parses it and files it beside
  ``attention_backend`` as data that is never judged.
* The stop stands: ``assemble_evidence.py`` refuses a missing or
  non-unanimous backend.
* srv2-03 is logged as failed, so it gets its one retry. A ``read`` has no
  wrapper and no artifact of its own — its run id is minted when it runs — so
  the retry is the same door command under a new run id.

No rig is reached: every log here is printed by a stub ``docker``, and every
window is written on paper.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet import read
from tests import onedoor
from tests.lockfleets_window import (
    REPO,
    USE,
    WINDOW_DATE,
    Window,
    assemble_module,
    context,
    frozen_window,
    plan_module,
)
from tests.test_a_read_measures_before_it_judges_and_loads_a_unit import Rig, rig_text
from tests.test_a_read_measures_before_it_judges_and_loads_a_unit import (
    record as read_record,
)
from tests.test_a_rig_is_read_through_the_door_without_leasing_it import (
    C_3B,
    GATE_SCRIPTS,
    UNIT_3B,
    UNIT_7B,
    go_live,
    unit_rows,
)

STEPS_DIR = REPO / "tools/runs/campaigns/lock-fleets/rig-id-relock"
REASON = "the read filed no attention_backend for either unit"
#: What the repo commits as srv2-03's reason.
SRV2_03_REASON = (
    "both vLLM units filed attention_backend null; the reader read only the "
    "first matching line; owner 2026-09-16: fix the reader and record the line"
)

#: srv2's log shape: the line that says "attention backend" carries no token,
#: and the token is on a later line the ``attention[ _]backend`` match misses.
SELECTING = "INFO 09-16 11:20:04 selector.py:8] Resolving attention backend"
SRV2_LOG = (
    "INFO 09-16 11:20:01 loader.py:12] Loading weights\n"
    f"{SELECTING}\n"
    "INFO 09-16 11:20:06 gpu_model_runner.py:3] Using FLASH_ATTN for the decoder\n"
)
#: How much of the matched line a row carries.
LINE_MAX = 400


def _reader(tmp_path: Path, log: str) -> list[str]:
    """``rig-units.sh`` run here against a stub ``docker`` whose ``logs`` prints
    ``log`` as the separate lines a container prints, one per line."""
    stubs = tmp_path / "bin"
    printed = tmp_path / "docker-logs.txt"
    printed.parent.mkdir(parents=True, exist_ok=True)
    printed.write_text(log, encoding="utf-8")
    onedoor.executable(
        stubs / "docker",
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        f"  ps) printf '%s|%s|%s\\n' {C_3B} mcgyvr-srv2-3b mcgyvr ;;\n"
        "  inspect) echo 0 ;;\n"
        f'  logs) cat "{printed}" ;;\n'
        "esac\n",
    )
    onedoor.executable(stubs / "nvidia-smi", "#!/usr/bin/env bash\nexit 0\n")
    onedoor.executable(
        stubs / "curl",
        "#!/usr/bin/env bash\n"
        'case "$*" in *is_sleeping*) echo \'{"is_sleeping": false}\' ;;\n'
        "  *) exit 7 ;; esac\n",
    )
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(
        ["bash", str(GATE_SCRIPTS / "rig-units.sh"), "vllm:8001:mcgyvr-srv2-3b"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


def _rows(lines: list[str], key: str) -> list[str]:
    return [line for line in lines if line.startswith(f"{key}=")]


def _one(lines: list[str], key: str) -> str:
    found = _rows(lines, key)
    assert len(found) == 1, lines
    return found[0]


def _recorded(lines: list[str]) -> str:
    """The line ``backend_line=8001,BASE64`` carries."""
    port, _, encoded = _one(lines, "backend_line").partition("=")[2].partition(",")
    assert port == "8001", lines
    return base64.b64decode(encoded).decode("utf-8")


# --------------------------------------------------------------------------
# the reader on the rig
# --------------------------------------------------------------------------


def test_the_backend_is_the_token_the_whole_log_carries_not_the_first_lines(
    tmp_path: Path,
) -> None:
    """The srv2 case: the matched line names no token and the log does."""
    lines = _reader(tmp_path, SRV2_LOG)
    assert "backend=8001,FLASH_ATTN" in lines, lines
    # And the reader says which line it matched, so the row can be read back.
    assert _recorded(lines) == SELECTING
    # Every row stays whitespace- and comma-free: they are split on commas.
    assert all(" " not in line for line in lines), lines


def test_a_log_that_names_no_token_anywhere_is_none_and_still_names_its_line(
    tmp_path: Path,
) -> None:
    """Owner ruling B4: a backend is never guessed."""
    lines = _reader(tmp_path, f"{SELECTING}\n")
    assert "backend=8001,none" in lines, lines
    assert _recorded(lines) == SELECTING


def test_a_log_with_no_matching_line_records_no_line_and_does_not_crash(
    tmp_path: Path,
) -> None:
    lines = _reader(tmp_path, "INFO 09-16 11:20:01 loader.py:12] Loading\n")
    assert "backend=8001,none" in lines, lines
    assert "backend_line=8001," in lines, lines
    assert _recorded(lines) == ""


def test_a_token_met_anywhere_is_the_backend_as_the_09_13_method_read_it(
    tmp_path: Path,
) -> None:
    """``measure_vllm.py`` searches the whole log for the token."""
    lines = _reader(tmp_path, "INFO 09-13 21:40:02 x.py:1] FLASHINFER ready\n")
    assert "backend=8001,FLASHINFER" in lines, lines
    assert _recorded(lines) == ""


def test_an_enormous_log_line_is_truncated_so_a_row_cannot_bloat(
    tmp_path: Path,
) -> None:
    huge = f"{SELECTING} " + "x" * 50_000
    lines = _reader(tmp_path, f"{huge}\n")
    said = _recorded(lines)
    assert len(said) == LINE_MAX, len(said)
    assert said == huge[:LINE_MAX]
    assert all(" " not in line for line in lines), [line[:80] for line in lines]


def test_the_reader_documents_the_row_it_prints() -> None:
    """The header block lists every row the reader prints, and only those."""
    text = (GATE_SCRIPTS / "rig-units.sh").read_text(encoding="utf-8")
    header = text.split("set -u")[0]
    assert "backend_line=PORT,BASE64" in header, header
    printed = set(re.findall(r"^\s*printf '(\w+)=", text, re.M))
    documented = set(re.findall(r"^#   (\w+)=", header, re.M))
    assert printed <= documented, (printed, documented)
    assert "backend_line" in printed


# --------------------------------------------------------------------------
# the row, parsed
# --------------------------------------------------------------------------


def _encoded(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_a_backend_line_row_is_decoded_and_never_lands_in_the_snapshot() -> None:
    """A row the parser does not know becomes a snapshot field, and the rig id
    is hashed over the snapshot — so this row is parsed, not swept up."""
    parsed = read.parse(
        f"backend=8001,FLASH_ATTN\nbackend_line=8001,{_encoded(SELECTING)}\n"
        "backend=8002,none\nbackend_line=8002,\n"
    )
    assert parsed.backend_line == {8001: SELECTING, 8002: ""}
    assert parsed.backend == {8001: "FLASH_ATTN", 8002: None}
    assert "backend_line" not in parsed.snapshot


@pytest.mark.parametrize(
    ("row", "said"),
    [
        ("backend_line=8001", "a backend line row is PORT,BASE64"),
        ("backend_line=x,QQ==", "a backend line row is PORT,BASE64"),
        ("backend_line=8001,not-base64!", "does not decode"),
    ],
    ids=["no-comma", "no-port", "undecodable"],
)
def test_a_backend_line_row_the_reader_mangled_is_refused(row: str, said: str) -> None:
    with pytest.raises(read.ReadError, match=re.escape(said)):
        read.parse(f"{row}\n")


def test_the_parser_bounds_the_line_as_the_reader_does() -> None:
    parsed = read.parse(f"backend_line=8001,{_encoded('y' * 50_000)}\n")
    assert parsed.backend_line == {8001: "y" * LINE_MAX}


# --------------------------------------------------------------------------
# what the read files
# --------------------------------------------------------------------------


def _read_with_lines(**line: str) -> str:
    """One reader's output for srv2, with a recorded line per port."""
    text = rig_text(backend=("8001,FLASH_ATTN", "8002,none"))
    return text + "".join(
        f"backend_line={port},{_encoded(said)}\n" for port, said in line.items()
    )


def test_the_line_the_reader_matched_is_filed_beside_the_backend_and_not_judged(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)

    text = _read_with_lines(**{"8001": "Using FLASH_ATTN", "8002": SELECTING})
    read_record(text, "live", Rig())

    three = unit_rows(journal, UNIT_3B)
    seven = unit_rows(journal, UNIT_7B)
    assert three["attention_backend"]["observed"] == "FLASH_ATTN"
    assert seven["attention_backend"]["observed"] is None
    # The line is filed beside it, under its own field, and never judged: a row
    # the judge looked at carries an `alert`.
    line = three["attention_backend_line"]
    assert line["observed"] == "Using FLASH_ATTN"
    assert line["attention_backend_line"] == "Using FLASH_ATTN"
    assert "alert" not in line
    # So a `none` names the wording the rig actually printed.
    assert seven["attention_backend_line"]["observed"] == SELECTING
    assert "alert" not in seven["attention_backend_line"]


def test_a_reader_that_printed_no_line_files_an_empty_one(tmp_path: Path) -> None:
    journal = go_live(tmp_path)

    read_record(rig_text(backend=("8001,FLASH_ATTN", "8002,none")), "live", Rig())

    assert unit_rows(journal, UNIT_3B)["attention_backend_line"]["observed"] == ""
    assert unit_rows(journal, UNIT_7B)["attention_backend_line"]["observed"] == ""


# --------------------------------------------------------------------------
# srv2-03 runs again: a read entry's one retry
# --------------------------------------------------------------------------


def _no_backend(payload: dict[str, Any]) -> None:
    """The srv2-03 defect: both vLLM units filed attention_backend null."""
    for fields in payload["units"].values():
        fields["attention_backend"] = {"observed": None, "attention_backend": None}


def _rig_failed(payload: dict[str, Any]) -> None:
    payload["rig"]["failed"] = {"b_small": "its in-flight page could not be read"}


def _window_to(tmp_path: Path, last: str, change: dict[str, Any]) -> Window:
    window = frozen_window(tmp_path)
    for entry in window.runs.entries:
        window.write(entry, change.get(entry.id))
        if entry.id == last:
            break
    return window


def test_a_read_entry_gets_one_retry_of_its_own_right_after_it(
    tmp_path: Path,
) -> None:
    window = _window_to(tmp_path, "beta-03", {"beta-03": _no_backend})
    plan = plan_module()
    made = plan.retry(window.root, USE, "beta-03", REASON, journal=str(window.journal))
    # A read has no wrapper and no artifact of its own: its run id is minted
    # when it runs, so the retry names neither.
    assert made == {
        "entry": "beta-03",
        "reason": REASON,
        "retry_entry": "beta-03-retry1",
    }
    listed = window.root / "records/measurements/lock-fleets" / USE / "retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["retries"] == [made]
    wrappers = window.root / f"tools/runs/campaigns/lock-fleets/{USE}"
    assert not [p for p in wrappers.glob("*.sh") if "beta-03" in p.name]

    runs = plan.read_runs(window.root, USE)
    beta = [e.id for e in runs.entries if e.rig == "beta"]
    assert beta[:5] == ["beta-01", "beta-02", "beta-03", "beta-03-retry1", "beta-04"]
    failed, retry = runs.entry("beta-03"), runs.entry("beta-03-retry1")
    assert (retry.kind, retry.fleet, retry.units, retry.run) == (
        "read",
        "two",
        ("b_small", "b_mid"),
        "c1",
    )
    assert (retry.retry_of, retry.wrapper) == ("beta-03", "")
    # The same door command, under the run id drive.sh mints for it.
    assert retry.argv == failed.argv
    assert retry.artifact == failed.artifact
    assert retry.run_id(WINDOW_DATE, "run-20260916T120000-0a1b2c3d") == (
        "run-20260916T120000-0a1b2c3d"
    )
    assert retry.envelope(WINDOW_DATE) == "journal"
    assert runs.retry_for("beta-03") == retry


def test_a_load_entry_is_retried_the_same_way(tmp_path: Path) -> None:
    """A load is a read of one unit: it starts nothing and mints its own id."""
    window = _window_to(tmp_path, "beta-04", {"beta-04": _rig_failed})
    plan = plan_module()
    made = plan.retry(window.root, USE, "beta-04", REASON, journal=str(window.journal))
    assert made["retry_entry"] == "beta-04-retry1"
    assert "step" not in made and "artifact" not in made
    runs = plan.read_runs(window.root, USE)
    assert runs.entry("beta-04-retry1").kind == "load"


@pytest.mark.parametrize("entry", ["beta-02", "beta-06"], ids=["up", "down"])
def test_retry_refuses_a_serve_entry_that_would_supersede_its_own_file(
    tmp_path: Path, entry: str
) -> None:
    """A second ``serve up``/``serve down`` moves the kept ``serve-<mode>.json``
    aside as superseded, which names a data point superseded."""

    def failed(payload: dict[str, Any]) -> None:
        key = "compose_up_exit" if entry == "beta-02" else "compose_down_exit"
        payload["step"][key] = 1

    window = _window_to(tmp_path, entry, {entry: failed})
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match="only a campaign unit or move"):
        plan.retry(window.root, USE, entry, REASON, journal=str(window.journal))


def test_a_retry_of_a_read_gets_no_extra_of_its_own(tmp_path: Path) -> None:
    window = _window_to(tmp_path, "beta-03", {"beta-03": _no_backend})
    window.retry("beta-03", _no_backend)
    plan = plan_module()
    for give, said in (
        (plan.retry, "beta-03-retry1 is itself a retry"),
        (plan.rerun, "beta-03-retry1 is itself a retry"),
        (plan.diagnose, "only a failed retry of a unit entry"),
        (plan.relaunch, "beta-03-retry1 is not a diagnostic start"),
    ):
        with pytest.raises(plan.PlanRefusedError, match=re.escape(said)):
            give(
                window.root,
                USE,
                "beta-03-retry1",
                REASON,
                journal=str(window.journal),
            )


def test_the_recheck_passes_the_failed_read_and_the_retry_runs_next(
    tmp_path: Path,
) -> None:
    window = _window_to(tmp_path, "beta-03", {"beta-03": _no_backend})
    asm, plan = assemble_module(), plan_module()
    # The stop is the one srv2-03 hit, and it is unchanged.
    before = asm.check(context(window), "beta", "beta-03")
    assert any("b_small reported no attention_backend" in why for why in before)

    plan.retry(window.root, USE, "beta-03", REASON, journal=str(window.journal))
    window.reload()
    ctx = context(window)
    assert asm.check(ctx, "beta", "beta-03") == []
    _reasons, said = asm.verdict(ctx, "beta", "beta-03")
    assert "beta-03 failed, retried by beta-03-retry1" in said
    order = [e.id for e in ctx.runs.entries if e.rig == "beta"]
    unlogged = [e for e in order if ctx.runs.logged(e) is None]
    assert unlogged[0] == "beta-03-retry1"


def test_a_passing_retry_of_a_read_stands_in_for_the_entry_it_retried(
    tmp_path: Path,
) -> None:
    clean = frozen_window(tmp_path / "clean")
    clean.write_all()
    retried = frozen_window(tmp_path / "retried")
    retried.write_all({"beta-03": _no_backend})
    made = retried.retry("beta-03")
    asm = assemble_module()
    want, _, _ = asm.assemble(context(clean))
    evidence, runs, _ = asm.assemble(context(retried))
    assert evidence == want
    kept = runs["runs"]
    assert set(kept) == {e.id for e in retried.runs.entries}
    assert kept["beta-03"]["retried_by"] == made["retry_entry"]
    assert any(
        "reported no attention_backend" in why for why in kept["beta-03"]["check"]
    )
    assert kept["beta-03-retry1"]["retry_of"] == "beta-03"


def test_assembly_refuses_a_failed_read_whose_retry_did_not_pass(
    tmp_path: Path,
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"beta-03": _no_backend})
    window.retry("beta-03", _no_backend)
    asm = assemble_module()
    with pytest.raises(
        asm.AssemblyRefusedError, match=re.escape("beta-03-retry1 fails its check")
    ):
        asm.assemble(context(window))


# --------------------------------------------------------------------------
# what the repo commits
# --------------------------------------------------------------------------


def test_srv2_03_of_rig_id_relock_has_its_one_retry_committed() -> None:
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    srv1 = [e.id for e in runs.entries if e.rig == "srv1"]
    srv2 = [e.id for e in runs.entries if e.rig == "srv2"]
    # srv1 does not move; srv2 gains exactly the read's retry.
    assert (len(srv1), len(srv2)) == (16, 31)
    assert srv2[4:8] == ["srv2-02", "srv2-03", "srv2-03-retry1", "srv2-04"]
    derived, text = plan.derive_retry("rig-id-relock", runs.entry("srv2-03"))
    assert derived == {"retry_entry": "srv2-03-retry1"}
    assert text == ""
    listed = REPO / "records/measurements/lock-fleets/rig-id-relock/retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["retries"][-1] == {
        "entry": "srv2-03",
        "reason": SRV2_03_REASON,
        **derived,
    }
    # srv2-01's retry, with its wrapper and artifact, is untouched.
    assert doc["retries"][0]["entry"] == "srv2-01"
    assert len(doc["retries"]) == 2
    assert not [p for p in STEPS_DIR.glob("*.sh") if "srv2-03" in p.name]

    read_entry, retry = runs.entry("srv2-03"), runs.entry("srv2-03-retry1")
    assert retry.retry_of == "srv2-03"
    assert (retry.kind, retry.fleet, retry.units) == (
        "read",
        "b-small",
        ("srv2_3b", "srv2_7b"),
    )
    assert retry.argv == read_entry.argv


def test_the_readme_records_the_2026_09_16_ruling_and_what_it_cites() -> None:
    readme = (REPO / "records/measurements/lock-fleets/README.md").read_text("utf-8")
    assert "2026-09-16" in readme
    assert "srv2-03" in readme
    assert "measure_vllm.py" in readme
    assert "attention_backend" in readme
    # The retry rule does not say only a unit or a move run is retried.
    assert "unit or move run has a wrapper of its own to retry" not in readme
    assert os.access(REPO / "src/mcgyvr/serving/gate-scripts/rig-units.sh", os.R_OK)
