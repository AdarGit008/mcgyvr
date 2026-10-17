""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  #
    from mcgyvr.config import Config, Unit

CATALOG_FILENAME = "task-catalog.json"
SCHEMA_VERSION = 2

#
#
#
#s.
RETIRED_TASK_TYPES: dict[str, str] = {
    "format": "'code' with operation: format",
    "import_sort": "'code' with operation: import_sort",
    "lint_fix": "'code' with operation: lint_fix",
    "rename_symbol": "'code' with operation: rename_symbol",
    "docstring": "'code' with no_semantic_change: true",
    "type_annotation": "'code' with type_check: true",
    "function_implementation": "'code'",
    "test_scaffold": "'code'",
    "bug_fix": "'code' with a demonstration",
}


class CatalogError(Exception):
    ""


@dataclass(frozen=True)
class Family:
    ""

    name: str
    rank: int
    doc: str


@dataclass(frozen=True)
class UseCase:
    ""

    name: str
    doc: str


@dataclass(frozen=True)
class Evidence:
    ""

    name: str
    doc: str
    needs_commands: bool
    baseline: str = "pass"


@dataclass(frozen=True)
class TaskType:
    ""

    name: str
    starts_on: Family
    use_case: UseCase
    guarantee: str
    required_evidence: tuple[Evidence, ...]
    warrant: str
    doc: str
    #
    #
    #
    task_type: str = ""
    #
    #
    #
    #
    #
    #
    #
    evidence_derived: bool = False
    #
    #
    #no
    #
    #
    #
    session: bool = False

    @property
    def deterministic(self) -> bool:
        ""
        return self.starts_on.rank == 0

    @property
    def needs_acceptance_commands(self) -> bool:
        ""
        return any(
            e.needs_commands and e.baseline == "pass" for e in self.required_evidence
        )

    @property
    def needs_demonstration_commands(self) -> bool:
        ""
        return any(
            e.needs_commands and e.baseline == "fail" for e in self.required_evidence
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.required_evidence)

    @property
    def judges_a_change(self) -> bool:
        ""
        return self.evidence_derived or "gate" in self.evidence_names

    @property
    def needs_output_cap(self) -> bool:
        ""
        return not self.deterministic and not self.session and self.judges_a_change


@dataclass(frozen=True)
class Catalog:
    ""

    families: tuple[Family, ...]
    use_cases: tuple[UseCase, ...]
    evidence_kinds: tuple[Evidence, ...]
    task_types: tuple[TaskType, ...]
    operations: tuple[TaskType, ...]

    @property
    def names(self) -> tuple[str, ...]:
        ""
        return tuple(t.name for t in self.task_types)

    def get(self, name: str) -> TaskType | None:
        ""
        return next((t for t in self.task_types if t.name == name), None)

    def require(self, name: str) -> TaskType:
        ""
        found = self.get(name)
        if found is None:
            if name in RETIRED_TASK_TYPES:
                raise CatalogError(f"{name!r} is now {RETIRED_TASK_TYPES[name]}.")
            raise CatalogError(
                f"{name!r} is not a known task type. Valid: {', '.join(self.names)}"
            )
        return found

    def operation(self, name: str) -> TaskType | None:
        ""
        return next((t for t in self.operations if t.name == name), None)

    def require_operation(self, name: str) -> TaskType:
        ""
        found = self.operation(name)
        if found is None:
            valid = ", ".join(t.name for t in self.operations)
            raise CatalogError(
                f"{name!r} is not a known deterministic operation. Valid: {valid}"
            )
        return found

    def family(self, name: str) -> Family:
        found = next((f for f in self.families if f.name == name), None)
        if found is None:
            valid = ", ".join(f.name for f in self.families)
            raise CatalogError(f"{name!r} is not a known family. Valid: {valid}")
        return found

    def evidence(self, name: str) -> Evidence:
        ""
        found = next((e for e in self.evidence_kinds if e.name == name), None)
        if found is None:
            valid = ", ".join(e.name for e in self.evidence_kinds)
            raise CatalogError(f"{name!r} is not a known evidence kind. Valid: {valid}")
        return found

    def family_of(self, source: Unit) -> Family:
        ""
        return self.family("api" if source.requires_credential else "local")

    #

    def unservable(self, config: Config) -> tuple[TaskType, ...]:
        ""
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name not in available)

    def servable(self, config: Config) -> tuple[TaskType, ...]:
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name in available)


def _families_present(catalog: Catalog, config: Config) -> frozenset[str]:
    ""
    present = {catalog.families[0].name}
    bound = {
        catalog.family_of(config.units[name]).rank
        for name in config.ladder.names
        if name in config.units
    }
    if bound:
        dearest = max(bound)
        present |= {f.name for f in catalog.families if f.rank <= dearest}
    return frozenset(present)


#


def catalog_path() -> Path:
    ""
    packaged = resources.files("mcgyvr") / "data" / CATALOG_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    checkout = Path(__file__).resolve().parents[2] / "data" / CATALOG_FILENAME
    if checkout.is_file():
        return checkout
    raise CatalogError(f"task catalog not found (looked for {CATALOG_FILENAME})")


def _require_keys(entry: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if not entry.get(k)]
    if missing:
        raise CatalogError(f"{where}: missing or empty {', '.join(missing)}")


def _load_entries(
    raw: dict[str, Any],
    key: str,
    by_family: dict[str, Family],
    by_use_case: dict[str, UseCase],
    by_evidence: dict[str, Evidence],
    reserved: set[str],
) -> tuple[TaskType, ...]:
    ""
    entries: list[TaskType] = []
    for entry in raw.get(key, []):
        name = str(entry.get("name", ""))
        where = f"{key}[{name or len(entries)}]"
        _require_keys(entry, ("name", "starts_on", "use_case", "guarantee"), where)
        if "required_evidence" not in entry:
            raise CatalogError(f"{where}: missing required_evidence")
        if not isinstance(entry["required_evidence"], list):
            raise CatalogError(f"{where}: required_evidence must be a list")
        if name in reserved:
            raise CatalogError(f"{where}: {name!r} is declared more than once")
        reserved.add(name)

        family = by_family.get(str(entry["starts_on"]))
        if family is None:
            raise CatalogError(
                f"{where}: starts_on {entry['starts_on']!r} is not a declared "
                f"family. Valid: {', '.join(by_family)}"
            )
        use_case = by_use_case.get(str(entry["use_case"]))
        if use_case is None:
            raise CatalogError(
                f"{where}: use_case {entry['use_case']!r} is not a declared "
                f"use case. Valid: {', '.join(by_use_case)}"
            )
        kinds: list[Evidence] = []
        for kind in entry["required_evidence"]:
            found = by_evidence.get(str(kind))
            if found is None:
                raise CatalogError(
                    f"{where}: required_evidence {kind!r} is not a declared "
                    f"evidence kind. Valid: {', '.join(by_evidence)}"
                )
            if found in kinds:
                raise CatalogError(f"{where}: required_evidence {kind!r} is repeated")
            kinds.append(found)

        entries.append(
            TaskType(
                name=name,
                starts_on=family,
                use_case=use_case,
                guarantee=str(entry["guarantee"]),
                required_evidence=tuple(kinds),
                warrant=str(entry.get("warrant", "")),
                doc=str(entry.get("doc", "")),
                evidence_derived=bool(entry.get("evidence_derived", False)),
                session=bool(entry.get("session", False)),
                task_type=str(entry.get("task_type", "")),
            )
        )
    return tuple(entries)


def load(path: Path | None = None) -> Catalog:
    ""
    path = path or catalog_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{path} is not valid JSON: {exc}") from exc

    if raw.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError(
            f"unsupported task catalog schema_version "
            f"{raw.get('schema_version')!r} (this build reads {SCHEMA_VERSION})"
        )

    families = tuple(
        Family(name=str(f["name"]), rank=rank, doc=str(f.get("doc", "")))
        for rank, f in enumerate(raw.get("families", []))
    )
    if not families:
        raise CatalogError(f"{path} declares no families")

    use_cases = tuple(
        UseCase(name=str(u["name"]), doc=str(u.get("doc", "")))
        for u in raw.get("use_cases", [])
    )
    if not use_cases:
        raise CatalogError(f"{path} declares no use cases")

    evidence = tuple(
        Evidence(
            name=str(e["name"]),
            doc=str(e.get("doc", "")),
            needs_commands=bool(e.get("needs_commands", False)),
            baseline=str(e.get("baseline", "pass")),
        )
        for e in raw.get("evidence_kinds", [])
    )
    for kind in evidence:
        if kind.baseline not in ("pass", "fail"):
            raise CatalogError(
                f"evidence_kinds[{kind.name}]: baseline {kind.baseline!r} is not "
                f"'pass' or 'fail'"
            )
        if kind.baseline == "fail" and not kind.needs_commands:
            raise CatalogError(
                f"evidence_kinds[{kind.name}]: baseline 'fail' without "
                f"needs_commands — a structural check has no baseline run whose "
                f"outcome could be expected"
            )
    by_evidence = {e.name: e for e in evidence}
    by_family = {f.name: f for f in families}
    by_use_case = {u.name: u for u in use_cases}

    reserved: set[str] = set()
    task_types = _load_entries(
        raw, "task_types", by_family, by_use_case, by_evidence, reserved
    )
    if not task_types:
        raise CatalogError(f"{path} declares no task types")

    operations = _load_entries(
        raw, "deterministic_operations", by_family, by_use_case, by_evidence, reserved
    )

    task_type_names = {t.name for t in task_types}
    for op in operations:
        if op.task_type not in task_type_names:
            raise CatalogError(
                f"deterministic_operations[{op.name}]: task_type "
                f"{op.task_type!r} is not a declared task type. Valid: "
                f"{', '.join(sorted(task_type_names))}"
            )

    return Catalog(
        families=families,
        use_cases=use_cases,
        evidence_kinds=evidence,
        task_types=task_types,
        operations=operations,
    )


@cache
def catalog() -> Catalog:
    ""
    return load()
