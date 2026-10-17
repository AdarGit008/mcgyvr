""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.fleet.roots import FolderError, data_home, is_live
from mcgyvr.fleet.sample import Sample, SampleError, judge

#
STAMPS_DIR = "stamps"
#
SETUP_DIR = "setup"
#
EVIDENCE_FILE = "evidence.json"
#
SETUP_FILES = ("fleet.yaml", "policy.yaml")


@dataclass(frozen=True)
class Stamp:
    ""

    fleet: str
    #
    folder: Path | None = None
    #
    why: tuple[str, ...] = ()

    @property
    def green(self) -> bool:
        return self.folder is not None

    def lines(self) -> list[str]:
        ""
        if self.folder is not None:
            return [f"stamped: {self.fleet} ({self.folder})"]
        return [f"no stamp: {self.fleet}", *(f"  {reason}" for reason in self.why)]


def stamps_dir() -> Path:
    ""
    return data_home() / STAMPS_DIR


def folder(fleet: str, run_id: str) -> Path:
    ""
    return stamps_dir() / fleet / run_id


def _plain(name: str) -> bool:
    return (
        bool(name) and name not in (".", "..") and "/" not in name and "@" not in name
    )


def stamp(sample: Sample, *, run_id: str) -> Stamp:
    ""

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
