"""A sizing says which host memory figure it has not read.

For an engine whose host memory figure is read on the user's machine, mcgyvr
ships no estimate of it (every engine is one or the other, never both; the
test beside this one holds that). While no reading exists, every sizing of a
unit of such an engine says that it has none: when the unit fits, when it is
refused, and in what ``mcgyvr emit`` prints, before it refuses units that
fit host memory one at a time and not together. That holds when the user's own
numbers file sets the figure too, and the sizing then also says that setting
is not used; when that file cannot be read, the sizing names its refusal
instead of refusing the unit. No sizing of a unit of any other engine says it.

The line is read from the sizing module and never restated here: a module
that has no such line says it nowhere. The machines are the invented shapes of
:mod:`tests.machine_shapes`; the models are invented here.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import derived, serving
from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.exits import Exit
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Memory, Scan
from mcgyvr.serving import (
    MODE_RAM_HEADROOM_GB,
    ModelSpec,
    UnitError,
    UnitKey,
    unit_for,
)
from tests import machine_shapes
from tests import numbers_fixture as nf
from tests.test_one_engines_host_memory_figure_is_never_charged_to_another import (
    WINDOW,
    machines,
    spilling,
)

#: The engines that carry a ``runtime_resident_gb`` figure: the one shipped,
#: plus the ones read on the machine. A media engine (diffusers) prices its
#: host memory as the spec's stated ``ram_gb``, so it is not in this set.
ENGINES = (derived.RUNTIME_RESIDENT_KEY, *derived.RUNTIME_RESIDENT_READ)

#: The invented dense model a unit of each engine serves.
DENSE = "example-dense"

#: A value the user might set for the figure, in GiB: invented.
SETTING = 1.25

#: A floor on host memory the user states for a dense unit, in GiB: invented.
#: With one, a unit's fit asks host memory for its blob mapped.
FLOOR = 1.0

#: Two kinds of numbers file that cannot be read.
BROKEN = ("not-yaml", "unknown-number")


def broken(kind: str, engine: str) -> str | dict[str, Any]:
    """A numbers file of ``kind`` that cannot be read: text that is not YAML,
    or a setting of ``engine``'s figure beside a number mcgyvr does not ship."""
    if kind == "not-yaml":
        return f"{derived.RUNTIME_RESIDENT}: [\n"
    return {
        derived.RUNTIME_RESIDENT: {engine: SETTING},
        "an_invented_number": {engine: SETTING},
    }


def line() -> str | None:
    """The line the sizing says, as the sizing module states it."""
    stated: str | None = getattr(serving, "HOST_FIGURE_NOT_READ", None)
    return stated


def says(text: str) -> bool:
    """Whether ``text`` says the line."""
    stated = line()
    return stated is not None and stated in text


def not_shipped() -> list[str]:
    """The engines a unit may name for which mcgyvr ships no host memory figure."""
    document = json.loads(derived.shipped_path().read_text(encoding="utf-8"))
    shipped = document["numbers"][derived.RUNTIME_RESIDENT]["values"]
    return [engine for engine in ENGINES if engine not in shipped]


def dense(scan: Scan) -> ModelSpec:
    """An invented dense model, with no geometry, that the roomiest card holds."""
    free_gib = max(gpu.vram.free_mib for gpu in scan.gpus) / 1024
    size = round((free_gib - DEFAULT_HEADROOM_GB) / 4, 1)
    return ModelSpec(
        name=DENSE,
        vram_gb=size,
        ram_gb=0.0,
        disk_gb=size,
        hf_cache="/models/hf",
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def test_the_engines_read_on_the_machine_are_some() -> None:
    assert not_shipped(), "every engine ships its figure; this file tests nothing"


def test_the_line_names_every_engine_whose_figure_it_has_not_read() -> None:
    stated = line()
    assert stated is not None, "the sizing module states no such line"
    for engine in derived.RUNTIME_RESIDENT_READ:
        assert engine.lower() in stated.lower(), (engine, stated)


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
@pytest.mark.parametrize("engine", ENGINES)
def test_a_unit_that_fits_says_it_only_when_its_figure_is_not_shipped(
    machine: machine_shapes.Shape, engine: str
) -> None:
    scan = machine_shapes.scan(machine)
    unit = unit_for(scan, dense(scan), engine=engine, ctx_per_slot=WINDOW)
    expected = engine in not_shipped()
    assert says(unit.fit.why) == expected, (
        f"{engine}: the sizing of a unit that fits says {unit.fit.why!r}"
    )
    if expected:
        assert any(says(note) for note in unit.fit.notes), unit.fit.notes


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
@pytest.mark.parametrize("engine", ENGINES)
def test_a_refused_unit_says_it_only_when_its_figure_is_not_shipped(
    machine: machine_shapes.Shape, engine: str
) -> None:
    scan = machine_shapes.scan(machine)
    with pytest.raises(UnitError) as refused:
        unit_for(scan, spilling(scan), engine=engine, ctx_per_slot=WINDOW)
    assert says(str(refused.value)) == (engine in not_shipped()), (
        f"{engine}: the refusal says {str(refused.value)!r}"
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_your_own_setting_of_that_figure_is_said_to_be_unused(
    engine: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    written = nf.write_user_file(
        tmp_path_factory, {derived.RUNTIME_RESIDENT: {engine: SETTING}}
    )
    scan = machine_shapes.scan(machines()[0])
    unit = unit_for(scan, dense(scan), engine=engine, ctx_per_slot=WINDOW)
    if engine not in not_shipped():
        assert not says(unit.fit.why), unit.fit.why
        return
    assert says(unit.fit.why), unit.fit.why
    unused = serving.HOST_FIGURE_SETTING_NOT_USED.format(where=written)
    assert len(unit.fit.notes) == 1, unit.fit.notes
    (note,) = unit.fit.notes
    assert says(note), note
    assert unused in note, note
    assert note in unit.fit.why


@pytest.mark.parametrize("kind", BROKEN)
@pytest.mark.parametrize("engine", ENGINES)
def test_a_numbers_file_that_cannot_be_read_is_named_not_swallowed(
    engine: str, kind: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    nf.write_user_file(tmp_path_factory, broken(kind, engine))
    with pytest.raises(derived.DerivedNumbersError) as refused:
        derived.user_setting(derived.RUNTIME_RESIDENT, engine)
    scan = machine_shapes.scan(machines()[0])
    unit = unit_for(scan, dense(scan), engine=engine, ctx_per_slot=WINDOW)
    if engine not in not_shipped():
        assert not says(unit.fit.why), unit.fit.why
        return
    assert str(refused.value) in unit.fit.why, unit.fit.why
    (note,) = unit.fit.notes
    assert says(note), note
    assert serving.HOST_FIGURE_SETTING_UNKNOWN.format(why=refused.value) in note


def config(host: str, sizes: dict[str, float]) -> str:
    """One unit of each engine a unit may name, on ``host``, each on its port."""
    blocks = []
    for port, engine in enumerate(ENGINES, start=8080):
        blocks.append(
            f"""\
  unit_{port}:
    address: http://{host}:{port}
    model: {DENSE}-{port}
    engine: {engine}
    hf_cache: /models/hf
    launch:
      vram_gb: {sizes["vram_gb"]}
      disk_gb: {sizes["disk_gb"]}
      ram_gb: {sizes.get("ram_gb", 0.0)}
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
"""
        )
    ladder = "".join(f"- unit_{port}\n" for port, _ in enumerate(ENGINES, start=8080))
    return "units:\n" + "".join(blocks) + "ladder:\n" + ladder


def install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scan: Scan,
    sizes: dict[str, float],
) -> tuple[Path, dict[str, str]]:
    """``scan`` recorded and :func:`config` written: where emit writes, and each
    engine's unit by its slug."""
    host = scan.machine.host
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / "machine.json").write_text(scan.to_json(), encoding="utf-8")
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))
    written = tmp_path / "mcgyvr.yaml"
    written.write_text(config(host, sizes), encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(written))
    out = tmp_path / "compose"
    out.mkdir()
    slugs = {
        engine: UnitKey(
            host=host, model=f"{DENSE}-{port}", engine=engine, port=port
        ).slug
        for port, engine in enumerate(ENGINES, start=8080)
    }
    return out, slugs


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_emit_says_it_for_each_such_unit_when_it_writes_and_when_it_checks(
    machine: machine_shapes.Shape,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scan = machine_shapes.scan(machine)
    spec = dense(scan)
    out, slugs = install(
        tmp_path, monkeypatch, scan, {"vram_gb": spec.vram_gb, "disk_gb": spec.disk_gb}
    )
    for check in ((), ("--check",)):
        told = main(["emit", *check, "--out", str(out), "--ctx-per-slot", str(WINDOW)])
        said = capsys.readouterr()
        assert told == Exit.OK, said.err
        notes = [text for text in said.err.splitlines() if text.startswith("note: ")]
        for engine, slug in slugs.items():
            about = [text for text in notes if text.startswith(f"note: {slug}: ")]
            if engine in not_shipped():
                assert any(says(text) for text in about), (
                    f"{engine}: {' '.join(('emit', *check))} said {said.err!r}"
                )
            else:
                assert about == [], about


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_emit_says_it_before_it_refuses_units_that_fit_host_memory_one_at_a_time(
    machine: machine_shapes.Shape,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each unit's blob fits the host's memory mapped alone; the two do not fit
    it together, so emit refuses them, and says the line first."""
    measured = machine_shapes.scan(machine)
    spec = dense(measured)
    available = spec.disk_gb + MODE_RAM_HEADROOM_GB + spec.disk_gb / 2
    scan = replace(
        measured, memory=Memory(total_gb=2 * available, available_gb=available)
    )
    out, slugs = install(
        tmp_path,
        monkeypatch,
        scan,
        {"vram_gb": spec.vram_gb, "disk_gb": spec.disk_gb, "ram_gb": FLOOR},
    )
    told = main(["emit", "--out", str(out), "--ctx-per-slot", str(WINDOW)])
    said = capsys.readouterr()
    assert told == Exit.REFUSED, said.err
    lines = said.err.splitlines()
    refusal = [at for at, text in enumerate(lines) if text.startswith("refused: ")]
    assert refusal, said.err
    for engine, slug in slugs.items():
        about = [
            at for at, text in enumerate(lines) if text.startswith(f"note: {slug}: ")
        ]
        if engine in not_shipped():
            assert any(says(lines[at]) for at in about), f"{engine}: {said.err!r}"
            assert max(about) < min(refusal), said.err
        else:
            assert about == [], said.err
