"""The cross-rig claim, turned into something that can refuse.

The width-16 ramp read srv2 at 15.42x of a single stream and srv1 at 3.76x, and
the campaign README concludes from it that "the gap is hardware, not
configuration" (`records/evidence/calibration-2026-08-19/README.md:983-987`),
resting on one controlled flag: `--enforce-eager` on both hosts. The owner's
hunch on record is the opposite — "something feels off — maybe config".

**Hardware may well be right. Nothing recorded can say so.** The journal the
sentence was read off, `d7-ramp.jsonl`, is twelve rows of seventeen keys and
names no card, no driver, no launcher, no engine build, no weights digest and
no engine config; there is not a single launch row in it. Under ADR-0026 lens 3
a claim nothing verifies is worse than dead weight, so this file makes the claim
a predicate instead of a sentence.

Three arms here, and none of them touches a rig:

* The launchers hand the engine the same arguments. srv1 runs `vllm serve` from
  a pip install and srv2 runs the `v0.26.0` container; the two code paths build
  their command lines separately, so "same flags" was an assumption about two
  strings nobody had compared. It holds at HEAD, and now stays held.
* :func:`cross_host_contrast` refuses a contrast whose two sides are not
  comparable — different weights, different engine build, or a card that never
  got named — instead of returning two numbers that look like an answer.
* The 2026-08-20 claim itself, read through that function off the journal it
  was made from. It is `xfail(strict=True)` because the function refuses: the
  rows carry no identity at all. That marker is the issue's own flip. The rig
  arm points :data:`CROSS_RIG_JOURNAL` at a journal with launch rows in it, and
  a strict xfail that passes fails the suite — so the marker comes off in the
  same commit that earns it.

What this file does NOT do is decide what the gap is. It makes the question
answerable by a measurement that carries its own conditions.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"

#: The journal the 2026-08-20 claim was read off. The rig arm repoints this at
#: its own journal, and the xfail below turns XPASS when it does.
CROSS_RIG_JOURNAL = (
    REPO / "records" / "evidence" / "calibration-2026-08-19" / "d7-ramp.jsonl"
)
#: The one cell the claim rests on: one model, one width, two hosts.
CROSS_RIG_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"
CROSS_RIG_WIDTH = 16

#: What a launch row must carry, on each host, for a contrast between two hosts
#: to mean anything. #329 filed the middle one as `engine_version`; #326 landed
#: it as `identity.serving_build`, which is what the row actually says.
#:
#: `weights_sha256` and `serving_build` must be EQUAL across the two hosts —
#: they are the things the contrast holds fixed. `gpu_name` must merely be
#: present on each, because the two cards differing is the hypothesis under
#: test, and a contrast that demanded equal cards could never be run.
EQUAL_ACROSS_HOSTS = ("weights_sha256", "serving_build")
PRESENT_ON_EACH = ("gpu_name",)

#: The environment variable the pip launcher exports and the container has no
#: use for: it puts `vllm` on the PATH of a non-login shell.
LAUNCHER_ONLY = ("PATH",)

_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vllm() -> Any:
    return _by_path("crossrig_vllm", SERVING / "backends" / "vllm.py")


# --------------------------------------------------------------------------
# Arm 1 — the two launchers
# --------------------------------------------------------------------------


def _engine_arguments(command: str, after: str) -> list[str]:
    """The tokens the engine itself is handed, from either launcher's line.

    pip's line continues into a shell redirect (`> /tmp/vllm-serving.log`); the
    container's does not, because the container is not started by a shell.
    """
    tokens = shlex.split(command)
    assert after in tokens, f"{after!r} is not in {command!r}"
    start = tokens.index(after) + 1
    end = tokens.index(">") if ">" in tokens else len(tokens)
    assert end > start, f"no engine arguments after {after!r} in {command!r}"
    return tokens[start:end]


def _environment(command: str) -> dict[str, str]:
    """Every `NAME=value` in a launcher's line, however it is passed.

    pip exports them into the shell that starts the process; docker passes `-e`
    pairs to a process whose parent is the daemon. Both arrive as one token.
    """
    found = {}
    for token in shlex.split(command):
        match = _ASSIGNMENT.match(token.rstrip(";"))
        if match:
            found[match.group(1)] = match.group(2)
    return found


def _command(vllm: Any, monkeypatch: pytest.MonkeyPatch, how: str) -> str:
    """The line `_start` would run on a host whose launcher is ``how``."""
    monkeypatch.setattr(vllm, "launcher", lambda host: how)
    monkeypatch.setattr(
        vllm.contract,
        "ssh",
        lambda host, command, timeout=None: "ready" if "/health" in command else "",
    )
    started = vllm._start(
        "rig",
        CROSS_RIG_MODEL,
        {
            "max_model_len": 8192,
            "max_num_seqs": CROSS_RIG_WIDTH,
            "gpu_memory_utilization": 0.85,
            "flags": ["--enforce-eager"],
            "env": {"FLASHINFER_DISABLE_VERSION_CHECK": "1"},
        },
    )
    assert started["launcher"] == how
    command = started["command"]
    assert isinstance(command, str)
    return command


def test_the_two_launchers_hand_the_engine_the_same_arguments(
    vllm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """srv1's pip install and srv2's container are handed identical flags.

    The one uncontrolled difference the 2026-08-20 claim would be most exposed
    to is the launcher, and the two commands are built by two separate branches
    of `_start` — so until this ran, "same flags on both hosts" was a statement
    about two strings that had never been compared. They agree: the same model,
    `--max-model-len`, `--gpu-memory-utilization`, `--max-num-seqs`, `--port`
    and `--enforce-eager`, in the same order, and the same environment once
    PATH — which exists to find the pip binary and means nothing to a container
    — is set aside.

    What this does NOT show is that the two ENGINES behind those flags are the
    same. They are known not to be (pip 0.26.0 on torch 2.11.0+cu130 against the
    `v0.26.0` image), which is why a contrast also has to carry the build.
    """
    pip = _command(vllm, monkeypatch, "pip")
    docker = _command(vllm, monkeypatch, "docker")

    assert _engine_arguments(pip, "serve") == _engine_arguments(
        docker, vllm.CONTAINER_IMAGE
    ), f"the launchers disagree on what the engine is asked for:\n{pip}\n{docker}"

    pip_environment = _environment(pip)
    for name in LAUNCHER_ONLY:
        assert name in pip_environment, (
            f"{name} is declared as the pip launcher's only extra export and "
            "it is not in its command line any more"
        )
        pip_environment.pop(name)
    assert pip_environment == _environment(docker), (
        f"the launchers disagree on the engine's environment:\n{pip}\n{docker}"
    )
    assert pip_environment, "both launchers set no environment; nothing compared"


# --------------------------------------------------------------------------
# Arm 2 — a contrast that can refuse
# --------------------------------------------------------------------------


def _rows(journal: Path) -> list[dict[str, Any]]:
    rows = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def cross_host_contrast(journal: Path, model: str, width: int) -> dict[str, Any]:
    """Two hosts' speedups at one width, or the field that refuses them.

    Pure: a path in, a dict out, no host touched. Either
    ``{"speedups": {host: figure}, "refused": None}`` — and only when both
    sides are comparable — or ``{"refused": "<what is missing>"}``.

    The identity is read off the LAUNCH row rather than the ramp row: one
    launch serves every token count at a width, so that is where the engine,
    the weights and the card are recorded (#326), and a journal with no launch
    row in it — which is every journal written before then — can say nothing
    about what its figures ran on.
    """
    speedups: dict[str, float] = {}
    launches: dict[str, dict[str, Any]] = {}
    for row in _rows(journal):
        if row.get("model") != model or row.get("configured_width") != width:
            continue
        host = row.get("host")
        if not isinstance(host, str):
            continue
        if row.get("metric") == "launch":
            launches[host] = row
        elif row.get("max_speedup_vs_n1") is not None:
            speedups[host] = float(row["max_speedup_vs_n1"])
    if len(speedups) != 2:
        return {"refused": f"two hosts' ramp rows ({sorted(speedups)})"}
    if set(launches) != set(speedups):
        return {"refused": "no launch row"}

    identity = {host: (row.get("identity") or {}) for host, row in launches.items()}
    for field in PRESENT_ON_EACH:
        unnamed = sorted(host for host in identity if not identity[host].get(field))
        if unnamed:
            return {"refused": f"{field} ({unnamed})"}
    for field in EQUAL_ACROSS_HOSTS:
        stated = {
            host: launches[host].get(field, identity[host].get(field))
            for host in launches
        }
        if None in stated.values():
            silent = sorted(host for host, value in stated.items() if value is None)
            return {"refused": f"{field} ({silent})"}
        if len(set(stated.values())) != 1:
            return {"refused": f"{field} ({stated})"}
    return {"speedups": dict(sorted(speedups.items())), "refused": None}


def _journal(
    path: Path,
    identity: dict[str, dict[str, Any]] | None = None,
    launch: dict[str, dict[str, Any]] | None = None,
    speedups: dict[str, float] | None = None,
) -> Path:
    """A two-host width-16 journal: one launch row and one ramp row per host."""
    shared = {
        "gpu_name": "NVIDIA GeForce RTX 3060",
        "serving_build": "vllm 0.26.0",
    }
    rows = []
    for host, speedup in (speedups or {"srv1": 3.76, "srv2": 15.42}).items():
        block = {**shared, **(identity or {}).get(host, {})}
        rows.append(
            {
                "phase": "ramp",
                "metric": "launch",
                "host": host,
                "model": CROSS_RIG_MODEL,
                "configured_width": CROSS_RIG_WIDTH,
                "identity": {k: v for k, v in block.items() if v is not ...},
                "weights_sha256": "a" * 64,
                **(launch or {}).get(host, {}),
            }
        )
        rows.append(
            {
                "phase": "ramp",
                "metric": "ramp",
                "host": host,
                "model": CROSS_RIG_MODEL,
                "configured_width": CROSS_RIG_WIDTH,
                "tokens": 475,
                "max_speedup_vs_n1": speedup,
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_a_cross_host_contrast_refuses_when_identity_differs_or_is_missing(
    tmp_path: Path,
) -> None:
    """The contrast is returned only when the two sides are comparable.

    Every refusal below is a way the 2026-08-20 sentence could be wrong without
    anyone noticing: two hosts serving different checkpoints, two hosts running
    different engine builds, or a row that never said which card it ran on. The
    accepting case is here too, because a function that only ever refuses is not
    a check — it is a broken function.
    """
    complete = cross_host_contrast(
        _journal(tmp_path / "complete.jsonl"), CROSS_RIG_MODEL, CROSS_RIG_WIDTH
    )
    assert complete == {
        "speedups": {"srv1": 3.76, "srv2": 15.42},
        "refused": None,
    }, complete

    # The cards DIFFERING is the hypothesis, not a refusal.
    differing_cards = cross_host_contrast(
        _journal(
            tmp_path / "cards.jsonl",
            identity={"srv1": {"gpu_name": "NVIDIA GeForce GTX 1660 SUPER"}},
        ),
        CROSS_RIG_MODEL,
        CROSS_RIG_WIDTH,
    )
    assert differing_cards["refused"] is None, differing_cards

    refusals = {
        "gpu_name": _journal(
            tmp_path / "unnamed.jsonl", identity={"srv2": {"gpu_name": None}}
        ),
        "serving_build": _journal(
            tmp_path / "build.jsonl",
            identity={"srv1": {"serving_build": "vllm 0.27.0"}},
        ),
        "weights_sha256": _journal(
            tmp_path / "weights.jsonl", launch={"srv2": {"weights_sha256": "b" * 64}}
        ),
    }
    for field, journal in refusals.items():
        answer = cross_host_contrast(journal, CROSS_RIG_MODEL, CROSS_RIG_WIDTH)
        assert "speedups" not in answer, (field, answer)
        assert answer["refused"].startswith(field), (field, answer)

    missing = tmp_path / "no-launch.jsonl"
    missing.write_text(
        "\n".join(
            line
            for line in _journal(tmp_path / "full.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if '"metric": "ramp"' in line
        )
        + "\n",
        encoding="utf-8",
    )
    assert cross_host_contrast(missing, CROSS_RIG_MODEL, CROSS_RIG_WIDTH) == {
        "refused": "no launch row"
    }

    # The journal the claim was actually read off, in place.
    read_off = cross_host_contrast(CROSS_RIG_JOURNAL, CROSS_RIG_MODEL, CROSS_RIG_WIDTH)
    assert read_off == {"refused": "no launch row"}, read_off


# --------------------------------------------------------------------------
# Arm 3 — the claim itself
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="2026-08-21: owed — is the width-16 gap hardware or configuration? "
    "The journal it was read off names no card, engine build or weights on any "
    "row, so nothing recorded can tell the two apart (#329).",
)
# The name #329 gives this check is one character past the line limit and is
# quoted in the issue's definition of done, so the limit yields, not the name.
def test_the_2026_08_20_cross_rig_claim_holds_only_on_a_journal_with_identity_rows() -> (  # noqa: E501
    None
):
    """srv1 below srv2 at width 16, off a journal that says what each ran on.

    Red because the journal carries no launch row, not because the numbers
    disagree — 3.76 and 15.42 are in the file and neither is in doubt. What is
    missing is everything that would let a reader tell a card apart from a
    container image. The rig arm of #329 writes one width-16 ramp and one launch
    row per host, points :data:`CROSS_RIG_JOURNAL` at it, and takes this marker
    off in the same commit.
    """
    contrast = cross_host_contrast(CROSS_RIG_JOURNAL, CROSS_RIG_MODEL, CROSS_RIG_WIDTH)
    assert contrast["refused"] is None, (
        f"the cross-rig contrast cannot be read: {contrast['refused']}"
    )
    speedups = contrast["speedups"]
    assert len(speedups) == 2, speedups
    slower, faster = sorted(speedups.items(), key=lambda pair: pair[1])
    assert slower[0] == "srv1" and faster[0] == "srv2", speedups
