"""Stamp a sample that came out green: the staged setup and its evidence.

A stamp is a folder of its own under the data folder,
``<data folder>/stamps/<fleet>/<run_id>/``, holding a ``setup/`` copy of
`fleet.yaml` and `policy.yaml` and the ``evidence.json`` the sample's verdict
built. Nothing else is written: no lock, no promoted folder, no ``live.json``.
:func:`mcgyvr.fleet.lock.write_from_stamp` is what locks a stamp, and a
promotion starts from there.

A sample refused for any reason — an unusable name, a setup or a rig that
cannot be read, a red verdict, no evidence — stamps nothing and comes back as a
red :class:`Stamp` carrying the reasons. A green stamp is built in a staging
folder beside its target and renamed into place, so a failure part-way leaves
no half-stamp behind and a run id already stamped is refused, not overwritten.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.fleet.roots import FolderError, data_home, is_live
from mcgyvr.fleet.sample import Sample, SampleError, judge

#: The data folder's subfolder of stamps, one folder per fleet and sample run.
STAMPS_DIR = "stamps"
#: The stamp's copy of the staged setup, holding the two setup files below.
SETUP_DIR = "setup"
#: The dev-run evidence the sample's verdict built, which the lock is read from.
EVIDENCE_FILE = "evidence.json"
#: What a stamp copies out of `Sample.setup`, by the names the setup is read by.
SETUP_FILES = ("fleet.yaml", "policy.yaml")


@dataclass(frozen=True)
class Stamp:
    """What one sample's stamp came to: the fleet, and its folder when green.

    `folder` is the stamp folder that was written, and is ``None`` for a red
    sample, whose `why` holds the reasons and whose folder was never made.
    """

    fleet: str
    #: The stamp folder once it is written, or ``None`` when nothing was written.
    folder: Path | None = None
    #: Why the sample was not stamped; empty for a green stamp.
    why: tuple[str, ...] = ()

    @property
    def green(self) -> bool:
        return self.folder is not None

    def lines(self) -> list[str]:
        """The stamp as lines to print: its folder when green, else the reasons."""
        if self.folder is not None:
            return [f"stamped: {self.fleet} ({self.folder})"]
        return [f"no stamp: {self.fleet}", *(f"  {reason}" for reason in self.why)]


def stamps_dir() -> Path:
    """The folder holding every stamp, under the data folder."""
    return data_home() / STAMPS_DIR


def folder(fleet: str, run_id: str) -> Path:
    """The stamp folder of one sample run: ``<stamps>/<fleet>/<run_id>``."""
    return stamps_dir() / fleet / run_id


def _plain(name: str) -> bool:
    return (
        bool(name) and name not in (".", "..") and "/" not in name and "@" not in name
    )


def stamp(sample: Sample, *, run_id: str) -> Stamp:
    """Judge `sample` and, if it is green, write its stamp under `run_id`.

    The fleet and the run id must each be a plain name, the sample must judge
    green with evidence, the stamps folder must not lie under the config folder
    where only promoted fleets live, and the target folder must not exist yet;
    any of these stamps nothing and returns a red :class:`Stamp` with the
    reason. The stamp is otherwise built in a staging folder beside the target
    — the setup files copied in and the evidence written as sorted, indented
    JSON — then renamed into place, so a target that appeared meanwhile is
    refused and a failure part-way leaves nothing behind.
    """

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
