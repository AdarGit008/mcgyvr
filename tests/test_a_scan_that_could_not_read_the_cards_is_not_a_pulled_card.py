"""A scan whose card list was not determined is not a machine with fewer cards.

Rule 1 of ``mcgyvr.scan``: a silent gap reads as "no GPU" when it may mean
"not determined". When nvidia-smi is absent or fails, or prints a row that
cannot be read (a MIG or vGPU parent), the scan carries a note saying so — and
:func:`mcgyvr.scan.compare` used to count the cards anyway, report the prior's
cards as pulled (exit 4, MISMATCH), and ``write_scan`` then replaced the good
record with the card-less one, so the next healthy scan reported every card
as new and the real baseline was gone. Memory and CPU already skip the
comparison when they are undetermined; the card list does the same, and a
record that knows its cards is not replaced by one that does not.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.scan import compare, load_prior, os_machine_id, scan, write_scan

MEMINFO = "MemTotal:       49293144 kB\nMemAvailable:   45010000 kB\n"
LSCPU = (
    "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n"
)
TWO_CARDS = (
    "0, NVIDIA GeForce RTX 3060, 12288, 11286, 1002\n"
    "1, NVIDIA GeForce RTX 3060, 12288, 12, 12276\n"
)
#: The second card as a MIG parent prints it: memory `[N/A]`, unreadable.
ONE_READABLE = (
    "0, NVIDIA GeForce RTX 3060, 12288, 11286, 1002\n"
    "1, NVIDIA A100-SXM4-40GB MIG 1g.5gb, [N/A], [N/A], [N/A]\n"
)


@pytest.fixture
def smi(monkeypatch: pytest.MonkeyPatch) -> Callable[[str | None], None]:
    """Install what nvidia-smi answers; everything else about the machine holds."""
    monkeypatch.setattr(scan_module, "_read_meminfo", lambda: MEMINFO)
    monkeypatch.setattr(scan_module, "measure_bandwidth", lambda: None)
    monkeypatch.setattr(scan_module, "_free_bytes", lambda path: 512 * 1024**3)

    def install(answer: str | None) -> None:
        table = {"nvidia-smi": answer, "lscpu": LSCPU}
        monkeypatch.setattr(
            scan_module, "_run", lambda binary, *a, **k: table.get(binary)
        )

    return install


@pytest.mark.parametrize(
    "answer", [None, ONE_READABLE], ids=["nvidia-smi-failed", "unreadable-row"]
)
def test_an_undetermined_card_list_is_no_mismatch_and_keeps_the_record(
    smi: Callable[[str | None], None], tmp_path: Path, answer: str | None
) -> None:
    smi(TWO_CARDS)
    write_scan(scan(), root=tmp_path)

    smi(answer)
    now = scan()
    prior = load_prior(os_machine_id(now), root=tmp_path)
    assert prior is not None and len(prior.gpus) == 2

    assert compare(now, prior) == (), (
        "a card list nvidia-smi could not give read as cards pulled"
    )
    write_scan(now, root=tmp_path)
    kept = load_prior(os_machine_id(now), root=tmp_path)
    assert kept is not None and len(kept.gpus) == 2, (
        "the record that knew two cards was replaced by one that did not"
    )


def test_a_determined_card_list_that_lost_a_card_is_still_a_mismatch(
    smi: Callable[[str | None], None], tmp_path: Path
) -> None:
    smi(TWO_CARDS)
    write_scan(scan(), root=tmp_path)
    smi(TWO_CARDS.splitlines(keepends=True)[0])
    now = scan()
    found = compare(now, load_prior(os_machine_id(now), root=tmp_path))
    assert [m.field for m in found] == ["gpus"], found
