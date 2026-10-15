"""What names the live fleet, read by the command line."""

from __future__ import annotations


import argparse


import contextlib


import ipaddress


import json


import os


import signal


import sys


import textwrap


import threading


from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence


from dataclasses import dataclass


from pathlib import Path


from typing import TYPE_CHECKING, Any, TextIO


import yaml


from mcgyvr import __version__, atomic


from mcgyvr import recommend as recommend_module


from mcgyvr import scan as scan_module


from mcgyvr.availability import PROBE_TIMEOUT_S


from mcgyvr.capability import (
    ESTIMATES_NOTICE,
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
    table_path,
)


from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    FLEET_FILENAME,
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)


from mcgyvr.config import config_path as resolve_config_path


from mcgyvr.config import load as load_config


from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for


from mcgyvr.emit import (
    Drift,
    EmitError,
    LockedLaunchError,
    check_all,
    check_locked,
    emit_all,
    emit_locked,
    is_locked,
    planned_locked_paths,
    planned_paths,
    resolved_launch,
    unplanned,
    unplanned_locked,
)


from mcgyvr.emit import sleep_mode as emit_sleep_mode


from mcgyvr.exits import Exit


from mcgyvr.fleet.files import FleetFileError, load_fleet


from mcgyvr.fleet.roots import (
    FLEETS_SHOWN,
    LIVE_FILE_SHOWN,
    RIGS_SHOWN,
    STAGING_SHOWN,
    FolderError,
)


from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    render_fleet,
    unit_names,
)


from mcgyvr.scan import ModelOnDisk, Scan


from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    host_of,
    units_for,
)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.detect import Detection
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.knowledge.record import ModelRecord
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted, Try
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session




def _live(config: Config) -> bool:
    """Whether a command run under ``config`` is held to the live fleet's lock.

    It is whenever a fleet is live, but under a setup in the data folder: the
    staging folder ``mcgyvr setup`` starts and samples before anything of it is
    locked, which is admitted against nothing
    (:func:`mcgyvr.fleet.roots.runs_live`).
    """
    from mcgyvr.fleet.roots import runs_live

    return runs_live(config.path)



def _admitted_live(config: Config) -> str | None:
    """``None`` when live admission admits this command, else why not, printed.

    Each rig of the live fleet is read through the door and held to the lock
    (:func:`mcgyvr.fleet.admission.admit`), and a unit on a rig in ``config``,
    the config the command loaded, must be one the live fleet lays out there. A
    plan to clean or restore refuses, and the door commands that would carry it
    out are printed and not run: that a live command carries its plan out is not
    decided.
    """
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    try:
        admission = admit(units=config.get("units") or {})
    except LiveRefusedError as exc:
        detail = f"live admission: {exc}"
        print(f"refused: {detail}", file=sys.stderr)
        return detail
    if admission.admitted:
        return None
    detail = (
        f"live admission: the rigs of {admission.fleet} do not read as locked; "
        "nothing was cleaned or restored, and these door commands would do it"
    )
    print(f"refused: {detail}:", file=sys.stderr)
    for line in admission.commands:
        print(f"  {line}", file=sys.stderr)
    return detail
