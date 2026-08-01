"""Changed JSON and YAML must parse.

One of the cheap checks that prevents an expensive failure: a worker that
writes a malformed config or fixture would otherwise fail much later, inside a
command execution, where the cause is harder to read. Parsing the changed
structured files up front turns that into a precise, early finding.

The whole resulting file is parsed, not just the added lines: a document is
valid or it is not, and a worker can break parsing with a deletion as easily as
an addition. YAML support is optional — it activates when a YAML parser is
installed (the config epic introduces one as the project's first runtime
dependency); until then YAML files are left unvalidated rather than guessed at.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding

# Optional: a YAML parser is present once the config epic adds PyYAML as a
# runtime dependency. Imported dynamically and held as Any so this module type
# checks identically whether or not the parser (and its stubs) are installed —
# a static `import yaml` would flip between "unused ignore" and "missing import"
# across those two environments.
try:  # pragma: no cover - branch taken depends on whether PyYAML is installed
    _yaml: Any = import_module("yaml")
except ImportError:  # pragma: no cover
    _yaml = None

_JSON_EXT = (".json",)
_YAML_EXT = (".yaml", ".yml")


def validate_structured_data(changeset: ChangeSet) -> list[Finding]:
    """Findings for each changed JSON/YAML file that no longer parses."""
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
            line = mark.line + 1  # PyYAML marks are 0-based
        return Finding(
            check="structured-data",
            path=rel,
            line=line,
            code="invalid-yaml",
            message=str(getattr(exc, "problem", None) or exc).strip(),
        )
    return None
