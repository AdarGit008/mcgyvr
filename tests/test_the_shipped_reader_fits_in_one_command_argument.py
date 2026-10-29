"""The shipped reader fits in one command argument, and runs as the reader.

The door ships the reader to a POSIX rig as one shell line, ``echo <base64> |
base64 -d | python3 -I -B -``, which ssh hands on as a single argument. Linux
refuses any one argument longer than ``MAX_ARG_STRLEN`` ("PAGE_SIZE * 32",
https://github.com/torvalds/linux/blob/master/include/uapi/linux/binfmts.h),
131072 bytes with 4 KiB pages; past it every read over ssh fails as a rig that
did not answer. So the line carries the reader assembled with the modules it
imports and packed (zlib, then base85, in one exec line), with room to grow,
and the packed program reads a machine exactly as the reader module does.
"""

from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

from tests.machine_shapes import host_shapes, shape
from tests.machinereader import READER, run, stage, stage_host

#: Linux's MAX_ARG_STRLEN with 4 KiB pages.
ONE_ARGUMENT = 4096 * 32
#: What the line may take of it: the reader carries hostos and the wire's names,
#: and two fifths of an argument stay free for it to grow.
ROOM = 3 * ONE_ARGUMENT // 5


def test_the_scan_and_the_card_read_each_fit_with_room_in_one_argument() -> None:
    from mcgyvr.serving import gatelib

    for command in (gatelib.scan_read_command(), gatelib.cards_read_command()):
        assert len(command.encode("utf-8")) < ROOM, (
            f"the shipped reader's command is {len(command)} bytes; one argument "
            f"holds {ONE_ARGUMENT}"
        )


def test_the_shipped_line_unpacks_to_the_assembled_reader() -> None:
    from mcgyvr.serving import gatelib, shipped

    command = gatelib.scan_read_command()
    program = base64.b64decode(command.split(" ", 2)[1])
    packed = program.split(b"b85decode(b'", 1)[1].split(b"')", 1)[0]
    assert zlib.decompress(base64.b85decode(packed)) == shipped.reader()


def test_the_shipped_program_reads_a_machine_as_the_reader_module_does(
    tmp_path: Path,
) -> None:
    for number, staged in enumerate(
        (stage(shape("one-card")), *(stage_host(m) for m in host_shapes()[:4]))
    ):
        # The module alone imports mcgyvr from this checkout's environment; the
        # shipped program carries what it imports and imports nothing installed.
        module = run(staged, tmp_path / f"module-{number}", source=READER.read_bytes())
        sent = run(staged, tmp_path / f"shipped-{number}")
        assert sent.returncode == 0, sent.stderr
        assert json.loads(sent.stdout) == json.loads(module.stdout)
