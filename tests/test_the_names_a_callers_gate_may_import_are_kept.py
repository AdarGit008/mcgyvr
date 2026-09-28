"""The names a caller's gate may import from the package are kept.

A caller's gate runs under the door and is written against the package: the
helpers every gate uses to prove the door, refuse, export and reach the
machine, the config loader, the lock's folder, and the two modules that read
a model's tensor table and size its placement. A rename of any of these
breaks a gate the package does not hold, so each is pinned here by the name a
gate imports it by.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

#: Module, and the names a caller's gate reads from it.
KEPT: dict[str, tuple[str, ...]] = {
    "mcgyvr": ("__version__",),
    "mcgyvr.serving.gatelib": (
        "DEV",
        "artifact_escape",
        "claim",
        "claim_path",
        "displaced_by_run",
        "door_required",
        "envelope_escape",
        "export",
        "lease_of_run",
        "lease_stamp",
        "need",
        "refuse",
        "release",
        "root",
        "ssh",
    ),
    "mcgyvr.config": (
        "CONFIG_PATH_ENV",
        "ConfigError",
        "ConfigMissingError",
        "field_at",
        "load",
        "named_config_path",
    ),
    "mcgyvr.fleet.roots": ("LiveFleetError", "lock_root"),
    "mcgyvr.serving.ggufscan": ("__file__",),
    "mcgyvr.serving.vramfit": (
        "SCRATCH_AND_CONTEXT_MIB",
        "experts_on_card",
        "floor",
        "kv_bytes",
        "rs_bytes",
    ),
}


@pytest.mark.parametrize(
    ("module", "name"),
    [(module, name) for module, names in KEPT.items() for name in names],
)
def test_a_name_a_callers_gate_imports_is_still_there(module: str, name: str) -> None:
    loaded = importlib.import_module(module)
    assert hasattr(loaded, name), (
        f"{module}.{name} is gone; a caller's gate imports it by that name"
    )


def test_the_tensor_table_reader_is_a_file_a_gate_can_ship() -> None:
    """A gate sends the reader's own file to the machine, so it must be one."""
    ggufscan = importlib.import_module("mcgyvr.serving.ggufscan")
    assert ggufscan.__file__ is not None
    assert Path(ggufscan.__file__).is_file()
