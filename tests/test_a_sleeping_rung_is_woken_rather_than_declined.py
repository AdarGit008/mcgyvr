"""A rung whose port refuses the connection is woken and retried, not written off.

RED. Every test in this file fails today, and it fails because the behaviour does
not exist: ``src/mcgyvr/wake.py`` is not written, ``serving.enable_sleep_wake``
is not a schema key, and a refused connection is charged to the rung as an
error. The design is ``records/plans/sleep-wake.md``, approved; this file is its
executable half.

**What happens today.** ``runner._post_json`` turns any ``OSError`` — a refused
connection included — into ``TransportError``. ``drive`` records it against
``mcgyvr.cooldown`` and re-raises; ``attempt`` wraps it as
``DispatchRaisedError``; the run ends ``outcome: error`` with one attempt spent
and the detail *rung ... raised TransportError*. Three of those in a row take the
source out for sixty seconds, which is a decline. Nothing waits, nothing asks
whether the rig could be brought back, and mcgyvr holds the file that would
bring it back.

**What the design rules.** A card that is down and for which *this config's*
``serving.compose_dir`` holds a launch spec ``mcgyvr emit`` wrote is ``asleep``
(D2), and asleep is a queue-and-wake rather than a decline. The instant refusal
is the wake signal (D6, §8.1): mcgyvr does not probe first, because a card that
is up must cost nothing extra and the check *is* the request. The wake goes
through the door and through nothing else (D3), bounded by
``budgets.wake_timeout_s``, and the dispatch that follows spends no attempt —
nothing was asked and nothing answered, which is the rule ``drive`` already
applies to a declined rung.

**Two seams, and only two.** The backend is substituted with
``livejournal.patch_backend`` — the seam this project is built on, one layer
below ``runner.dispatch``, so the hold, the endpoint binding and the rung lookup
all still happen. The rig is substituted at ``mcgyvr.wake.spawn_door``: D3 rules
that a wake is one subprocess of ``python -m mcgyvr.serving.run serve up`` and
that nothing in ``mcgyvr.wake`` runs ``docker`` or ``ssh``, so one seam is the
whole of the rig contact and a machine with no rigs can hold the module to it.
Substituting it is what makes this suite pass, once the feature lands, on a
laptop.

**The card here is srv2's**, two vLLM sources on one RTX 3060 behind ``:8001``
and ``:8002``, because it is the multi-unit card and therefore the harder case:
waking it is waking both rungs at once. Sleeping it is
``tests/test_sleeping_a_card_takes_every_rung_it_serves.py``.

**The engine is not a predicate.** An earlier draft scoped the feature to vLLM
cards and put srv1's llama.cpp rig out of it. The owner dropped that scope on
2026-09-08 (N10) after the wake measurement showed the two engines
indistinguishable — a single vLLM unit woke in 82 s against llama.cpp's 50-128 s
on the same fleet — and after the same measurement found srv2 can serve an
80B-A3B in 97 s under llama.cpp, which is a rung above anything the vLLM-only
ladder could reach. A card is a card; what is on it decides nothing about
whether it may sleep. That is pinned below.

Numbers this file does not pin: ``WAKE_RATIO`` (N1), ``WAKE_SUSTAIN_S`` (N2) and
the three dampers (N3-N5) belong to the pressure-driven wake of §7.3, which on
the live ladder has no candidate at all (§7.7). What is pinned here is the
refusal-driven wake of D6, which is live on day one and is exempt from those
dampers by §7.6 — a dispatch that was actually aimed at a card and refused by
the port is a request, not a ratio's speculation.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

HOST = "srv2"
RUNG_3B = "local_qwen2.5-coder-3b"
RUNG_7B = "local_qwen2.5-coder-7b"

#: The refusal a sleeping rig gives: nothing is listening, so the answer comes
#: back in under a millisecond and carries ``Connection refused``. This is the
#: string ``runner._post_json`` builds from the ``OSError`` urllib raises.
REFUSED = (
    "could not reach http://srv2:8001/v1/chat/completions within 120s: "
    "[Errno 111] Connection refused"
)


def ladder(*, engine: str) -> str:
    """srv2's two rungs, on one card, behind ``engine``.

    ``attempts: 1`` on each tier so that "the retry spends no attempt" is a
    statement the result file can be read for: a rung allowed one attempt that
    was refused and then answered must show one attempt, and a rung that
    charged the refusal has none left to answer with.
    """
    return f"""
version: 1
sources:
  srv2_3b:
    base_url: http://{HOST}:8001
    api: openai
    engine: {engine}
    max_parallel: 2
  srv2_7b:
    base_url: http://{HOST}:8002
    api: openai
    engine: {engine}
    max_parallel: 2
ladder:
  tiers:
    - name: {RUNG_3B}
      source: srv2_3b
      model: qwen2.5-coder-3b
      attempts: 1
    - name: {RUNG_7B}
      source: srv2_7b
      model: qwen2.5-coder-7b
      attempts: 1
"""


def compose_dir(tmp_path: Path, *, with_spec: bool) -> Path:
    """Where this checkout keeps launch specs, holding srv2's or holding none.

    The file name is ``emit_all``'s own convention rather than a literal, so a
    wake that looked somewhere else would fail here rather than in a year on a
    rig: one compose file per host, ``compose.<host>.yml``, because a host is
    what an operator brings up.
    """
    from mcgyvr.emit import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    if with_spec:
        (where / f"{COMPOSE_PREFIX}{HOST}{COMPOSE_SUFFIX}").write_text(
            "services:\n"
            "  qwen7b:\n"
            "    image: vllm/vllm-openai:v0.26.0\n"
            f"    container_name: mcgyvr-{HOST}-qwen7b-8002\n"
            "  qwen3b:\n"
            "    image: vllm/vllm-openai:v0.26.0\n"
            f"    container_name: mcgyvr-{HOST}-qwen3b-8001\n"
            "    depends_on: [qwen7b]\n",
            encoding="utf-8",
        )
    return where


def config_file(
    path: Path,
    *,
    journal: Path,
    specs: Path | None,
    switch: bool | None,
    engine: str = "vllm",
    profile: str | None = None,
) -> Path:
    """A config on disk. ``switch=None`` writes no ``serving:`` block at all.

    ``profile=None`` writes no ``profile:`` key, which loads as ``live``. The
    tests that act on a card pass ``"dev"``: under
    ``records/plans/fleet-identity.md`` a live config that holds launch specs
    acts only on an approved fleet shape, and these tests pin the wake
    mechanism, which a dev run may exercise freely.

    Loaded here rather than left for ``mcgyvr run`` to load, so that a config
    the schema does not know says so at the line that wrote it.
    """
    from mcgyvr.config import load

    text = ladder(engine=engine) + f"journal:\n  dir: {journal}\n"
    if profile is not None:
        text += f"profile: {profile}\n"
    if switch is not None:
        text += "serving:\n"
        text += f"  enable_sleep_wake: {'true' if switch else 'false'}\n"
        if specs is not None:
            text += f"  compose_dir: {specs}\n"
    path.write_text(text, encoding="utf-8")
    load(path)
    return path


def door_log(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Substitute the one subprocess a wake is allowed to make, and record it.

    D3: "A wake is ``python -m mcgyvr.serving.run serve up --host H --compose
    FILE --suffix S``, spawned as a subprocess. ... Nothing in ``mcgyvr.wake``
    runs ``docker`` or ``ssh``." Under the door those two names resolve to shims
    that admit only the host the door was opened for and only a process the door
    started, and ``tests/test_one_door.py`` bans the way round it. So a single
    seam is the whole of this module's contact with a rig, and a test that owns
    it owns everything that could reach a machine.

    Returning ``0`` is the door reporting the card up. What the caller does with
    that — dispatch again, once — is what the tests below read.
    """
    import mcgyvr.wake as wake

    spawned: list[list[str]] = []

    def spawn(argv: Sequence[str], **_: Any) -> int:
        spawned.append(list(argv))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return spawned


def refusing(*, until_call: int) -> tuple[Any, list[str]]:
    """A backend whose port is shut for the first ``until_call`` dispatches.

    The list it returns is every model it was asked for, so a test can say how
    many times the wire was touched independently of how many attempts the run
    thinks it spent. Those two numbers being different is the whole of "the
    retry spends no attempt".
    """
    from mcgyvr.runner import TransportError

    asked: list[str] = []

    def generate(model: str, request: Any) -> Any:
        asked.append(model)
        if len(asked) <= until_call:
            raise TransportError(REFUSED)
        return lj.completion(lj.GOOD_REPLY, request)

    return generate, asked


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME and a capacity rendezvous directory nobody else writes to.

    ``tempfile.tempdir`` is redirected because the slot files, and under this
    design the two clock files beside them (D7), are keyed host-wide by uid: a
    test that used the developer's would read another test's card as busy.
    """
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def run_once(
    tmp_path: Path,
    config: Path,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, Any]]:
    """One ``mcgyvr run`` against ``config``, and the result file it announced."""
    repo = lj.make_repo(tmp_path / f"repo-{name}")
    contract = lj.make_contract(tmp_path / f"impl-{name}.yaml")
    code = lj.main(lj.run_args(contract, repo, config))
    announced = lj.result_path(capsys.readouterr().out)
    return code, json.loads(announced.read_text(encoding="utf-8"))


# --- the switch gates it ------------------------------------------------------


def test_with_the_switch_off_a_refused_port_ends_the_run_exactly_as_it_does_today(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Off is off: the same card, the same spec on disk, and nothing changes.

    Asserted against the run that says nothing at all rather than against a
    literal, so the test cannot go stale if what a refusal does today is ever
    rewritten for another reason: what is pinned is that turning the switch off
    is indistinguishable from not having the feature. This is the half of the
    ruling that makes the default safe — the design's whole safety property is
    that mcgyvr cannot take a card down anonymously or *without being asked*
    (§14), and a switch that gated nothing would leave "asked" meaning nothing.

    A spec IS on disk here, and the engine IS vLLM, so the card would read as
    asleep and be woken if anything but the switch were deciding.
    """
    specs = compose_dir(tmp_path, with_spec=True)
    silent = config_file(
        tmp_path / "silent.yaml",
        journal=tmp_path / "j-silent",
        specs=specs,
        switch=None,
        profile="dev",
    )
    off = config_file(
        tmp_path / "off.yaml",
        journal=tmp_path / "j-off",
        specs=specs,
        switch=False,
        profile="dev",
    )

    generate, asked = refusing(until_call=99)
    lj.patch_backend(monkeypatch, generate)
    spawned = door_log(monkeypatch)

    silent_code, silent_result = run_once(tmp_path, silent, "silent", capsys)
    dispatched_silent = len(asked)
    off_code, off_result = run_once(tmp_path, off, "off", capsys)
    dispatched_off = len(asked) - dispatched_silent

    assert spawned == [], (
        f"the switch is off and a rig was reached anyway: {spawned}. The "
        "feature does not exist for an operator who did not ask for it"
    )
    assert off_code == silent_code
    assert off_result["outcome"] == silent_result["outcome"]
    assert len(off_result["attempts"]) == len(silent_result["attempts"])
    assert [a["verdict"] for a in off_result["attempts"]] == [
        a["verdict"] for a in silent_result["attempts"]
    ]
    assert dispatched_off == dispatched_silent, (
        f"a run with the switch off dispatched {dispatched_off} time(s) and "
        f"one that never heard of the switch {dispatched_silent}: the key is "
        "changing behaviour it was set to false to leave alone"
    )


# --- the wake -----------------------------------------------------------------


def test_a_refused_vllm_card_this_config_holds_a_spec_for_is_woken_not_written_off(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The behaviour the owner gets on day one (§7.7).

    srv2 was slept, the next dispatch at ``http://srv2:8001`` is refused by the
    port, and the card comes back without anyone typing anything. The wake is
    one door run against the *whole* compose file — the card is the file, and
    the file's own ``depends_on`` sequences the two units largest-first, so the
    wake re-runs no fit and re-derives no order (D1, D8).
    """
    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "on.yaml",
        journal=tmp_path / "j",
        specs=specs,
        switch=True,
        profile="dev",
    )
    generate, asked = refusing(until_call=1)
    lj.patch_backend(monkeypatch, generate)
    spawned = door_log(monkeypatch)

    code, result = run_once(tmp_path, config, "wake", capsys)

    assert code == 0, result
    assert result["outcome"] == "accepted", (
        f"a rung whose port was shut ended the run as {result['outcome']!r}: "
        f"{result['detail']}. mcgyvr holds the launch spec that would have "
        "brought the card back and declined the work instead"
    )
    assert result["rung"] == RUNG_3B, "the work went somewhere else instead"
    assert len(asked) == 2, f"the refusal was not retried: {asked}"

    assert len(spawned) == 1, f"expected one door run, saw {spawned}"
    (argv,) = spawned
    assert "mcgyvr.serving.run" in argv, argv
    assert argv[argv.index("serve") + 1] == "up", argv
    assert HOST in argv, argv
    assert str(specs / f"compose.{HOST}.yml") in argv, argv
    assert "--suffix" in argv, (
        "a wake minted no suffix of its own: gate 5 claims a RUN_ID with "
        "O_CREAT|O_EXCL, so two wakes on one day would collide, and so would "
        "a wake with an operator's hand-run `serve up`"
    )
    for forbidden in ("docker", "ssh"):
        assert not any(forbidden in part for part in argv), (argv, forbidden)


def test_the_dispatch_that_follows_a_wake_spends_no_attempt(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing was asked and nothing answered, so nothing was spent (§8.2).

    The rung declares ``attempts: 1``. The wire is touched twice — once to be
    refused, once to be answered — and the run must show *one* attempt, because
    a rung that produced no verdict funded no escalation. That is the rule
    ``drive`` already applies to a declined rung, and the reason it has to hold
    here too is that a refusal charged as a failure would exhaust a one-attempt
    rung on a card that was merely off.

    A wake that *fails* is a different thing and is a real verdict against the
    rung; this test is about the one that lands.
    """
    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "on.yaml",
        journal=tmp_path / "j",
        specs=specs,
        switch=True,
        profile="dev",
    )
    generate, asked = refusing(until_call=1)
    lj.patch_backend(monkeypatch, generate)
    door_log(monkeypatch)

    _, result = run_once(tmp_path, config, "noattempt", capsys)

    assert len(asked) == 2, asked
    assert len(result["attempts"]) == 1, (
        f"two dispatches became {len(result['attempts'])} attempts: "
        f"{result['attempts']}"
    )
    (spent,) = result["attempts"]
    assert spent["verdict"] != "error", spent
    assert "TransportError" not in json.dumps(result), (
        "the refusal that triggered the wake was reported to the caller as a "
        "fault of the rung; the caller is owed the wake, not the socket"
    )


# --- every engine, and what is merely down ------------------------------------


def test_a_llama_cpp_card_is_woken_exactly_as_a_vllm_one_is(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No rig is banned for the engine that serves it (N10, ruled 2026-09-08).

    This is the same config as the wake above with one field changed — every
    source says ``llama.cpp`` instead of ``vllm`` — and it must produce the same
    door run. The wake path is a compose file, ``serve up`` and a ``/v1/models``
    poll; all three are engine-agnostic, and neither engine ever carried a
    branch of its own here (§6). Scoping the feature bought no simplification
    and cost the ladder its only upgrade path, so the scope is gone.

    Pinned as an equality of behaviour rather than as a second set of literals:
    what would regress is somebody re-introducing a predicate on
    ``Source.engine``, and a predicate shows up as a card that is not woken.
    """
    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "lcp.yaml",
        journal=tmp_path / "j",
        specs=specs,
        switch=True,
        engine="llama.cpp",
        profile="dev",
    )
    generate, asked = refusing(until_call=1)
    lj.patch_backend(monkeypatch, generate)
    spawned = door_log(monkeypatch)

    code, result = run_once(tmp_path, config, "lcp", capsys)

    assert code == 0, result
    assert result["outcome"] == "accepted", (
        f"a llama.cpp card whose port was shut ended the run as "
        f"{result['outcome']!r}: {result['detail']}. The engine on the card is "
        "not a reason to decline work mcgyvr holds the launch spec for"
    )
    assert len(asked) == 2, f"the refusal was not retried: {asked}"

    assert len(spawned) == 1, (
        f"expected one door run for a llama.cpp card, saw {spawned}. A "
        "predicate on `source.engine` is exactly what N10 removed"
    )
    (argv,) = spawned
    assert argv[argv.index("serve") + 1] == "up", argv
    assert str(specs / f"compose.{HOST}.yml") in argv, argv
    for forbidden in ("docker", "ssh"):
        assert not any(forbidden in part for part in argv), (argv, forbidden)


def test_a_card_with_no_launch_spec_is_down_rather_than_asleep(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``asleep`` is ``down`` plus a file mcgyvr wrote, and no more than that (D2).

    There is no fourth lifecycle state to store, no field to keep in sync with
    a rig and no third liveness module. The distinction that matters to a
    caller — *can mcgyvr bring this back?* — is answered by *does mcgyvr have
    the file?*, and that is answerable without touching the network.

    It degrades honestly by construction: an api source has no compose file, a
    rig somebody else runs has no compose file, and a config with no
    ``serving.compose_dir`` has no sleeping cards at all. A wake cannot invent
    a unit, because sizing is a judgement a person reviews — ``hold_together``,
    ``--ctx-per-slot``, a measured ``--gpu-memory-utilization`` — and that is
    the clause of §14 that keeps ``emit``'s boundary standing.
    """
    specs = compose_dir(tmp_path, with_spec=False)
    config = config_file(
        tmp_path / "nospec.yaml",
        journal=tmp_path / "j",
        specs=specs,
        switch=True,
        profile="dev",
    )

    from mcgyvr.config import load
    from mcgyvr.serving import cards

    generate, asked = refusing(until_call=99)
    lj.patch_backend(monkeypatch, generate)
    spawned = door_log(monkeypatch)

    card = cards(load(config))[RUNG_3B]
    assert card.host == HOST
    assert card.compose_file is not None
    assert not Path(card.compose_file).exists(), (
        "the fixture was meant to leave this card without a launch spec"
    )

    code, result = run_once(tmp_path, config, "nospec", capsys)

    assert spawned == [], (
        f"a card mcgyvr never wrote a launch spec for was started: {spawned}. "
        "Waking one would be mcgyvr sizing and starting in one act, which is "
        "exactly what emit's boundary forbids"
    )
    assert code == 1 and result["outcome"] == "error", result
    assert len(asked) == 1, asked
