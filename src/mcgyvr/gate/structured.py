"""Parse the JSON and YAML files in a change set and report the ones that fail.

Each text file is dispatched on its suffix: ``.json`` is parsed with
:func:`json.loads`, ``.yaml``/``.yml`` with PyYAML's ``safe_load``. A parse
error becomes a ``structured-data`` finding carrying the line where the parser
gave up. Anything else — an unreadable file, another suffix, or YAML when
PyYAML is not installed — produces no finding.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding

# PyYAML is an optional dependency: the gate has to import in environments that
# do not have it. The module is therefore resolved at import time and kept as
# ``None`` when missing, which disables YAML validation instead of breaking
# every run.
try:  # pragma: no cover - branch taken depends on whether PyYAML is installed
    _yaml: Any = import_module("yaml")
except ImportError:  # pragma: no cover
    _yaml = None

_JSON_EXT = (".json",)
_YAML_EXT = (".yaml", ".yml")


def validate_structured_data(changeset: ChangeSet) -> list[Finding]:
    """Return findings for changed JSON and YAML files that do not parse.

    Only text changes are inspected, so binary files, deletions and symlinks
    are skipped. Suffix matching is case-insensitive, YAML files are skipped
    when PyYAML is unavailable, and each file contributes at most one finding.
    """
    findings: list[Finding] = []
    for change in changeset.text_changes():
        path = change.path.lower()
        if path.endswith(_JSON_EXT):
            finding = _validate_json(changeset.repo / change.path, change.path)
        elif path.endswith(_YAML_EXT) and _yaml is not None:
            finding = _validate_yaml(changeset.repo / change.path, change.path)
        else:
            finding = None
        if finding is not None:
            findings.append(finding)
    return findings


def _validate_json(file: Path, rel: str) -> Finding | None:
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return Finding(
            check="structured-data",
            path=rel,
            line=exc.lineno,
            code="invalid-json",
            message=exc.msg,
        )
    return None


def _validate_yaml(file: Path, rel: str) -> Finding | None:
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        _yaml.safe_load(text)
    except _yaml.YAMLError as exc:
        line = None
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = mark.line + 1  # YAML marks are zero-based, findings are one-based
        return Finding(
            check="structured-data",
            path=rel,
            line=line,
            code="invalid-yaml",
            message=str(getattr(exc, "problem", None) or exc).strip(),
        )
    return None
