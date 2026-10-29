"""The shipped reader fits in one command argument, and runs as the reader.

The door ships the reader to a rig as one shell line, ``echo <base64> | base64
-d | python3 -I -B -``, which ssh hands on as a single argument. Linux refuses
any one argument longer than ``MAX_ARG_STRLEN`` ("PAGE_SIZE * 32",
https://github.com/torvalds/linux/blob/master/include/uapi/linux/binfmts.h),
131072 bytes with 4 KiB pages; past it every read over ssh fails as a rig that
did not answer. So the line carries the reader packed (zlib, then base85, in one
exec line), with room to grow, and the packed program reads a machine exactly
as the reader's own source does.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from tests.machine_shapes import host_shapes, shape
from tests.machinereader import READER, run, stage, stage_host

#: Linux's MAX_ARG_STRLEN with 4 KiB pages.
ONE_ARGUMENT = 4096 * 32


def test_the_scan_and_the_card_read_each_fit_in_half_an_argument() -> None:
    from mcgyvr.serving import gatelib

    for command in (gatelib.scan_read_command(), gatelib.cards_read_command()):
        assert len(command.encode("utf-8")) < ONE_ARGUMENT // 2, (
            f"the shipped reader's command is {len(command)} bytes; one argument "
            f"holds {ONE_ARGUMENT}"
        )


def test_the_shipped_line_unpacks_to_the_reader_itself() -> None:
    import zlib

    from mcgyvr.serving import gatelib

    command = gatelib.scan_read_command()
    program = base64.b64decode(command.split(" ", 2)[1])
    packed = program.split(b"b85decode(b'", 1)[1].split(b"')", 1)[0]
    assert zlib.decompress(base64.b85decode(packed)) == READER.read_bytes()


def test_the_packed_program_reads_a_machine_as_the_source_does(
    tmp_path: Path,
) -> None:
    from mcgyvr.serving import gatelib

    packed = gatelib.packed_reader(READER.read_bytes())
    for number, staged in enumerate(
        (stage(shape("one-card")), *(stage_host(m) for m in host_shapes()[:4]))
    ):
        plain = run(staged, tmp_path / f"plain-{number}")
        shipped = run(staged, tmp_path / f"packed-{number}", source=packed)
        assert shipped.returncode == 0, shipped.stderr
        assert json.loads(shipped.stdout) == json.loads(plain.stdout)
