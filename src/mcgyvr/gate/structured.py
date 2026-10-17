""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding

#
#rt
#
#
try:  #
    _yaml: Any = import_module("yaml")
except ImportError:  #
    _yaml = None

_JSON_EXT = (".json",)
_YAML_EXT = (".yaml", ".yml")


def validate_structured_data(changeset: ChangeSet) -> list[Finding]:
    ""
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
            line = mark.line + 1  #
        return Finding(
            check="structured-data",
            path=rel,
            line=line,
            code="invalid-yaml",
            message=str(getattr(exc, "problem", None) or exc).strip(),
        )
    return None
