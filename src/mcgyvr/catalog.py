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
  Deliberately a *family* (deterministic → local → api, ADR-0001 boundary 3)
  rather than a rung: rung names are chosen by whoever wrote the config, so a
  catalog naming rungs would only be valid on the machine it was written for. A
  family resolves against any ladder, because a rung is ``api`` exactly when its
  source declares an ``api_key_env``.
* **Required evidence** — what a contract of this type must carry to be
  judgeable. Evidence needing a command to produce it is enforced at contract
  load, so a type that promises a test demonstrated the fix cannot be dispatched
  with nothing to run.

The start is a floor, and it is the *type's* floor only. Risk raises it per
contract (#16) and escalation climbs from it (#24); neither is decided here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

CATALOG_FILENAME = "task-catalog.json"
SCHEMA_VERSION = 1


class CatalogError(Exception):
    """The catalog is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Family:
    """One family of the ladder, and where it sits in the cheap-to-dear order."""

    name: str
    rank: int
    doc: str


@dataclass(frozen=True)
class Evidence:
    """One kind of evidence a task type can require.

    ``needs_commands`` is the load-bearing bit: evidence a structural check can
    produce costs a contract nothing to declare, while evidence that only a
    command can produce means a contract with no acceptance commands cannot
    supply it. That distinction is enforced rather than documented.
    """

    name: str
    doc: str
    needs_commands: bool


@dataclass(frozen=True)
class TaskType:
    """One kind of work mcgyvr knows how to be asked for."""

    name: str
    starts_on: Family
    guarantee: str
    required_evidence: tuple[Evidence, ...]
    warrant: str
    doc: str

    @property
    def deterministic(self) -> bool:
        """Whether the deterministic tier executes this type outright.

        Derived from the starting family rather than declared, so the two can
        never disagree — the same move ADR-0003 makes for binding names.
        """
        return self.starts_on.rank == 0

    @property
    def needs_acceptance_commands(self) -> bool:
        """Whether a contract of this type is unjudgeable without commands."""
        return any(e.needs_commands for e in self.required_evidence)

    @property
    def evidence_names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.required_evidence)


@dataclass(frozen=True)
class Excluded:
    """An inherited type that did not survive validation, kept with its reason.

    Removals are recorded rather than deleted for the same reason the capability
    table keeps its known-bad measurements: the next person to reach for
    ``multi_file_refactor`` should find out why it is absent instead of
    rediscovering it.
    """

    name: str
    reason: str
    superseded_by: str | None


@dataclass(frozen=True)
class Catalog:
    """The loaded catalog."""

    families: tuple[Family, ...]
    evidence_kinds: tuple[Evidence, ...]
    task_types: tuple[TaskType, ...]
    excluded: tuple[Excluded, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.task_types)

    def get(self, name: str) -> TaskType | None:
        return next((t for t in self.task_types if t.name == name), None)

    def require(self, name: str) -> TaskType:
        """The type called ``name``, or a rejection naming the vocabulary.

        An unknown task type is exactly the case where a caller needs to see the
        valid set rather than a boolean.
        """
        found = self.get(name)
        if found is None:
            raise CatalogError(
                f"{name!r} is not a known task type. Valid: {', '.join(self.names)}"
            )
        return found

    def excluded_entry(self, name: str) -> Excluded | None:
        return next((e for e in self.excluded if e.name == name), None)

    def family(self, name: str) -> Family:
        found = next((f for f in self.families if f.name == name), None)
        if found is None:
            valid = ", ".join(f.name for f in self.families)
            raise CatalogError(f"{name!r} is not a known family. Valid: {valid}")
        return found

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
        catalog.family(
            "api" if config.sources[tier.source].requires_credential else "local"
        ).rank
        for tier in config.ladder.tiers
        if tier.source in config.sources
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

    evidence = tuple(
        Evidence(
            name=str(e["name"]),
            doc=str(e.get("doc", "")),
            needs_commands=bool(e.get("needs_commands", False)),
        )
        for e in raw.get("evidence_kinds", [])
    )
    by_evidence = {e.name: e for e in evidence}
    by_family = {f.name: f for f in families}

    task_types: list[TaskType] = []
    seen: set[str] = set()
    for entry in raw.get("task_types", []):
        name = str(entry.get("name", ""))
        where = f"task_types[{name or len(task_types)}]"
        _require_keys(
            entry, ("name", "starts_on", "guarantee", "required_evidence"), where
        )
        if name in seen:
            raise CatalogError(f"{where}: {name!r} is declared more than once")
        seen.add(name)

        family = by_family.get(str(entry["starts_on"]))
        if family is None:
            raise CatalogError(
                f"{where}: starts_on {entry['starts_on']!r} is not a declared "
                f"family. Valid: {', '.join(by_family)}"
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

        task_types.append(
            TaskType(
                name=name,
                starts_on=family,
                guarantee=str(entry["guarantee"]),
                required_evidence=tuple(kinds),
                warrant=str(entry.get("warrant", "")),
                doc=str(entry.get("doc", "")),
            )
        )

    if not task_types:
        raise CatalogError(f"{path} declares no task types")

    excluded = tuple(
        Excluded(
            name=str(e["name"]),
            reason=str(e["reason"]),
            superseded_by=e.get("superseded_by"),
        )
        for e in raw.get("excluded", [])
    )
    for gone in excluded:
        if gone.name in seen:
            raise CatalogError(
                f"excluded[{gone.name}]: {gone.name!r} is also a declared task "
                f"type. A type is in the vocabulary or it is not."
            )
        if gone.superseded_by and gone.superseded_by not in seen:
            raise CatalogError(
                f"excluded[{gone.name}]: superseded_by "
                f"{gone.superseded_by!r} is not a declared task type"
            )

    return Catalog(
        families=families,
        evidence_kinds=evidence,
        task_types=tuple(task_types),
        excluded=excluded,
    )


_CACHED: Catalog | None = None


def catalog() -> Catalog:
    """The shipped catalog, loaded once.

    The file ships with the package and cannot change under a running process,
    so re-reading it per contract would be cost with no meaning.
    """
    global _CACHED
    if _CACHED is None:
        _CACHED = load()
    return _CACHED
