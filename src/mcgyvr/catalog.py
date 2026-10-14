"""Reader for the decomposition catalog — the vocabulary of what may be asked for.

The catalog (``data/task-catalog.json``) is *data*, and the acceptance
criterion for this module is that it stays that way: adding a task type must be
an edit to that file and nothing else. So there are no per-type branches here,
no name is written down twice, and nothing downstream may match on a type name
— it asks the entry what it guarantees instead. ``tests/test_catalog.py``
enforces this by inventing a type in a temporary file and driving it through
contract validation: a source scan can be satisfied by a file that still
branches, but a type that exists nowhere in the repository cannot load unless
the code really is generic over the vocabulary.

Each entry states three things the rest of the system needs:

* **A guarantee** — what accepting a change of this type actually promises.
  This is the sentence a caller is owed, and it is why some inherited types are
  not here: a type whose guarantee cannot be stated is one nothing can accept.
* **A starting family** — where on the ladder work of this type may begin.
  Deliberately a *family* (deterministic → local → api) rather than a rung: rung
  names are chosen by whoever wrote the config, so a catalog naming rungs would
  only be valid on the machine it was written for. A family resolves against any
  ladder, because a rung is ``api`` exactly when its unit declares an
  ``api_key_env``.
* **Required evidence** — what a contract of this type must carry to be
  judgeable. Evidence needing a command to produce it is enforced at contract
  load, so a type that promises a test demonstrated the fix cannot be dispatched
  with nothing to run.

The start is a floor, and it is the *type's* floor only; escalation climbs
from it, and that is not decided here.

The vocabulary is four task types — ``code``, ``chat``, ``agent`` and ``media``
— and a set of **deterministic operations** that are not task types. An
operation is an entry of the same shape that names the task type a contract
asks for it under: ``task_type: code`` with ``operation: format`` is how a
contract has a tool do the work. The one place a name that used to be a task
type survives is :data:`RETIRED_TASK_TYPES`, so a contract that still names one
is told what replaced it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config, Unit

CATALOG_FILENAME = "task-catalog.json"
SCHEMA_VERSION = 2

#: Names that used to be task types, and the spelling that replaced each. Not
#: vocabulary: nothing resolves to these. They are kept only so a contract or a
#: caller that still names one is refused with the replacement rather than with
#: a bare "unknown" — the one table where an old name survives.
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
    """The catalog is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Family:
    """One family of the ladder, and where it sits in the cheap-to-dear order."""

    name: str
    rank: int
    doc: str


@dataclass(frozen=True)
class UseCase:
    """One use case the vocabulary serves; task types are grouped by it."""

    name: str
    doc: str


@dataclass(frozen=True)
class Evidence:
    """One kind of evidence a task type can require.

    ``needs_commands`` is the load-bearing bit: evidence a structural check can
    produce costs a contract nothing to declare, while evidence that only a
    command can produce means a contract with no commands cannot supply it.
    That distinction is enforced rather than documented.

    ``baseline`` says what those commands must do on the *unchanged* tree —
    ``"pass"`` for a regression signal, ``"fail"`` for a demonstration
    (``failing_test_first``: a command that does not fail before the change
    demonstrates nothing). The two expectations are opposite, so they cannot
    share one contract list; ``baseline`` is what routes a kind to the right
    one (``acceptance`` vs ``demonstration``, #183) without any consumer
    naming a kind. Only meaningful where ``needs_commands`` is true — a
    structural check has no baseline run.
    """

    name: str
    doc: str
    needs_commands: bool
    baseline: str = "pass"


@dataclass(frozen=True)
class TaskType:
    """One kind of work mcgyvr knows how to be asked for."""

    name: str
    starts_on: Family
    use_case: UseCase
    guarantee: str
    required_evidence: tuple[Evidence, ...]
    warrant: str
    doc: str
    #: For a deterministic operation, the task type a contract names to ask for
    #: it (``task_type: code`` with ``operation: <name>``); empty on a task
    #: type itself.
    task_type: str = ""
    #: Whether this type's evidence is computed per contract from the
    #: contract's own fields rather than read off ``required_evidence``. Only
    #: ``code`` sets it: its evidence is ``gate`` plus the kinds its
    #: ``demonstration``, ``acceptance``, ``no_semantic_change`` and
    #: ``type_check`` fields derive. The derivation itself lives in
    #: :mod:`mcgyvr.contract`, because it reads contract fields this module
    #: deliberately knows nothing about.
    evidence_derived: bool = False
    #: Whether a run of this type is a session: its reply is the answer,
    #: returned in the result file and kept in the journal's session log, and
    #: nothing is written to the tree — so a contract of it names no
    #: ``target`` and no ``scope``. ``chat`` and ``agent`` set it (owner
    #: decision, e2e run 1 F7: "chat and agent are sessions and should be
    #: logged as such").
    session: bool = False

    @property
    def deterministic(self) -> bool:
        """Whether the deterministic tier executes this type outright.

        Derived from the starting family rather than declared, so the two can
        never disagree.
        """
        return self.starts_on.rank == 0

    @property
    def needs_acceptance_commands(self) -> bool:
        """Whether this type needs commands that pass at baseline (``acceptance``).

        Deliberately *not* "any command-needing evidence": a demonstration has
        the opposite baseline expectation and its own contract list, so each is
        checked against the list that can actually satisfy it (#183).
        """
        return any(
            e.needs_commands and e.baseline == "pass" for e in self.required_evidence
        )

    @property
    def needs_demonstration_commands(self) -> bool:
        """Whether this type needs commands failing at baseline (``demonstration``)."""
        return any(
            e.needs_commands and e.baseline == "fail" for e in self.required_evidence
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.required_evidence)

    @property
    def judges_a_change(self) -> bool:
        """Whether the gate judges work of this kind as a change to the tree.

        True where the kind carries the ``gate`` evidence, or derives its
        evidence per contract (which always starts at the gate): a change to
        a file, which a reviewer can be asked about. A kind that does neither
        is a reply — judged by the output checks it declares, if any, and
        never sent to a reviewer, because there is no change to review.
        """
        return self.evidence_derived or "gate" in self.evidence_names

    @property
    def needs_output_cap(self) -> bool:
        """Whether a contract of this kind must state ``limits.max_output_tokens``.

        True of the work mcgyvr's harness bounds: a change a model writes and
        the gate judges. Not of a session, which is a raw connection to a
        model, nor of a deterministic operation, which calls none, nor of a
        reply judged only by its output checks (``media``). Owner decision,
        2026-10-14 (e2e run 3 T1).
        """
        return not self.deterministic and not self.session and self.judges_a_change


@dataclass(frozen=True)
class Catalog:
    """The loaded catalog."""

    families: tuple[Family, ...]
    use_cases: tuple[UseCase, ...]
    evidence_kinds: tuple[Evidence, ...]
    task_types: tuple[TaskType, ...]
    operations: tuple[TaskType, ...]

    @property
    def names(self) -> tuple[str, ...]:
        """The model vocabulary: the task types a model may choose."""
        return tuple(t.name for t in self.task_types)

    def get(self, name: str) -> TaskType | None:
        """The task type called ``name``, or ``None``.

        Task types only: an operation is not one, and is resolved by
        :meth:`operation`.
        """
        return next((t for t in self.task_types if t.name == name), None)

    def require(self, name: str) -> TaskType:
        """The task type called ``name``, or a rejection naming what to use.

        An unknown task type is exactly the case where a caller needs to see the
        valid set rather than a boolean, and a name that used to be a task type
        is told what replaced it (:data:`RETIRED_TASK_TYPES`).
        """
        found = self.get(name)
        if found is None:
            if name in RETIRED_TASK_TYPES:
                raise CatalogError(f"{name!r} is now {RETIRED_TASK_TYPES[name]}.")
            raise CatalogError(
                f"{name!r} is not a known task type. Valid: {', '.join(self.names)}"
            )
        return found

    def operation(self, name: str) -> TaskType | None:
        """The deterministic operation called ``name``, or ``None``."""
        return next((t for t in self.operations if t.name == name), None)

    def require_operation(self, name: str) -> TaskType:
        """The deterministic operation called ``name``, or a rejection naming
        the valid ones."""
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
        """The declared evidence kind called ``name``.

        Looked up by name for the one type whose evidence is derived per
        contract: the derivation names kinds, and the catalog is the only
        place a name maps to the kind's ``needs_commands`` and ``baseline``.
        """
        found = next((e for e in self.evidence_kinds if e.name == name), None)
        if found is None:
            valid = ", ".join(e.name for e in self.evidence_kinds)
            raise CatalogError(f"{name!r} is not a known evidence kind. Valid: {valid}")
        return found

    def family_of(self, source: Unit) -> Family:
        """Which family a rung served by the unit ``source`` belongs to.

        The one definition of the rule, so that nothing else has to restate it:
        a rung is ``api`` exactly when its unit declares a credential, and
        ``local`` when it does not. It is deliberately a property of the
        *unit* rather than of the model — a 30B model on a keyless local box
        and a 30B model behind a hosted API differ in what they cost to ask,
        which is what the families order.

        Note what this cannot return. ``deterministic`` is not a rung on any
        ladder — it is tools, and it binds no source — so no configuration can
        produce it here. :mod:`mcgyvr.route` says what follows from that.
        """
        return self.family("api" if source.requires_credential else "local")

    # --- resolving against a configured ladder ----------------------------

    def unservable(self, config: Config) -> tuple[TaskType, ...]:
        """Types this configuration has no rung for, cheapest-first.

        The catalog's own acceptance says no entry may exist that no configured
        ladder can serve. That is checked against a *configuration*, not
        asserted in the abstract: a keyless install genuinely cannot serve a type
        that must start on `api`, and the honest answer is to say so by name
        rather than to route the work optimistically and fail at dispatch.
        """
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name not in available)

    def servable(self, config: Config) -> tuple[TaskType, ...]:
        available = _families_present(self, config)
        return tuple(t for t in self.task_types if t.starts_on.name in available)


def _families_present(catalog: Catalog, config: Config) -> frozenset[str]:
    """Which families a configuration can start work in.

    The deterministic family is always present — it is tools, and it needs no
    binding. Beyond that a rung is `api` when its source needs a credential and
    `local` when it does not.

    A starting family is a *floor*, so a rung satisfies it when the rung is at
    least as dear: work that may start on `local` is served perfectly well by an
    api-only ladder, just dearly. The reverse does not hold — a keyless install
    cannot serve a type that must start on `api`, and it is the dearest bound
    rung, not the cheapest, that decides how far up the floors can be met.
    """
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


# --- loading ---------------------------------------------------------------


def catalog_path() -> Path:
    """Locate the shipped catalog, whether running from a checkout or a wheel."""
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
    """Load and validate one catalog entry list (``task_types`` or operations).

    An operation is a task type in every respect except that it is not in the
    model vocabulary: same fields, same guarantee/starts_on/use_case/evidence
    rules, so the same walk loads both lists.
    """
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
    """Load and validate the catalog."""
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
    """The shipped catalog, loaded once.

    The file ships with the package and cannot change under a running process,
    so re-reading it per contract would be cost with no meaning.

    Memoised rather than held in a module variable, so no assignable name can
    replace the catalog under a running process, and for one more reason
    specific to this file: contract digest identity is derived from the catalog, and
    the lab's instruments script pins ``sha256(dumps(contract))`` as the
    evidence that a recorded run was run against a declared instrument. A
    module variable holding the catalog is therefore an assignable name that
    silently re-keys
    every contract in the process. Reloading is ``catalog.cache_clear()`` after
    repointing :func:`catalog_path`.
    """
    return load()
