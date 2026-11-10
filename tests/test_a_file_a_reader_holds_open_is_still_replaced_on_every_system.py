"""A file a reader holds open is still replaced whole, on every system.

Windows refuses to rename over a file another handle holds open (Python's own
``open`` does not share delete), which a record read at that moment does;
``atomic.replace`` tries the rename again until the reader lets go. POSIX lets
the rename through at once, and the reader keeps the bytes it opened. This runs
on the macOS and Windows runners too (``.github/workflows/platforms.yml``),
where the refusal is real rather than simulated.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from mcgyvr import atomic


def test_a_file_a_reader_holds_open_is_replaced_once_the_reader_lets_go(
    tmp_path: Path,
) -> None:
    target = tmp_path / "record.json"
    target.write_text("old", encoding="utf-8")
    reader = open(target, "rb")  # noqa: SIM115 - closed by the timer, as a reader would
    # Well inside the retry window (REPLACE_TRIES pauses of REPLACE_PAUSE_S).
    letting_go = threading.Timer(atomic.REPLACE_PAUSE_S * 4, reader.close)
    letting_go.start()
    try:
        atomic.write(target, "new")
        # POSIX let the rename through at once; Windows waited for the close.
        held = reader.read() if sys.platform != "win32" else None
    finally:
        letting_go.join()
        reader.close()

    assert target.read_text(encoding="utf-8") == "new"
    assert held in (None, b"old")  # a POSIX reader keeps the bytes it opened
    assert [p.name for p in tmp_path.iterdir()] == ["record.json"]
