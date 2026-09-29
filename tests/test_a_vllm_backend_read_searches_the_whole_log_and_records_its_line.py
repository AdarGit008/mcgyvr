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
import os
import re
import subprocess
from pathlib import Path

import pytest

from mcgyvr.fleet import read
from tests import onedoor
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


# --------------------------------------------------------------------------
# what the repo commits
# --------------------------------------------------------------------------
