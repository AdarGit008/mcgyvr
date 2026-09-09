"""The lease has run on a real rig, once, and the record says so.

W4 (#423) put the lease on the rig: gate 2 takes ``~/.mcgyvr/lease`` before
any rig time is spent, a ``dev`` run yields to a ``live`` one, and the door
releases the lease on every way out. Every rig in those tests is the stub
behind the shims — nothing reached srv1 or srv2 — and the pull request says
so: *the first live run of the lease is the owner's.* Until that run is
filed, the lease is a mechanism the tree describes and no rig has held.

What must be observably true, in the tree, once it has happened:

* under ``records/evidence/`` an envelope holds a ``<RUN_ID>.run.json``
  header (gate 5, #422) whose ``profile`` is ``live`` and whose ``host`` is
  a rig ``tools/runs/hosts.json`` declares — the door ran, under the
  profile that takes the lease whatever holds it, against the fleet;
* that run is over: no ``.<RUN_ID>.running`` claim sits beside the header.
  The claim and the lease are released on the same way out, so a claim
  still there is a run the door never closed;
* the step ran: a file the step wrote sits beside the header, so the run
  got past the gates and spent rig time under the lease;
* the run names its product, and the product carries the lease:
  ``mcgyvr_version`` is a version at or above ``0.1.0`` — the first tag,
  cut on the merge of #424, above W4 — and not the fallback a tree with no
  git reads, nor the ``+uninstalled`` a never-installed tree says.

Nothing here reaches a machine. The test reads the record the run leaves;
the run itself is the owner's, on the rig, once.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "records" / "evidence"
DECLARATION = REPO / "tools" / "runs" / "hosts.json"

#: The first product that carries the lease.
FIRST_PRODUCT = (0, 1, 0)

#: A release: ``MAJOR.MINOR.PATCH`` at the front, whatever hatch-vcs appends.
RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

#: What a finished run's envelope holds that is not the step's own artifact:
#: the header, the claim, and gate 7's stamp beside a non-TSV artifact.
NOT_THE_STEP = (".run.json", ".running", ".RIGMOVED")


def fleet() -> set[str]:
    """The rigs this repository declares, from ``tools/runs/hosts.json``."""
    document = json.loads(DECLARATION.read_text(encoding="utf-8"))
    return set(document["hosts"])


def header_of(path: Path) -> dict[str, Any]:
    """The run header at ``path``, as gate 5 wrote it."""
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return record


def live_runs_on_a_rig() -> list[tuple[Path, dict[str, Any]]]:
    """Every recorded run of the door under ``live`` against a declared rig.

    The RED failure when there is none: the lease has never run on a rig.
    """
    rigs = fleet()
    found = [
        (path, record)
        for path in sorted(EVIDENCE.glob("*/*.run.json"))
        if (record := header_of(path)).get("profile") == "live"
        and record.get("host") in rigs
    ]
    if not found:
        pytest.fail(
            "the lease has never run on a rig: no <RUN_ID>.run.json under "
            f"records/evidence/ says profile=live on {' or '.join(sorted(rigs))}. "
            "Run the door under profile live against a declared rig, once, and "
            "file its envelope",
            pytrace=False,
        )
    return found


def test_the_lease_has_run_live_on_a_rig() -> None:
    """A live run against the fleet is recorded, and the door closed it."""
    for path, record in live_runs_on_a_rig():
        run_id = path.name.removesuffix(".run.json")
        assert record["run_id"] == run_id, (
            f"{path.relative_to(REPO)} is the header of {record['run_id']!r}, "
            f"filed under the name of {run_id!r}"
        )
        claim = path.with_name(f".{run_id}.running")
        assert not claim.exists(), (
            f"{claim.relative_to(REPO)} is still there: the door never closed "
            f"{run_id}, and the way out that releases the claim is the way out "
            "that releases the lease"
        )


def test_the_live_run_ran_its_step() -> None:
    """The run spent rig time under the lease: the step left its artifact."""
    for path, record in live_runs_on_a_rig():
        beside = [
            p.name
            for p in path.parent.iterdir()
            if p.is_file() and not p.name.endswith(NOT_THE_STEP)
        ]
        assert beside, (
            f"{path.parent.relative_to(REPO)} holds the header of "
            f"{record['run_id']} and nothing the step wrote: the gates ran and "
            "the step did not"
        )


def test_the_live_run_names_its_product() -> None:
    """The run says which product ran it, and that product carries the lease."""
    for path, record in live_runs_on_a_rig():
        version = str(record.get("mcgyvr_version", ""))
        found = RELEASE.match(version)
        assert found is not None and "+uninstalled" not in version, (
            f"{path.relative_to(REPO)} says mcgyvr_version={version!r}, which "
            "names no product: a live run is made under an installed release"
        )
        assert tuple(int(n) for n in found.groups()) >= FIRST_PRODUCT, (
            f"{path.relative_to(REPO)} says mcgyvr_version={version!r}, below "
            "v0.1.0: a product without the lease cannot have held one"
        )
