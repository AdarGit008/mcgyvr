"""The sweep drivers' TSV, read the way a person reads it — and not the way the
journals are read.

``records/evidence/**/*.tsv`` is what ``lcp_sweep_31-08-2026.py`` and
``vllm_sweep_31-08-2026.py`` print: ``### `` marker lines, then rows of
``host \\t label \\t kind \\t k=v...``. It is **not** a journal, and the one habit
that must not travel here is last-write-wins per label. ``run.py:93``'s journals
are append-only and keyed by label; these files repeat a label under every arm.
``2026-09-01-bandwidth-and-ncmoe-floor/srv1-nomma-dp4a-ab.tsv`` carries
``d3b np=8 ctx_slot=2048 c=16384 ncmoe=0`` eight times — four rows under each of
two images — distinguished by nothing but file order and a ``###`` comment. A
reader that collapses by label keeps the second arm and discards the first
without saying so, which is an A/B silently becoming one arm.

So a :class:`Row` remembers its line number and the marker it sits under, and
nothing in this module deduplicates.
"""

from __future__ import annotations

import hashlib
import itertools
import random
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"

_KV = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)


def _pairs(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in tokens:
        match = _KV.match(token)
        if match:
            out[match.group(1)] = match.group(2)
    return out


@dataclass(frozen=True)
class Row:
    """One printed line, with the marker it was printed under."""

    lineno: int
    host: str
    label: str
    kind: str
    fields: dict[str, str]
    tail: tuple[str, ...]
    marker: str

    @property
    def n(self) -> int | None:
        return int(self.kind[2:]) if self.kind.startswith("n=") else None

    @property
    def tag(self) -> str:
        """The cell tag — the label's first word, e.g. ``A2-d3b``."""
        return self.label.split(" ", 1)[0]

    @property
    def cell(self) -> str:
        """The tag with any ``ARM-`` prefix removed, so arms can be aligned."""
        head, sep, rest = self.tag.partition("-")
        return rest if sep and re.fullmatch(r"[AB][0-9]", head) else self.tag

    def num(self, key: str) -> float:
        value = self.fields.get(key)
        assert value is not None, f"line {self.lineno}: no {key}= on {self.label!r}"
        return float(value)

    def frac(self, key: str) -> tuple[int, int]:
        """``failed=3/8`` -> ``(3, 8)``."""
        value = self.fields.get(key)
        assert value is not None, f"line {self.lineno}: no {key}= on {self.label!r}"
        left, _, right = value.partition("/")
        return int(left), int(right)

    def draw(self) -> tuple[float, float]:
        """The work this row actually did.

        Two rows are comparable only if this matches. The prompt lengths come
        from a per-process counter, so a cell that ran levels ``1,2,4,8`` drew
        different work than one that ran ``1,4,8`` — measured at up to 6.2%
        apart on nominally identical stock cells.
        """
        return (self.num("ptok"), self.num("otok"))


@dataclass(frozen=True)
class Sweep:
    path: Path
    rows: tuple[Row, ...]
    markers: tuple[tuple[int, str], ...]

    def levels(self) -> list[Row]:
        return [r for r in self.rows if r.n is not None]

    def of_kind(self, kind: str) -> list[Row]:
        return [r for r in self.rows if r.kind == kind]

    def stamp(self, word: str) -> dict[str, str]:
        """The k=v pairs of the LAST ``### <word> ...`` marker."""
        found: dict[str, str] = {}
        for _, line in self.markers:
            parts = line.removeprefix("###").split()
            if parts and parts[0] == word:
                found = _pairs(parts[1:])
        return found

    def stamps(self, word: str) -> list[dict[str, str]]:
        """Every ``### <word> ...`` marker, in file order."""
        out: list[dict[str, str]] = []
        for _, line in self.markers:
            parts = line.removeprefix("###").split()
            if parts and parts[0] == word:
                out.append(_pairs(parts[1:]))
        return out

    def stamped_before(self, row: Row, word: str) -> dict[str, str]:
        """The nearest preceding ``### <word>`` — what a per-arm re-stamp means."""
        found: dict[str, str] = {}
        for lineno, line in self.markers:
            if lineno > row.lineno:
                break
            parts = line.removeprefix("###").split()
            if parts and parts[0] == word:
                found = _pairs(parts[1:])
        return found


def read(path: Path) -> Sweep:
    rows: list[Row] = []
    markers: list[tuple[int, str]] = []
    marker = ""
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith("###"):
            marker = line
            markers.append((lineno, line))
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        host, label, kind, *rest = parts
        rows.append(
            Row(
                lineno,
                host,
                label,
                kind,
                _pairs(rest),
                tuple(p for p in rest if not _KV.match(p)),
                marker,
            )
        )
    return Sweep(path, tuple(rows), tuple(markers))


#: What a row must name about the machine that produced it. Every one of these
#: has moved under this project with no record saying so: RAM swapped between
#: rigs twice in six days, a hard lock wiped srv1's BIOS profile and PL1 read
#: 95 W at 05:23 and 4095 W at 05:57, srv1's max clock went 4800 -> 4600
#: unattended, and the GSP reserve differs per boot. A figure that cannot name
#: them is a figure about an afternoon, not about a rig.
RIG_FIELDS = (
    "cpu_max_mhz",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "driver",
    "gpu_reserve_mib",
)


def rig_gaps(stamp: dict[str, str]) -> list[str]:
    return [f for f in RIG_FIELDS if not (stamp.get(f) or "").strip()]


#: README.md's check. Over 200 GENERATED prompts, not over source text: the
#: source hash moves under a `ruff format` pass and did so in 90635351, which
#: would void a live cross-engine comparison over a whitespace commit.
WORKLOAD_DIGEST = "2f2bb7932a0b660653def819"


def workload_digest(driver: Path) -> str:
    source = driver.read_text(encoding="utf-8")
    block = source[source.index("PROMPT_DECILES") : source.index("def sh(")]
    namespace: dict[str, Any] = {
        "itertools": itertools,
        "threading": threading,
        "random": random,
    }
    exec(compile(block, str(driver), "exec"), namespace)
    make = namespace["mkprompt"]
    blob = "".join(f"{w}\x00{t}\x1e" for t, w in (make() for _ in range(200)))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


#: The run these tests specify. Absent until it is performed.
RUN = EVIDENCE / "2026-09-02-srv1-kernel-arms"


def artifact(path: Path, behaviour: str) -> Sweep:
    """The run's artifact, or a RED failure naming the run that produces it.

    ``pytest.fail(pytrace=False)`` and not ``skipif``: ``records/evidence/`` is
    in the tree, so an absent artifact is never an environment accident the way
    an absent ``ruff`` is. A skip here would encode "not doing the run is fine",
    which is the failure ``test_a_rung_that_did_not_run_is_not_a_commit`` exists
    to close.
    """
    import pytest

    if not path.is_file():
        pytest.fail(
            f"{path.relative_to(REPO)} does not exist. {behaviour}", pytrace=False
        )
    return read(path)
