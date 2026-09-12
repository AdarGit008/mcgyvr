"""A config that changed and a compose file that did not are two configurations.

The live ladder ran for two days in exactly that state. On 2026-09-06 the owner
narrowed ``local_qwen3.6-35b-a3b`` from eight slots to two, for a reason the
config states in a comment: at width 8 the rung gives each stream 5.1 tok/s and
a 1024-token reply needs 201 s, past ``budgets.request_timeout_s``. The compose
file on srv1 was never re-emitted and the container was never restarted, so the
unit went on serving ``--parallel 8 -c 32768`` while ``mcgyvr`` bounded dispatch
at 2. Six of the unit's eight slots were unreachable, three expert blocks that
the smaller KV cache would have freed stayed on the CPU, and nothing anywhere
said so: :meth:`mcgyvr.capacity.Capacity.of` is called with no probe, so the two
numbers never met.

That is what this file refuses. ``mcgyvr emit`` already renders the exact bytes
a config implies; the only thing missing was a caller that compares them with
the bytes on disk and says the config moved. ``--check`` is that caller. It
writes nothing — the operator re-emits and restarts, because this repository
does not reach into a rig — and it exits :attr:`~mcgyvr.exits.Exit.MISMATCH`,
which is the code ``scan`` already uses for "the record and the machine stopped
agreeing". A drift between a config and the unit it describes is the same shape
of fact about a different pair.

Three states, and they are not one test: the files agree, a declaration moved,
and nothing was ever emitted. The third is separate because "no file" and "the
wrong file" send an operator to different commands, and a check that answered
them alike would send half of them to the wrong one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.exits import Exit
from mcgyvr.scan import Scan

#: The window every emit here declares. Stated per run since
#: ``mcgyvr.serving.DEFAULT_CONTEXT`` was retired on 2026-09-06 — ``-c`` is
#: this times the slot count, which is precisely the product a changed width
#: moves.
WINDOW = 4096

#: A measured row from the capability table, dense and small enough that a
#: 12 GiB card sizes it without an argument. The drift under test is about a
#: width an operator wrote, so the model must not be the interesting part.
MODEL = "qwen2.5-coder:3b"

#: What the `install` fixture hands a case: where compose files land, the
#: config path, and a way to rewrite the tier's declared width.
Install = tuple[Path, Path, Callable[[int], None]]

#: The host a source's URL routes to and the name the machine calls itself.
#: They are the same string here on purpose: reconciling the two is
#: ``cli._resolve_hosts``'s job and not this file's subject.
HOST = "rig"


def _config(width: int) -> str:
    """A one-rung ladder whose tier declares ``width`` slots of its own."""
    return f"""
version: 1
sources:
  rig:
    base_url: "http://{HOST}:8080"
    api: openai
    max_parallel: 8
models:
  "{MODEL}":
    vram_gb: 2.4
    disk_gb: 1.9
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
ladder:
  tiers:
    - name: local_qwen2.5-coder-3b
      source: rig
      model: "{MODEL}"
      max_parallel: {width}
"""


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Install:
    """A scanned machine, a config that can be rewritten, and where files land.

    The scan is written rather than stubbed because ``emit`` refuses a host it
    has never measured, and that refusal is a different one from this file's.
    """
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / f"{HOST}.json").write_text(
        Scan.of(
            host=HOST,
            vram_mib=12288,
            ram_gb=64.0,
            disk_free_gb=900.0,
            cores=10,
            threads=20,
            bandwidth_gbps=41.2,
        ).to_json(),
        encoding="utf-8",
    )
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))

    config = tmp_path / "mcgyvr.yaml"
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))

    out = tmp_path / "compose"
    out.mkdir()

    def declare(width: int) -> None:
        config.write_text(_config(width), encoding="utf-8")

    return out, config, declare


def _emit(out: Path) -> int:
    return main(["emit", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


def _check(out: Path) -> int:
    return main(["emit", "--check", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


def test_a_file_that_is_what_the_config_emits_is_not_a_mismatch(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    out, _config_path, declare = install
    declare(2)
    assert _emit(out) == Exit.OK
    capsys.readouterr()

    assert _check(out) == Exit.OK
    said = capsys.readouterr()
    assert "compose.rig.yml" in said.out
    # Nothing is written by a check: the file that was there is the file that
    # is there, byte for byte, or the exit code above would not have been OK.
    assert (out / "compose.rig.yml").exists()


def test_a_width_that_moved_since_the_last_emit_is_a_mismatch(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    out, _config_path, declare = install
    declare(8)
    assert _emit(out) == Exit.OK
    before = (out / "compose.rig.yml").read_text(encoding="utf-8")
    capsys.readouterr()

    # The 2026-09-06 edit, exactly: a width narrowed in the config and nothing
    # re-emitted afterwards.
    declare(2)

    assert _check(out) == Exit.MISMATCH
    said = capsys.readouterr()
    complaint = said.err or said.out
    assert "compose.rig.yml" in complaint
    # The operator's next move is in the message: which file, and that it is
    # re-emitting rather than editing that fixes it.
    assert "emit" in complaint
    # A check writes nothing. The stale file is still stale afterwards, which
    # is what makes the exit code the whole answer.
    assert (out / "compose.rig.yml").read_text(encoding="utf-8") == before


def test_a_config_that_was_never_emitted_is_not_reported_as_drift(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    out, _config_path, declare = install
    declare(2)

    assert _check(out) == Exit.MISMATCH
    said = capsys.readouterr()
    complaint = said.err or said.out
    assert "compose.rig.yml" in complaint
    # "Never emitted" and "emitted from a different config" send an operator to
    # different places, so they must not read alike.
    assert "no compose file" in complaint.lower() or "not been emitted" in complaint
