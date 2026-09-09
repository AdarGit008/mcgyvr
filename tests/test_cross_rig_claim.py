"""The cross-rig claim, turned into something that can refuse.

The width-16 ramp read srv2 at 15.42x of a single stream and srv1 at 3.76x, and
the campaign README concludes from it that "the gap is hardware, not
configuration"
(`archive/docs/archive/evidence-prose/calibration-2026-08-19/README.md:983-987`),
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
* The 2026-08-20 claim itself, read through that function. It stood as
  `xfail(strict=True)` from 2026-08-22, because the journal it was made from
  carries no identity at all and the function refuses it. **The marker came off
  on 2026-08-23**, when #329's rig arm wrote a journal that says what each side
  ran on: `records/evidence/2026-08-23-cross-rig/`, one width-16 ramp and one
  launch row per host, both launched through the container.

And one arm that is neither: the launcher a run DECLARES. srv1 holds both a pip
install and the same image digest srv2 pulls, and detection returns `pip` for
any host answering `command -v vllm` — so the contrast could not be put on one
launcher without a seam, and `serving_build` would not have caught the mismatch
(both answer `vllm 0.26.0`, which is the package's version, not the build's).

What this file does NOT do is decide what the gap is. It makes the question
answerable by a measurement that carries its own conditions — and the answer it
reached is narrower than the sentence it checks: the deployment is out, and the
card and the driver, which move together across these two rigs, are not
separated by anything here.
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

#: The journal the contrast is read off: #329's rig arm, 2026-08-23. It replaced
#: `calibration-2026-08-19/d7-ramp.jsonl`, which the 2026-08-20 claim was made
#: from and which :func:`cross_host_contrast` refuses for `no launch row` — that
#: refusal is still asserted, on the old path, in arm 2.
CROSS_RIG_JOURNAL = (
    REPO / "records" / "evidence" / "2026-08-23-cross-rig" / "ramp.jsonl"
)

#: The journal the 2026-08-20 sentence was read off. Kept as a constant rather
#: than deleted: "the claim's own journal cannot support it" is a property of
#: this tree that stays true, and a check that stopped asserting it would leave
#: the rig arm looking like a re-measurement rather than a repair.
CLAIMED_FROM_JOURNAL = (
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
# Arm 1b — the launcher a run declares, rather than the one a host detects
# --------------------------------------------------------------------------
#
# Arm 1 shows the two branches build the same flags. It cannot show the two
# engines behind them are the same, and they are not. srv1 now holds BOTH — the
# pip install it always had and, since 2026-08-22, the same `v0.26.0` image
# digest srv2 pulls — and `launcher()` returns `pip` for any host answering
# `command -v vllm`. So the rig arm could not put both hosts on the container
# without a way to declare one, and `serving_build` would not have caught it:
# both launchers answer `vllm 0.26.0`, because that string is the package's
# version and not the build's.


@pytest.fixture
def declaring(vllm: Any) -> Any:
    """The module with its declarations emptied afterwards.

    `DECLARED_LAUNCHERS` is module state on a module-scoped fixture, so a test
    that declared and did not clean up would decide the next test's launcher.
    """
    vllm.DECLARED_LAUNCHERS.clear()
    yield vllm
    vllm.DECLARED_LAUNCHERS.clear()


def _host_answering(declaring: Any, monkeypatch: pytest.MonkeyPatch, *has: str) -> Any:
    """A host that answers the probes for ``has`` and nothing else.

    Records every command it is asked, so a test can show WHERE a launcher
    reached: the digest runs `docker run` or host python, and which one it
    picked is the whole question for a cross-rig contrast.
    """
    seen: list[str] = []

    def ssh(host: str, command: str, timeout: float | None = None) -> str:
        seen.append(command)
        for how in declaring.LAUNCHER_PROBES:
            if command == declaring.LAUNCHER_PROBES[how]:
                return f"/usr/bin/{how}" if how in has else ""
        return ""

    monkeypatch.setattr(declaring.contract, "ssh", ssh)
    return seen


def test_a_host_with_both_launchers_detects_as_pip_and_can_be_declared_docker(
    declaring: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The srv1 case exactly: detection cannot reach the container arm.

    Detection is right for a host with one launcher and wrong for a contrast.
    This is the defect in one assertion pair — the same host, the same probes,
    two answers — and it is why the declaration exists at all.
    """
    _host_answering(declaring, monkeypatch, "pip", "docker")

    assert declaring.launcher("srv1") == "pip"
    declaring.declare_launcher("srv1", "docker")
    assert declaring.launcher("srv1") == "docker"
    declaring.declare_launcher("srv1", None)
    assert declaring.launcher("srv1") == "pip", "un-declaring restores detection"


def test_a_declared_launcher_the_host_cannot_honour_refuses_instead_of_falling_back(
    declaring: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fallback would run the arm on the launcher the declaration excludes.

    And it would record `pip` on the row, which is not even a silent failure —
    it is a row that reads as a deliberate pip cell. The refusal names the
    probe that went unanswered so the fix is the host's, not the config's.
    """
    _host_answering(declaring, monkeypatch, "pip")
    declaring.declare_launcher("srv1", "docker")

    with pytest.raises(declaring.contract.NotCleanError) as raised:
        declaring.launcher("srv1")
    assert "docker" in str(raised.value)
    assert declaring.LAUNCHER_PROBES["docker"] in str(raised.value)


def test_a_launcher_outside_the_two_this_engine_has_is_refused_at_the_declaration(
    declaring: Any,
) -> None:
    """`none` is a detection RESULT, never a declaration.

    Left unchecked it would set a declaration that no probe can verify, and the
    refusal would arrive from `LAUNCHER_PROBES[declared]` as a KeyError at the
    moment the rig was reached rather than at the moment the run was described.
    """
    for bad in ("none", "Docker", ""):
        with pytest.raises(declaring.contract.NotCleanError):
            declaring.declare_launcher("srv1", bad)
    assert declaring.DECLARED_LAUNCHERS == {}


def test_the_declaration_reaches_the_weights_digest_and_not_only_the_launch(
    declaring: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both consumers of `launcher()`, or the arm compares two halves.

    The digest picks where torch runs — inside the image, or on the host — from
    the same call. A declaration honoured by `_start` alone would serve srv1
    from the container and hash its checkpoint with the host's torch: one cell,
    two builds, and the identity block would report the container's.
    """
    seen = _host_answering(declaring, monkeypatch, "pip", "docker")
    declaring.declare_launcher("srv1", "docker")
    declaring._DIGEST_CACHE.clear()

    declaring.weights_sha256("srv1", CROSS_RIG_MODEL)
    ran = [command for command in seen if "mcgyvr-weights-digest" in command]
    assert ran, "the digest reached no host at all"
    assert any("docker run" in command for command in ran), (
        f"the digest ignored the declaration and ran on the host: {ran}"
    )
    declaring._DIGEST_CACHE.clear()


def test_the_launch_row_says_whether_its_launcher_was_declared_or_detected(
    declaring: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two hosts agreeing is a different fact depending on which it was.

    Two detections that agree describe the rigs; one declaration honoured twice
    describes the run. A reader of a cross-host contrast needs to know which,
    and `launcher` alone says the same word either way.
    """

    def ssh(host: str, command: str, timeout: float | None = None) -> str:
        if "/health" in command:
            return "ready"
        return (
            "/usr/bin/docker" if command == declaring.LAUNCHER_PROBES["docker"] else ""
        )

    monkeypatch.setattr(declaring.contract, "ssh", ssh)
    monkeypatch.setattr(declaring, "release", lambda host: None)
    monkeypatch.setattr(declaring, "free_mib", lambda host: 12288)
    monkeypatch.setattr(
        declaring, "declaration_fits", lambda host, model, serve, free: None
    )
    serve = {
        "max_model_len": 8192,
        "max_num_seqs": CROSS_RIG_WIDTH,
        "gpu_memory_utilization": 0.85,
    }

    detected = declaring._start("srv2", CROSS_RIG_MODEL, serve)
    assert (detected["launcher"], detected["launcher_declared"]) == ("docker", False)

    declaring.declare_launcher("srv2", "docker")
    stated = declaring._start("srv2", CROSS_RIG_MODEL, serve)
    assert (stated["launcher"], stated["launcher_declared"]) == ("docker", True)
    assert stated["command"] == detected["command"], (
        "a declaration that agrees with detection must change the record and "
        "not the command"
    )


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
    read_off = cross_host_contrast(
        CLAIMED_FROM_JOURNAL, CROSS_RIG_MODEL, CROSS_RIG_WIDTH
    )
    assert read_off == {"refused": "no launch row"}, read_off


# --------------------------------------------------------------------------
# Arm 3 — the claim itself
# --------------------------------------------------------------------------


# The name #329 gives this check is one character past the line limit and is
# quoted in the issue's definition of done, so the limit yields, not the name.
def test_the_2026_08_20_cross_rig_claim_holds_only_on_a_journal_with_identity_rows() -> (  # noqa: E501
    None
):
    """srv1 below srv2 at width 16, off a journal that says what each ran on.

    **The marker came off on 2026-08-23**, in the commit carrying the rig arm.
    It was `xfail(strict=True)` from 2026-08-22 because the journal the sentence
    was read off holds no launch row: 3.76 and 15.42 were never in doubt and
    what was missing was everything that tells a card apart from a container
    image. The arm wrote one width-16 ramp and one launch row per host with the
    launcher DECLARED docker on both, and this reads the contrast off it.

    What the arm removed, and what it did not. The launcher is out: srv1 had
    only ever been launched from its pip install and now runs the same image
    digest srv2 does, and it read 3.82 against the pip run's 3.76 — so the
    launcher was worth 0.06 of a 4x gap, which is the size of the run-to-run
    noise around it. The card and the driver move together across these two
    rigs and are NOT separated: this check says the contrast is admissible and
    that srv1 is the slower side of it, never what the slower side is made of.
    """
    contrast = cross_host_contrast(CROSS_RIG_JOURNAL, CROSS_RIG_MODEL, CROSS_RIG_WIDTH)
    assert contrast["refused"] is None, (
        f"the cross-rig contrast cannot be read: {contrast['refused']}"
    )
    speedups = contrast["speedups"]
    assert len(speedups) == 2, speedups
    slower, faster = sorted(speedups.items(), key=lambda pair: pair[1])
    assert slower[0] == "srv1" and faster[0] == "srv2", speedups


def test_both_sides_of_the_cross_rig_contrast_ran_the_launcher_the_run_declared() -> (
    None
):
    """The declaration is on the record, not only in the command that ran it.

    `cross_host_contrast` holds the weights and the build equal and says
    nothing about the launcher, because the field it would read did not exist
    when it was written. It exists now, and a contrast whose two hosts were
    DETECTED into the same launcher is a different fact from one whose hosts
    were declared into it — detection returns `pip` for any host answering
    `command -v vllm`, which srv1 does, so a detected srv1 is a pip cell.
    """
    launches = {
        row["host"]: row
        for row in _rows(CROSS_RIG_JOURNAL)
        if row.get("metric") == "launch"
        and row.get("model") == CROSS_RIG_MODEL
        and row.get("configured_width") == CROSS_RIG_WIDTH
    }
    assert sorted(launches) == ["srv1", "srv2"], sorted(launches)
    for host, row in launches.items():
        assert row.get("launcher") == "docker", (host, row.get("launcher"))
        assert row.get("launcher_declared") is True, (
            f"{host} was detected into its launcher, not declared into it: a "
            "host that has both is detected as pip, so this contrast would be "
            "pip against container with nothing on the row saying so"
        )
