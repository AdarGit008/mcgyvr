"""A green sample stamps its fleet: the existing chain, lock -> promote -> use.

Owner, Round 4 (2026-10-07), FLEET FLOW TWEAK: sample GREEN = fleet STAMPED
(approved, locked, reusable through ``mcgyvr fleet use``); sample red = no
stamp, and why. Plan section 8.2: the sample's results are the dev-run
evidence ``mcgyvr fleet lock`` reads, and then the chain runs unchanged.

:func:`stamp` judges the sample (:func:`mcgyvr.fleet.sample.judge`) and, only
when it is green:

1. writes the stamp folder ``<data folder>/stamps/<fleet>/<run_id>/``
   (:func:`folder`; owner call, Round 8): ``setup/`` (the staged
   ``fleet.yaml`` and ``policy.yaml``), ``evidence.json``, and the dev lock
   ``records/fleet/`` written by :func:`mcgyvr.fleet.lock.write` -- a dev root
   of its own, so a stamp from an install needs no lab checkout;
2. promotes the fleet from there (:func:`mcgyvr.fleet.promote.promote`) to
   ``<config folder>/fleets/<fleet>@<lock date>/``;
3. names it live (:func:`mcgyvr.fleet.promote.use`). Nothing is started or
   stopped here: what runs is the sample's.

A red sample, a lock refusal and a promotion refusal are all "no stamp", each
by its own reasons, and leave nothing behind: the folder is built beside its
place and renamed in only once the lock is written, and removed again when
promotion refuses. ``live.json`` is written last, and only on a promotion.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.fleet.promote import PromoteRefusedError, Switch, promote, use
from mcgyvr.fleet.roots import (
    FolderError,
    LiveFleetError,
    data_home,
    is_live,
    live_fleet,
)
from mcgyvr.fleet.sample import Sample, SampleError, judge

#: The folder of stamps under the data folder.
STAMPS_DIR = "stamps"
#: The staged setup, as a stamp folder keeps it.
SETUP_DIR = "setup"
#: The dev-run evidence the lock was written from.
EVIDENCE_FILE = "evidence.json"
#: The two files a staged setup holds.
SETUP_FILES = ("fleet.yaml", "policy.yaml")


@dataclass(frozen=True)
class Stamp:
    """What :func:`stamp` did: the fleet stamped and named live, or why not."""

    fleet: str
    #: The live name, ``<fleet>@<lock date>``; ``None`` when nothing was stamped.
    name: str | None = None
    #: The stamp folder under the data folder, kept only for a stamp.
    folder: Path | None = None
    #: The promoted fleet folder under the config folder.
    promoted: Path | None = None
    #: What naming it live did.
    switch: Switch | None = None
    #: Why nothing was stamped, one reason per line.
    why: tuple[str, ...] = ()

    @property
    def green(self) -> bool:
        return self.name is not None

    def lines(self) -> list[str]:
        """What a caller prints: the stamp and where it is, or each reason."""
        if self.name is not None:
            return [
                f"stamped: {self.name} ({self.promoted})",
                f"live: {self.name}",
                f"evidence: {self.folder}",
            ]
        return [f"no stamp: {self.fleet}", *(f"  {reason}" for reason in self.why)]


def stamps_dir() -> Path:
    """``<data folder>/stamps``: one folder per fleet, one per sample run in it."""
    return data_home() / STAMPS_DIR


def folder(fleet: str, run_id: str) -> Path:
    """``<data folder>/stamps/<fleet>/<run_id>``, the dev root of one stamp."""
    return stamps_dir() / fleet / run_id


def _plain(name: str) -> bool:
    return (
        bool(name) and name not in (".", "..") and "/" not in name and "@" not in name
    )


def _tolerances() -> dict[str, object]:
    from mcgyvr.derived import class_tolerances

    return {"warm_decode_class_pct": class_tolerances()["warm_decode_tok_s"]}


def stamp(sample: Sample, *, run_id: str) -> Stamp:
    """Stamp ``sample``'s fleet when the sample is green; say why not otherwise."""
    from mcgyvr.derived import DerivedNumbersError
    from mcgyvr.fleet import lock
    from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy

    def red(*why: str) -> Stamp:
        return Stamp(fleet=sample.fleet, why=tuple(why))

    if not _plain(sample.fleet) or not _plain(run_id):
        return red(
            f"stamp: {sample.fleet!r} at {run_id!r}: a fleet and a sample run are "
            "each a plain name, with no '/' or '@'"
        )
    try:
        verdict = judge(sample)
    except SampleError as exc:
        return red(f"sample: {exc}")
    if not verdict.green:
        return red(*verdict.why)
    if verdict.evidence is None:
        return red("sample: no evidence could be built from its reads")
    try:
        target = folder(sample.fleet, run_id)
        if is_live(stamps_dir()):
            return red(
                f"stamp: {stamps_dir()} lies under the config folder, where only "
                "promoted fleets live; move the data folder out of it"
            )
        live_fleet()
    except (FolderError, LiveFleetError) as exc:
        return red(f"stamp: {exc}")
    if target.exists() or target.is_symlink():
        return red(f"stamp: {target} already exists: sample run {run_id} was stamped")
    try:
        fleet = load_fleet((sample.setup / "fleet.yaml").read_text(encoding="utf-8"))
        policy = load_policy((sample.setup / "policy.yaml").read_text(encoding="utf-8"))
        tolerances = _tolerances()
    except (OSError, FleetFileError, DerivedNumbersError) as exc:
        return red(f"stamp: {exc}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=target.parent))
    try:
        (staging / SETUP_DIR).mkdir()
        for name in SETUP_FILES:
            shutil.copyfile(sample.setup / name, staging / SETUP_DIR / name)
        (staging / EVIDENCE_FILE).write_text(
            json.dumps(verdict.evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            lock.write(
                staging, fleet, verdict.evidence, policy=policy, tolerances=tolerances
            )
        except lock.LockRefusedError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return red(f"lock: the fleet lock refused the sample's evidence: {exc}")
        if target.exists() or target.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
            return red(f"stamp: {target} appeared while the stamp was being written")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    try:
        promoted = promote(target, target / SETUP_DIR, sample.fleet)
    except PromoteRefusedError as exc:
        shutil.rmtree(target, ignore_errors=True)
        return red(f"promote: {exc}")
    switch = use(promoted.name)
    return Stamp(
        fleet=sample.fleet,
        name=promoted.name,
        folder=target,
        promoted=promoted,
        switch=switch,
    )
