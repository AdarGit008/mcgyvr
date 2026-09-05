"""Verify the harness is the harness we edited — the markers, and nothing else.

**Why this file exists.** This lane spent 1.5 h of rig time on a run whose patch
silently never reached the file: the unchanged harness ran, produced a full set of
plausible readings, and nobody could tell from the output. D8 turned that into a
process rule — assert the marker in the file after writing **and** after the
formatter, then launch — and made it one step, because two steps with a human
between them is exactly how the first one gets skipped.

**Why it no longer launches.** The launch half was the second of four live entry
points to the rigs on 2026-09-02, with its own detached driver, its own trap and
its own release path — none of which stamped rig state, product round or workload
digest. ``python -m mcgyvr.serving.run`` is now the one door: its gate 2
(``src/mcgyvr/serving/gate-scripts/02-rig.py``) runs :func:`verify_markers`
before any step of a campaign whose ``campaign.json`` declares ``"serving":
true`` and refuses, having written nothing, when a marker is missing. So D8's
"one step" still holds — the check and the launch are one invocation — it is just
the door's invocation. Running this file as a script does not launch; it says so
and points at the door.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

#: Every marker is a decision that must be IN THE FILE at launch time, with the
#: decision it encodes named beside it. A marker is not a checksum: it is the
#: smallest string that is present if and only if the decision landed, so a
#: reader can see what would be lost if it were missing.
MARKERS: tuple[tuple[str, str, str], ...] = (
    ("tools/bench/serving/contract.py", "RAMP_TOKENS = 475", "D3"),
    ("tools/bench/serving/contract.py", "PLATEAU_FRACTION = 0.92", "D2"),
    (
        "tools/bench/serving/contract.py",
        "INFERRED_SATURATION_MIN_SPEEDUP = 1.0",
        "D1 — the inferred path only",
    ),
    (
        "tools/bench/serving/contract.py",
        "def saturation(",
        "D1 — the plateau is not a slot limit",
    ),
    (
        "tools/bench/serving/contract.py",
        "speedup <= INFERRED_SATURATION_MIN_SPEEDUP",
        "DE-1 — a curve that never rises is excluded",
    ),
    (
        "tools/bench/serving/contract.py",
        "RAMP_FLOOR_TOKENS_PER_S",
        "BL-4 — the per-request cap scales with the work asked for",
    ),
    (
        "tools/bench/serving/contract.py",
        "def ladder(",
        "#356 — the ladder follows the configured width past 24",
    ),
    (
        "tools/bench/serving/contract.py",
        "PROVENANCE: dict[str, dict[str, str]]",
        "#356 — every constant names the run behind it",
    ),
    (
        "tools/bench/serving/calibrate.py",
        "contract.ladder(width)",
        "#356 — the width matrices are measured past their ceiling",
    ),
    (
        "tools/bench/serving/contract.py",
        '"ramp_repeats": RAMP_REPEATS',
        "D8 — every derived number ships with its parameters",
    ),
    (
        "tools/bench/serving/contract.py",
        '"repeats": attempts',
        "D6/D7 item 7 — the losing repeat is kept",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        'check["card_idle_before_load"] is True',
        "BL-1 — D4's replacement gate actually gates",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        "def blob_path(",
        "BL-5 — the child is identified by the blob it serves",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        '"keep_alive": -1',
        "BL-6 — the co-resident neighbour outlives the ramp",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "def declared_slots(",
        "E5 — the width, with its provenance",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "def launched_width(",
        "E5 revised — read off the host's own argv, not off our variable",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "ancestor={CONTAINER_IMAGE}",
        "E8 — the container filter is pinned to the tag we launch",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "start_seconds",
        "D6/D7 item 7 — START_TIMEOUT_S gets a calibration point",
    ),
    ("tools/bench/observed.py", "ELIDE_BY_NAME", "D5"),
    ("tools/bench/observed.py", "MAX_INLINE_ITEMS = 4096", "D5 — the backstop"),
)
#: A marker this list used to carry — ``("tools/bench/serving/launch.py",
#: "wait $CHILD", "the interrupt path — a foreground phase defers the trap")``
#: — is retired with the launch path it certified. The interrupt path now
#: belongs to the door's gate 7
#: (``src/mcgyvr/serving/gate-scripts/07-teardown.py``), which is checked by a
#: test rather than by a substring.

#: Markers that must NOT be present — a withdrawn thing is only withdrawn if it
#: is gone. Checked in the same pass, because "we removed it" is exactly the
#: claim a stale file makes look true.
#:
#: **Matched against CODE, not against the file.** The first version was a plain
#: substring test and it refused this very launch, because
#: ``BATCHING_SPEEDUP = 2.0`` appears in the docstring explaining what D1
#: replaced it with. A record saying what a constant used to be is the opposite
#: of the defect this list looks for, and a check that cannot tell a definition
#: from a mention of one pushes every author toward deleting the explanation.
#: So a comment or docstring line is not a hit.
WITHDRAWN: tuple[tuple[str, str, str], ...] = (
    (
        "tools/bench/serving/backends/ollama.py",
        "MIN_VRAM_FRACTION = 0.8",
        "D4 — the withdrawn gate must not still be a constant",
    ),
    (
        "tools/bench/serving/contract.py",
        "BATCHING_SPEEDUP = 2.0",
        "D1 — renamed and re-valued",
    ),
    (
        "tools/bench/serving/contract.py",
        "rate >= 0.95 * best",
        "D2 — the inline threshold is a named constant now",
    ),
    (
        "tools/bench/serving/contract.py",
        '"batches":',
        "D1 — retired",
    ),
)


def code_lines(text: str) -> list[str]:
    """The lines that are code, with comment and docstring lines dropped.

    Deliberately crude — line-oriented, not a parse. It has one job: stop a
    docstring that NAMES a withdrawn constant from reading as that constant
    still existing.
    """
    triple_double = chr(34) * 3
    triple_single = chr(39) * 3
    out: list[str] = []
    in_doc = False
    for raw in text.splitlines():
        line = raw.strip()
        fences = line.count(triple_double) + line.count(triple_single)
        if in_doc:
            if fences:
                in_doc = False
            continue
        if line.startswith("#"):
            continue
        if fences == 1:
            in_doc = True
            continue
        out.append(line)
    return out


def verify_markers(repo: Path) -> list[str]:
    """Every marker, against the files under ``repo`` as they are on disk right now.

    Returns the problems — ``<path>: MISSING '<marker>' — <decision>`` for a
    decision that has not landed, ``STILL PRESENT`` for a withdrawn one that is
    still code — or an empty list. Takes the repo rather than reading a global so
    the door can hold a throw-away copy of the tree to the same list, and a test
    can break one marker on purpose and watch the refusal name it.
    """
    problems: list[str] = []
    for path, marker, decision in MARKERS:
        text = (repo / path).read_text(encoding="utf-8")
        if marker not in text:
            problems.append(f"{path}: MISSING {marker!r} — {decision}")
    for path, marker, decision in WITHDRAWN:
        code = code_lines((repo / path).read_text(encoding="utf-8"))
        hit = next((line for line in code if marker in line), None)
        if hit is not None:
            problems.append(
                f"{path}: STILL PRESENT {marker!r} — {decision} (at: {hit[:70]!r})"
            )
    return problems


def check(label: str) -> list[str]:
    """:func:`verify_markers` over this checkout, each problem tagged ``[label]``.

    Kept because the serving tests read the check through this name and label
    the pass they are asking about (``after writing``, ``after ruff format``).
    """
    return [f"[{label}] {problem}" for problem in verify_markers(REPO)]


def main(argv: list[str] | None = None) -> int:
    """Refuse: this file verifies, the door launches."""
    del argv
    problems = check("on disk")
    for line in problems:
        print(f"  {line}", file=sys.stderr)
    print(
        "tools/bench/serving/launch.py no longer launches anything. The marker "
        "check runs at gate 2 of the door (src/mcgyvr/serving/gate-scripts/"
        "02-rig.py) before every step of a serving campaign; start the run "
        "there, and let its usage name the arguments:\n"
        "  python -m mcgyvr.serving.run --help",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
