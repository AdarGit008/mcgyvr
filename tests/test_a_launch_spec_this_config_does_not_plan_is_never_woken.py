"""A file mcgyvr no longer writes is a file mcgyvr must never start.

RED. ``d8c5cf0a`` gave ``emit`` the ability to cut one host into several launch
specs, and the day it did, three things stopped agreeing about what
``compose.<host>.yml`` means.

* ``emit`` writes ``compose.<host>.<model>.yml`` for each alternative and
  **leaves the old ``compose.<host>.yml`` on disk**. Nothing deletes it; the
  writer only writes what it plans.
* ``emit --check`` reads only *planned* paths — its own docstring says "files
  this config says nothing about are not read and not reported" — so it is
  **CLEAN** with that file sitting there.
* ``serving.cards`` **hardcodes** ``compose.<host>.yml``, finds it, and
  ``wake.compose_for`` hands it to the door.

So ``mcgyvr serve wake --host rig``, and the automatic ``Waker`` the moment
``serving.enable_sleep_wake`` is on, starts a **stale multi-service compose
file**: the exact card overcommit ``hold_together`` used to refuse at emit time,
launched on a rig, with nothing having said a word. On srv1's own figures that
is 11.83 GiB asked of a 6.00 GiB card — two servers racing for one card, the
second crash-looping under ``restart: unless-stopped`` while the door reports
``NOT ANSWERING`` (``records/plans/handoff.md``, "rig gotchas").

**What this file pins**

1. A card whose directory holds more than one file matching mcgyvr's own naming
   convention for that host is **not woken**. mcgyvr does not guess which of
   them is current, and the one it would have guessed is the stale one.
2. A host emitted as N alternatives is **not "no launch spec"**. Every file is
   found; what is missing is a decision about *which*, and the refusal says so
   rather than claiming mcgyvr never wrote one. (That case is otherwise
   invisible: with three units at 5 GiB on a 12 GiB card the covering is
   ``{A,B}`` and ``{A,C}``, ``compose.<host>.yml`` is never written at all, and
   the hardcoded name degraded to "no launch spec" for a host ``emit`` had just
   written two files for.)
3. A host that comes up as one file is woken with it, exactly as before — the
   compatibility rule ``d8c5cf0a`` established, and both live rigs.
4. ``emit --check`` **names** a ``compose.<host>.yml`` this config no longer
   plans. It is not "a file this config says nothing about": it matches
   mcgyvr's own convention, for a rig this ladder still binds, and it is the
   file ``cards`` would have picked up. Reported at drift severity, because the
   consequence is the same one drift has — a rig serving argv nobody is reading.
5. ``emit`` **says** when a host's units did not sum onto the card and were
   therefore written as N alternatives, only one of which is ever up. That
   sentence stands where ``hold_together``'s card refusal used to: the refusal
   is gone (owner's ruling 5, 2026-09-09) and the fact it was about is not.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV, load, parse
from mcgyvr.exits import Exit
from mcgyvr.scan import Scan

#: The host, as both the URL's route and the name the machine calls itself.
HOST = "rig"

#: Two models that each fit the card alone and cannot both be on it: 7.0 + 7.0
#: GiB of a 12 GiB card. srv1's own shape, with the figures declared rather than
#: read out of a GGUF header, because what is under test is the file on disk and
#: not the arithmetic that sized it.
LITE = "lite-7b"
BIG = "big-7b"

WINDOW = 4096


def _config(compose_dir: Path, *, switch: bool = True) -> str:
    return f"""
version: 1
sources:
  rig_lite:
    base_url: "http://{HOST}:8080"
    api: openai
    context_window: {WINDOW}
  rig_big:
    base_url: "http://{HOST}:8081"
    api: openai
    context_window: {WINDOW}
models:
  {LITE}:
    vram_gb: 7.0
    disk_gb: 5.0
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
  {BIG}:
    vram_gb: 7.0
    disk_gb: 5.0
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
ladder:
  tiers:
    - name: local_lite
      source: rig_lite
      model: "{LITE}"
    - name: local_big
      source: rig_big
      model: "{BIG}"
serving:
  compose_dir: {compose_dir}
  enable_sleep_wake: {"true" if switch else "false"}
"""


#: One model on one port: the host that comes up as one file, which is every
#: fleet emitted before ``d8c5cf0a`` and both live rigs today.
def _one_unit_config(compose_dir: Path) -> str:
    return f"""
version: 1
sources:
  rig_lite:
    base_url: "http://{HOST}:8080"
    api: openai
    context_window: {WINDOW}
models:
  {LITE}:
    vram_gb: 7.0
    disk_gb: 5.0
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
ladder:
  tiers:
    - name: local_lite
      source: rig_lite
      model: "{LITE}"
serving:
  compose_dir: {compose_dir}
  enable_sleep_wake: true
"""


Install = tuple[Path, Path, Callable[[str], None]]


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Install:
    """A scanned rig, a config that can be rewritten, and where files land."""
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / f"{HOST}.json").write_text(
        Scan.of(
            host=HOST,
            vram_mib=12288,
            ram_gb=64.0,
            disk_free_gb=900.0,
            cores=10,
            threads=20,
            bandwidth_gbps=41.2,
        ).to_json(),
        encoding="utf-8",
    )
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))

    config = tmp_path / "mcgyvr.yaml"
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))

    out = tmp_path / "compose"
    out.mkdir()

    def declare(text: str) -> None:
        config.write_text(text, encoding="utf-8")

    return out, config, declare


def _emit(out: Path) -> int:
    return main(["emit", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


def _check(out: Path) -> int:
    return main(["emit", "--check", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


def _stale(out: Path) -> Path:
    """The file a host used to come up as, left behind by an earlier emit."""
    path = out / f"compose.{HOST}.yml"
    path.write_text(
        "services:\n"
        f"  {LITE}-8080:\n    image: stale\n"
        f"  {BIG}-8081:\n    image: stale\n",
        encoding="utf-8",
    )
    return path


def test_a_stale_whole_host_file_is_not_what_a_wake_brings_up(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Sev 1 reproduction: two specs written, an old one left, that one woken.

    The stale file is the one shape ``hold_together`` was written to refuse — a
    card asked to hold both units at once — and every guard between the config
    and the rig has a reason not to look at it. Waking must not.
    """
    out, config, declare = install
    declare(_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()
    stale = _stale(out)

    from mcgyvr.serving import cards
    from mcgyvr.wake import compose_for

    card = cards(load(config))["local_big"]
    chosen = compose_for(card)

    assert chosen != stale, (
        f"a wake would have started {stale}, which this config no longer writes "
        "and which holds both units on one card"
    )
    assert chosen is None, (
        f"mcgyvr picked {chosen} out of {sorted(p.name for p in out.iterdir())}. "
        "Which of a host's alternatives is the current one is not a question "
        "the config answers, and guessing is how the wrong weights get served"
    )


def test_a_wake_that_cannot_say_which_spec_starts_nothing_and_says_so(
    install: Install,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No door is spawned, and the operator is told why — not left with silence."""
    out, config, declare = install
    declare(_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()
    _stale(out)

    import mcgyvr.wake as wake

    spawned: list[tuple[str, ...]] = []

    def spawn(argv: Sequence[str], **_: object) -> int:
        spawned.append(tuple(argv))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)

    waker = wake.for_config(load(config))
    assert waker is not None
    assert waker.wake_for("local_big") is False
    assert spawned == [], f"a stale launch spec was started: {spawned}"

    said = capsys.readouterr().err
    assert HOST in said and "compose" in said, (
        f"nothing said a word about the ambiguity: {said!r}. A card that is not "
        "woken because mcgyvr cannot tell which file is current is a rung that "
        "declines for a reason only the directory listing holds"
    )


def test_a_host_of_alternatives_is_not_no_launch_spec(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both files are found. What is missing is a decision, and it says which.

    Under the hardcoded name this host had no ``compose.rig.yml`` at all, so a
    wake reported "this config holds no launch spec to bring up" — about a host
    ``emit`` had just written two launch specs for.
    """
    out, config, declare = install
    declare(_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()

    from mcgyvr.serving import cards
    from mcgyvr.wake import WakeError, wake

    card = cards(load(config))["local_big"]
    assert len(card.specs) == 2, card.specs
    assert {path.name for path in card.specs} == {
        f"compose.{HOST}.{LITE}.yml",
        f"compose.{HOST}.{BIG}.yml",
    }

    with pytest.raises(WakeError) as raised:
        wake(load(config), HOST)
    said = str(raised.value)
    assert "no launch spec" not in said, said
    assert LITE in said and BIG in said, said


def test_a_host_that_comes_up_as_one_file_is_still_woken_with_it(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """The compatibility rule: nothing on disk moves, and nothing here changes."""
    out, config, declare = install
    declare(_one_unit_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()

    from mcgyvr.serving import cards
    from mcgyvr.wake import compose_for

    card = cards(load(config))["local_lite"]
    assert compose_for(card) == out / f"compose.{HOST}.yml"


def test_emit_check_names_a_file_this_config_no_longer_plans(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean check over a loaded gun is the whole of how this stayed hidden."""
    out, _, declare = install
    declare(_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()
    stale = _stale(out)

    code = _check(out)
    said = capsys.readouterr()

    assert code == Exit.MISMATCH, (code, said)
    assert stale.name in said.err, said.err


def test_a_compose_file_for_a_rig_this_ladder_does_not_bind_is_left_alone(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rule that must survive: a directory may hold other rigs' files.

    ``check_all``'s docstring is right about this and it is why the report is
    scoped to hosts the ladder names — calling another machine's compose file a
    drift asks an operator to delete evidence of a rig that is serving.
    """
    out, _, declare = install
    declare(_one_unit_config(out))
    assert _emit(out) == Exit.OK, capsys.readouterr()
    (out / "compose.elsewhere.yml").write_text("services: {}\n", encoding="utf-8")

    code = _check(out)
    said = capsys.readouterr()

    assert code == Exit.OK, (code, said)
    assert "elsewhere" not in said.err, said.err


def test_emit_says_when_a_host_was_cut_into_alternatives(
    install: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two files where there was one is a fact about the rig, not a detail.

    Only one of them is ever up; ``serve up`` takes one file; and the operator
    who reads "wrote compose.rig.lite-7b.yml / wrote compose.rig.big-7b.yml" and
    nothing else has been told the *result* of a decision nobody announced.
    """
    out, _, declare = install
    declare(_config(out))

    code = _emit(out)
    said = capsys.readouterr()

    assert code == Exit.OK, said
    warned = said.err + said.out
    assert "alternative" in warned, warned
    assert LITE in warned and BIG in warned, warned


def test_the_units_of_one_launch_spec_are_not_warned_about() -> None:
    """A host that comes up as one has nothing to say, and says nothing.

    A warning printed for every emit is a warning nobody reads by the second
    week, which is the whole reason ``hold_together`` refused rather than warned
    in the first place.
    """
    from mcgyvr.serving import hold_together, units_for

    scan = Scan.of(
        host=HOST,
        vram_mib=12288,
        ram_gb=64.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )
    config = parse(_one_unit_config(Path("/nowhere")))
    units = units_for(config, {HOST: scan}, specs=(), ctx_per_slot=WINDOW)

    assert hold_together(units, {HOST: scan}) == ()
