"""A scan whose card list was not determined is not a machine with fewer cards.

Rule 1 of ``mcgyvr.scan``: a silent gap reads as "no GPU" when it may mean
"not determined". When nvidia-smi is absent or fails, or prints a row that
cannot be read (a MIG or vGPU parent), the one reader's scan carries a note
saying so — and a comparison that counted the cards anyway would report the
record's cards as pulled (exit 4, MISMATCH), and replacing the good record
with the card-less one would make the next healthy scan report every card as
new, with the real baseline gone. So :func:`mcgyvr.serving.rigfile.moved`
compares cards only when both readings determined them, and
:func:`mcgyvr.serving.rigfile.save` does not replace a rig file that knows
its cards with a reading that does not.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from mcgyvr.serving import rigfile, rigscan

MEMINFO = "MemTotal:       49293144 kB\nMemAvailable:   45010000 kB\n"
LSCPU = (
    "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n"
)
TWO_CARDS = (
    "0, 12288, 11286, 1002, NVIDIA GeForce RTX 3060\n"
    "1, 12288, 12, 12276, NVIDIA GeForce RTX 3060\n"
)
#: The second card as a MIG parent prints it: memory `[N/A]`, unreadable.
ONE_READABLE = (
    "0, 12288, 11286, 1002, NVIDIA GeForce RTX 3060\n"
    "1, [N/A], [N/A], [N/A], NVIDIA A100-SXM4-40GB MIG 1g.5gb\n"
)
FIRST_QUERY = f"--query-gpu={rigscan.FIRST_QUERY}"

#: What nvidia-smi answers: its text and why it failed; ``(None, None)`` is a
#: machine without it.
Answer = tuple[str | None, str | None]
Read = Callable[[Answer], rigfile.Saved]


@pytest.fixture
def read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Read:
    """Read the machine with nvidia-smi answering as told, and record it;
    everything else about the machine holds."""
    root = tmp_path / "root"
    (root / "proc").mkdir(parents=True)
    (root / "proc" / "meminfo").write_text(MEMINFO, encoding="utf-8")
    (root / "etc").mkdir()
    (root / "etc" / "machine-id").write_text("ab" * 16 + "\n", encoding="utf-8")
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    monkeypatch.setattr(rigscan, "measure_bandwidth", lambda root="": None)

    def install(answer: Answer) -> rigfile.Saved:
        def run(argv: Sequence[str], *, bound: float = 0.0) -> Answer:
            if argv[0] == "nvidia-smi" and argv[1] == FIRST_QUERY:
                return answer
            if argv[0] == "lscpu":
                return LSCPU, None
            return None, None

        monkeypatch.setattr(rigscan, "_run", run)
        reading = rigscan.scan(weights_dir=str(tmp_path / "weights"), root=str(root))
        return rigfile.save(rigfile.LOCAL, reading)

    return install


@pytest.mark.parametrize(
    "answer",
    [(None, None), (None, "nvidia-smi --query-gpu exited 9"), (ONE_READABLE, None)],
    ids=["nvidia-smi-absent", "nvidia-smi-failed", "unreadable-row"],
)
def test_an_undetermined_card_list_is_no_move_and_keeps_the_record(
    read: Read, answer: Answer
) -> None:
    read((TWO_CARDS, None))

    saved = read(answer)
    assert not saved.now.scan.gpus_determined
    assert saved.before is not None and len(saved.before.cards) == 2

    assert rigfile.moved(saved.before, saved.now) == (), (
        "a card list nvidia-smi could not give read as cards pulled"
    )
    assert saved.kept
    kept = rigfile.read(rigfile.LOCAL)
    assert kept is not None and len(kept.cards) == 2, (
        "the record that knew two cards was replaced by one that did not"
    )


def test_a_determined_card_list_that_lost_a_card_is_still_a_move(read: Read) -> None:
    read((TWO_CARDS, None))
    saved = read((TWO_CARDS.splitlines(keepends=True)[0], None))
    assert saved.before is not None and not saved.kept
    found = rigfile.moved(saved.before, saved.now)
    assert [m.field for m in found] == ["card 1"], found
    assert rigfile.is_hardware(found[0])
