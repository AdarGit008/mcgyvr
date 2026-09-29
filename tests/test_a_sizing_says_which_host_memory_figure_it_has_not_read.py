"""A sizing says which host memory figure it has not read.

For an engine whose host memory figure is read on the user's machine, mcgyvr
ships no estimate of it (every engine is one or the other, never both; the
test beside this one holds that). While no reading exists, every sizing of a
unit of such an engine says that it has none: when the unit fits, when it is
refused, and in what ``mcgyvr emit`` prints, before anything is written or
checked. That holds when the user's own numbers file sets the figure too, and
the sizing then also says that setting is not used. No sizing of a unit of
any other engine says it.

The line is read from the sizing module and never restated here: a module
that has no such line says it nowhere. The machines are the invented shapes of
:mod:`tests.machine_shapes`; the models are invented here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import derived, serving
from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.exits import Exit
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, UnitKey, unit_for
from tests import machine_shapes
from tests import numbers_fixture as nf
from tests.test_one_engines_host_memory_figure_is_never_charged_to_another import (
    WINDOW,
    machines,
    spilling,
)

#: The invented dense model a unit of each engine serves.
DENSE = "example-dense"

#: A value the user might set for the figure, in GiB: invented.
SETTING = 1.25


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
    return [engine for engine in derived.KEY_SPACES["engine"] if engine not in shipped]


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


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
@pytest.mark.parametrize("engine", derived.KEY_SPACES["engine"])
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
@pytest.mark.parametrize("engine", derived.KEY_SPACES["engine"])
def test_a_refused_unit_says_it_only_when_its_figure_is_not_shipped(
    machine: machine_shapes.Shape, engine: str
) -> None:
    scan = machine_shapes.scan(machine)
    with pytest.raises(UnitError) as refused:
        unit_for(scan, spilling(scan), engine=engine, ctx_per_slot=WINDOW)
    assert says(str(refused.value)) == (engine in not_shipped()), (
        f"{engine}: the refusal says {str(refused.value)!r}"
    )


@pytest.mark.parametrize("engine", derived.KEY_SPACES["engine"])
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


def config(host: str, sizes: dict[str, float]) -> str:
    """One unit of each engine a unit may name, on ``host``, each on its port."""
    blocks = []
    for port, engine in enumerate(derived.KEY_SPACES["engine"], start=8080):
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
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
"""
        )
    ladder = "".join(
        f"- unit_{port}\n"
        for port, _ in enumerate(derived.KEY_SPACES["engine"], start=8080)
    )
    return "units:\n" + "".join(blocks) + "ladder:\n" + ladder


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_emit_says_it_for_each_such_unit_before_it_writes_or_checks(
    machine: machine_shapes.Shape,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scan = machine_shapes.scan(machine)
    host = scan.machine.host
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / "machine.json").write_text(scan.to_json(), encoding="utf-8")
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))
    spec = dense(scan)
    written = tmp_path / "mcgyvr.yaml"
    written.write_text(
        config(host, {"vram_gb": spec.vram_gb, "disk_gb": spec.disk_gb}),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENV, str(written))
    out = tmp_path / "compose"
    out.mkdir()
    slugs = {
        engine: UnitKey(
            host=host, model=f"{DENSE}-{port}", engine=engine, port=port
        ).slug
        for port, engine in enumerate(derived.KEY_SPACES["engine"], start=8080)
    }
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
