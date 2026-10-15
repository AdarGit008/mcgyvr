"""Sandbox policy and tree-reading helpers shared by sandbox, run and delegate."""

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




def _reads_the_tree(contract: Contract) -> bool:
    """Whether a run of ``contract`` reads anything off the repository's HEAD.

    The note :func:`_say_what_the_sandbox_leaves_out` prints is about what a
    sandbox of HEAD holds, so it is worth reading only to a run that looks in
    it. Every run that writes a change does. A session (``chat``, ``agent``)
    writes nothing and has no target: it reads the tree only through the
    ``sources`` it names and the commands it declares. One with neither — a
    plain ``chat`` — reads nothing there, and telling it to commit files it
    never opens is noise (e2e run 3, T4). An ``agent``'s sources are read off
    HEAD, so it is told. Read off the contract and the catalog's ``session``
    flag, never a task type's name, which no consumer of the vocabulary
    spells.
    """
    if not contract.is_session:
        return True
    return bool(contract.sources or contract.acceptance or contract.demonstration)



def _say_what_the_sandbox_leaves_out(repo: Path) -> list[str]:
    """Say on stderr what a sandbox of ``repo``'s HEAD will not hold.

    Returns the note as a one-item list, or an empty one when there is
    nothing to say, for a run to carry into its result file as well.
    """
    from mcgyvr.orchestrator import head_only_note

    note = head_only_note(repo)
    if note is None:
        return []
    print(f"note: {note}", file=sys.stderr)
    return [note]



def _sandbox_policy(config: Config | None) -> dict[str, Any]:
    """What the `sandbox` block says about a sandbox beyond its mode.

    Read in one place for both paths that open one, so the floor and the climb
    cannot come to disagree about whether a missing daemon falls back or what
    network a container gets. No config is the schema's defaults: refuse
    rather than fall back, and Docker's default network.
    """
    if config is None:
        return {"allow_fallback": False, "network": "bridge"}
    return {
        "allow_fallback": bool(config.get("sandbox.allow_fallback", False)),
        "network": config.get("sandbox.network", "bridge"),
    }
