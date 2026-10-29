"""What mcgyvr can be asked to do, read from `data/task-catalog.json`.

The JSON is the only definition of the vocabulary: the families a contract may
start on, the use cases, the evidence kinds and the task types, each with the
guarantee accepting it makes. This module gives that data a shape (`Family`,
`UseCase`, `Evidence`, `TaskType`, `Catalog`), validates it on load, and answers
the questions callers ask of it — look a type up by name, resolve a unit to the
family serving it, list the types a config's ladder can reach.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.hubwire import POOL_CREW, serving_pool
from mcgyvr.shipped import shipped_file

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config, Unit

CATALOG_FILENAME = "task-catalog.json"
SCHEMA_VERSION = 2


class CatalogError(Exception):
    """A catalog that cannot be found, read, parsed or validated, or a lookup of
    a name the catalog does not declare."""


@dataclass(frozen=True)
class Family:
    """Where work may start, independent of the rung names a config chose.

    `rank` is the index in the file's cheapest-to-dearest order, so rank 0 is the
    family of tools.
    """

    name: str
    rank: int
    doc: str


@dataclass(frozen=True)
class UseCase:
    """One of the kinds of work the install can be put to; a task type belongs to
    exactly one."""

    name: str
    doc: str


@dataclass(frozen=True)
class Evidence:
    """One kind of evidence a contract can be required to carry.

    `needs_commands` says whether the gate runs commands for it. `baseline` says
    what those commands must do on the unchanged tree: `pass` for a regression
    check, `fail` for a demonstration of the defect.
    """

    name: str
    doc: str
    needs_commands: bool
    baseline: str = "pass"


@dataclass(frozen=True)
class TaskType:
    """A unit of work with a promise attached.

    `starts_on` is the family it may begin on, `guarantee` what accepting it
    promises, `required_evidence` what a contract of this type must carry,
    `warrant` why the type is worth asking, and `doc` the one-line description
    shown to callers and to models.
    """

    name: str
    starts_on: Family
    use_case: UseCase
    guarantee: str
    required_evidence: tuple[Evidence, ...]
    warrant: str
    doc: str
    #: Set only on entries of `deterministic_operations`: the task type a
    #: contract asks for this operation under (`task_type: code` with
    #: `operation: <name>`). Empty on task types themselves.
    task_type: str = ""
    #: True when the contract's own contents decide the evidence rather than
    #: the catalog listing it: the gate always, plus failing_test_first for a
    #: demonstration, tests_pass for acceptance commands, no_semantic_change
    #: and type_check for the matching flags. Callers then describe that
    #: derivation instead of a fixed list, so the model is told it never
    #: chooses evidence itself. Declared per entry in the JSON and False when
    #: the entry leaves the key out.
    evidence_derived: bool = False

    @property
    def deterministic(self) -> bool:
        """True when the type starts on the cheapest family, where a tool
        owns the output and no model is asked."""
        return self.starts_on.rank == 0

    @property
    def needs_acceptance_commands(self) -> bool:
        """True when some required evidence runs commands that must already
        pass on the unchanged tree, so the contract must supply
        `acceptance` commands."""
        return any(
            e.needs_commands and e.baseline == "pass" for e in self.required_evidence
        )

    @property
    def needs_demonstration_commands(self) -> bool:
        """True when some required evidence runs commands that must fail on
        the unchanged tree, so the contract must supply `demonstration`
        commands."""
        return any(
            e.needs_commands and e.baseline == "fail" for e in self.required_evidence
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.required_evidence)

    @property
    def judges_a_change(self) -> bool:
        """True when a change of this type is judged, not merely produced:
        either the evidence is derived from the contract, or the gate is
        among the required evidence."""
        return self.evidence_derived or "gate" in self.evidence_names

    @property
    def needs_output_cap(self) -> bool:
        """True when a model writes a change that something then judges —
        not a tool's work — so its reply is sent the unit's maximum and the
        unit it runs on must state one (`window` or `output_tokens`)."""
        return not self.deterministic and self.judges_a_change


@dataclass(frozen=True)
class Catalog:
    """The whole vocabulary, in the order the file declares it.

    `task_types` is what a contract may name. `operations` are the
    deterministic entries a `code` contract asks for by operation name;
    they share the `TaskType` shape but are not task types themselves.
    """

    families: tuple[Family, ...]
    use_cases: tuple[UseCase, ...]
    evidence_kinds: tuple[Evidence, ...]
    task_types: tuple[TaskType, ...]
    operations: tuple[TaskType, ...]

    @property
    def names(self) -> tuple[str, ...]:
        """Every declared task type name, in file order."""
        return tuple(t.name for t in self.task_types)

    def get(self, name: str) -> TaskType | None:
        """The task type called `name`, or None if none is declared."""
        return next((t for t in self.task_types if t.name == name), None)

    def require(self, name: str) -> TaskType:
        """The task type called `name`; raises `CatalogError` listing the valid
        names when it is not declared."""
        found = self.get(name)
        if found is None:
            raise CatalogError(
                f"{name!r} is not a known task type. Valid: {', '.join(self.names)}"
            )
        return found

    def operation(self, name: str) -> TaskType | None:
        """The deterministic operation called `name`, or None."""
        return next((t for t in self.operations if t.name == name), None)

    def require_operation(self, name: str) -> TaskType:
        """The operation called `name`; raises `CatalogError` listing the
        valid operation names."""
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
        """The evidence kind called `name`; raises `CatalogError` listing the
        valid kind names."""
        found = next((e for e in self.evidence_kinds if e.name == name), None)
        if found is None:
            valid = ", ".join(e.name for e in self.evidence_kinds)
            raise CatalogError(f"{name!r} is not a known evidence kind. Valid: {valid}")
        return found

    def family_of(self, source: Unit) -> Family:
        """The family a unit is served from: `api` when it declares an
        `api_key_env`, `local` when it does not. A crew unit (one `crew.yaml`
        holds) a hub serves from the crew pool (`hubwire.serving_pool`) names
        the key it is asked with and still is `local`: a crew lends its units
        free, so it is no api rung. A hand-written unit is never taken as one."""
        lent = source.crew and serving_pool(source.scope, source.model) == POOL_CREW
        priced = source.requires_credential and not lent
        return self.family("api" if priced else "local")

    # Servability: what this config's ladder can and cannot start.

    def unservable(self, config: Config) -> tuple[TaskType, ...]:
        """The task types whose starting family this config's ladder does
        not reach, so they cannot be asked for here."""
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name not in available)

    def servable(self, config: Config) -> tuple[TaskType, ...]:
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name in available)


def _families_present(catalog: Catalog, config: Config) -> frozenset[str]:
    """The families a config's ladder reaches: the first declared family
    always, plus every family up to the dearest one bound by a rung's
    unit. Rungs naming no declared unit are ignored."""
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


# Where the catalog file comes from.


def catalog_path() -> Path:
    """The catalog file: the copy packaged inside `mcgyvr/data` when it is
    there, otherwise `data/` in the source checkout this module sits in.
    Raises `CatalogError` when neither exists."""
    found = shipped_file(CATALOG_FILENAME)
    if found is not None:
        return found
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
    """Build the `TaskType` tuple for one JSON list, resolving each entry's
    `starts_on`, `use_case` and `required_evidence` against the declared
    ones. `reserved` carries the names already taken across both lists, so
    a name is declared once. Any missing key, unknown reference or repeat
    raises `CatalogError` naming the entry."""
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
                task_type=str(entry.get("task_type", "")),
            )
        )
    return tuple(entries)


def load(path: Path | None = None) -> Catalog:
    """Read and validate the catalog at `path`, defaulting to
    `catalog_path()`. Raises `CatalogError` for a file that cannot be read or
    is not JSON, for a `schema_version` this build does not read, for a file
    declaring no families, use cases or task types, for an evidence kind
    whose baseline contradicts `needs_commands`, and for an operation naming
    a task type that is not declared."""
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
    """The catalog, loaded once and cached for the process."""
    return load()
