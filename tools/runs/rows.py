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


#: The arm prefixes this campaign puts in front of a cell tag: the ``L``-ladder
#: rungs ``L0``-``L4``, the ``A`` bounds ``A1``/``A3``, and the ``B`` vLLM pair
#: (``lcp-vllm-3-arm-run.md:37-54``). All of them strip, so ``<ARM>-<cell>`` is
#: one labelling convention for every file rather than two that contradict.
ARM_PREFIX = re.compile(r"[ABL][0-9]")


def _stamp_name(lineno: int, line: str) -> str:
    """The stamp's name: the first whitespace token after ``###``.

    Raises rather than reporting "no such stamp". A marker that names nothing
    used to read exactly like a marker that is absent, and the two mean opposite
    things: ``### END`` missing says the run did not close (a lock took the ssh
    pipe with it, which is guideline 7's whole worry), while a malformed ``###``
    says the emitter is broken. A silent ``{}`` merges them.
    """
    parts = line.removeprefix("###").split()
    if not parts:
        raise ValueError(
            f"line {lineno}: {line!r} is a bare ### and names no stamp. A stamp "
            "names itself in the first token after ###; a nameless one is not an "
            "absent stamp, and must not be read as one."
        )
    if _KV.match(parts[0]):
        raise ValueError(
            f"line {lineno}: {line!r} opens with the field {parts[0]!r} where its "
            "name belongs. `### digest=...` is not `### WORKLOAD digest=...`, and "
            "every lookup for it would have returned an empty stamp."
        )
    return parts[0]


def _stamp_fields(lineno: int, line: str) -> dict[str, str]:
    """The stamp's k=v pairs — every token after the name, or an error.

    Rows are tab-separated and a row value may hold spaces; a stamp is split on
    whitespace and a stamp value may not. That difference used to be silent:
    ``### END ... uptime_since=2026-09-01 08:11:08``
    (``records/.../srv1-locktest-ling-60min.tsv:1``) parses as
    ``uptime_since=2026-09-01`` and drops the clock, so START and END compare
    equal across two different moments and the rig check passes on a run whose
    machine state was never actually re-read. A stamp with a loose token is a
    parse error here, not a truncation.
    """
    tokens = line.removeprefix("###").split()[1:]
    loose = [t for t in tokens if not _KV.match(t)]
    if loose:
        raise ValueError(
            f"line {lineno}: {line!r} carries {loose!r}, which is not key=value. "
            "A stamp is split on whitespace, so a value containing a space loses "
            "its tail without saying so — `uptime_since=2026-09-01 08:11:08` "
            "keeps the date and drops the clock. Join the value "
            "(`2026-09-01T08:11:08`), or move it onto a row where a tab-delimited "
            "field may hold spaces."
        )
    return _pairs(tokens)


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
        """The tag with its ``ARM-`` prefix removed, so arms can be aligned.

        Every arm this campaign names is stripped — the ``L``-ladder rungs as
        well as the ``A`` bounds and the ``B`` vLLM pair. Stripping only
        ``[AB][0-9]`` left ``L0-d3b`` and ``L3-d3b`` in different cells, which
        made two files need opposite labelling conventions: one test wants the
        arm in the label (no label shared by two arms) and another wants an
        ``L3`` row to align with the ``L2`` row it is the regression for. With a
        uniform strip both are the same convention — ``<ARM>-<cell>`` on every
        label — and a cell means the same thing in every file.
        """
        head, sep, rest = self.tag.partition("-")
        return rest if sep and ARM_PREFIX.fullmatch(head) else self.tag

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
        """The work this row actually did: tokens in, tokens generated.

        An *outcome*, and not the thing two arms must match on. ``otok`` is
        emitted output, so it moves when the answer moves: the 2026-09-01 A/B
        reads ``otok`` 214 against 221 on one cell at ``temperature: 0``,
        because different kernels give different logits and stop in different
        places. That difference is a finding
        (``test_a_faster_arm_that_answers_differently_has_not_won``), not a
        desync, and a test that demanded equality here would forbid it.

        Use it for statements about a single row's arithmetic — ``prefill/agg``
        is ``ptok/otok`` identically, which is why ``prefill=`` is not a
        measurement. For cross-arm comparability use :meth:`requested`.
        """
        return (self.num("ptok"), self.num("otok"))

    def requested(self) -> tuple[float, float]:
        """The work this row was *asked* for: tokens in, output budget out.

        Guideline 2's quantity, and a different one from :meth:`draw`. The
        prompt lengths come from a per-process counter, so a cell that ran
        levels ``1,2,4,8`` drew different work than one that ran ``1,4,8`` —
        measured at up to 6.2% apart on nominally identical stock cells, larger
        than most effects this campaign is looking for. Two rows are comparable
        only if this matches; what they then *emitted* is the result.

        ``otok_req`` is the per-request output cap the driver asked for. It is
        a plan and is equal across arms by construction; ``otok`` is what came
        back and is not.
        """
        return (self.num("ptok"), self.num("otok_req"))


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
        for lineno, line in self.markers:
            if _stamp_name(lineno, line) == word:
                found = _stamp_fields(lineno, line)
        return found

    def stamps(self, word: str) -> list[dict[str, str]]:
        """Every ``### <word> ...`` marker, in file order."""
        out: list[dict[str, str]] = []
        for lineno, line in self.markers:
            if _stamp_name(lineno, line) == word:
                out.append(_stamp_fields(lineno, line))
        return out

    def stamped_before(self, row: Row, word: str) -> dict[str, str]:
        """The nearest preceding ``### <word>`` — what a per-arm re-stamp means."""
        found: dict[str, str] = {}
        for lineno, line in self.markers:
            if lineno > row.lineno:
                break
            if _stamp_name(lineno, line) == word:
                found = _stamp_fields(lineno, line)
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

#: One artifact, one script that produces it.
#:
#: ``artifact()``'s message is the only instruction a RED reader is given, and
#: it was telling two different stories about one file: ``srv1-moe-slots.tsv``
#: was announced as the output of ``srv1-kernel-arms.sh`` by three tests and of
#: ``srv1-moe-slots.sh`` by a fourth, and ``srv1-vllm-arms.tsv`` likewise. The
#: string is never compared, so nothing broke — which is exactly why it drifted.
#: The campaign's step list runs these as separate sessions, in the order that
#: loses least if srv1 locks (``lcp-vllm-3-arm-run.md:111-128``), so the file
#: names the one step that produces it.
BEHAVIOUR = {
    "srv1-lcpp-arms.tsv": "run tools/runs/srv1-kernel-arms.sh",
    "srv1-moe-slots.tsv": "run tools/runs/srv1-moe-slots.sh",
    "srv1-vllm-arms.tsv": "run tools/runs/srv1-vllm-arms.sh",
    "srv1-llama-bench.tsv": "run tools/runs/srv1-llama-bench.sh",
    "srv1-build-ladder.tsv": "run tools/runs/srv1-build-ladder.sh",
    "srv1-aa-null.tsv": "run tools/runs/srv1-aa-null.sh",
    "srv1-ncmoe-floor.tsv": "run tools/runs/srv1-ncmoe-floor.sh",
}


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


def owed(name: str) -> Sweep:
    """The run's artifact by file name, or the RED failure naming its step.

    Every test reaches an artifact through here, so one file cannot be announced
    as the output of two different scripts depending on which test failed first.
    """
    return artifact(RUN / name, BEHAVIOUR[name])
