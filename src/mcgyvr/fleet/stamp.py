"""A green sample stamps its fleet: the stamp folder, and no lock.

Owner, Round 4 (2026-10-07), FLEET FLOW TWEAK: sample GREEN = fleet STAMPED;
sample red = no stamp, and why. Owner, 2026-10-14: "one script that locks a
fleet, one script that stamps a fleet without locking". Plan section 8.2: the
sample's results are the dev-run evidence ``mcgyvr fleet lock`` reads.

:func:`stamp` judges the sample (:func:`mcgyvr.fleet.sample.judge`) and, only
when it is green, writes the stamp folder ``<data folder>/stamps/<fleet>/
<run_id>/`` (:func:`folder`; owner call, Round 8): ``setup/`` (the staged
``fleet.yaml`` and ``policy.yaml``) and ``evidence.json``. That is all a stamp
is. Locking it is :func:`mcgyvr.fleet.lock.write_from_stamp`'s (``mcgyvr fleet
lock --stamp DIR``), which writes the lock into the stamp folder as a dev root
of its own, so a stamp from an install needs no lab checkout; from there the
fleet takes the path every live fleet takes, promote then use
(:mod:`mcgyvr.fleet.promote`). Nothing is started or stopped here: what runs is
the sample's.

A red sample is "no stamp", by its own reasons, and leaves nothing behind: the
folder is built beside its place and renamed in only once it is whole.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.fleet.roots import FolderError, data_home, is_live
from mcgyvr.fleet.sample import Sample, SampleError, judge

#: The folder of stamps under the data folder.
STAMPS_DIR = "stamps"
#: The staged setup, as a stamp folder keeps it.
SETUP_DIR = "setup"
#: The dev-run evidence the lock is written from.
EVIDENCE_FILE = "evidence.json"
#: The two files a staged setup holds.
SETUP_FILES = ("fleet.yaml", "policy.yaml")


@dataclass(frozen=True)
class Stamp:
    """What :func:`stamp` did: the stamp folder written, or why not."""

    fleet: str
    #: The stamp folder under the data folder; ``None`` when nothing was stamped.
    folder: Path | None = None
    #: Why nothing was stamped, one reason per line.
    why: tuple[str, ...] = ()

    @property
    def green(self) -> bool:
        return self.folder is not None

    def lines(self) -> list[str]:
        """What a caller prints: the stamp and where it is, or each reason."""
        if self.folder is not None:
            return [
                f"stamped: {self.fleet} ({self.folder})",
                f"lock it: mcgyvr fleet lock --stamp {self.folder}",
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


def stamp(sample: Sample, *, run_id: str) -> Stamp:
    """Write ``sample``'s stamp folder when the sample is green; say why not
    otherwise. Nothing is locked, promoted or named live here."""

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
    except FolderError as exc:
        return red(f"stamp: {exc}")
    if target.exists() or target.is_symlink():
        return red(f"stamp: {target} already exists: sample run {run_id} was stamped")

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
        if target.exists() or target.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
            return red(f"stamp: {target} appeared while the stamp was being written")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return Stamp(fleet=sample.fleet, folder=target)
