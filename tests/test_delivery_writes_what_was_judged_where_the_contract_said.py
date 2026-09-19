"""Delivery writes exactly what was accepted, to where the contract said, against
the tree it was judged on.

Six ways the pipeline from a verdict to the bytes on disk came apart:

* ``run --commit`` committed over a target someone else committed to during the
  run; ``place`` refused that case and ``deliver`` did not.
* ``place`` wrote an :class:`~mcgyvr.deliver.Accepted` the gate rejected, or one
  whose bytes no longer answer for its digest; ``deliver`` refused both.
* The acceptance commands were timed by the default config's
  ``task_timeout_s``, not by the config the run was given with ``--config``.
* ``rename_symbol`` cut lines where ``str.splitlines`` cuts them while the index
  numbered them where the parser does, rewrote CRLF files as LF, raised on a
  byte strict UTF-8 refuses after writing earlier files, and reported success
  when it renamed nothing the index found.
* The contract loader and delivery each had a definition of "this target is a
  pattern", and they disagreed about ``]``.
* Two dependencies from one file made the decomposer emit a contract its own
  loader rejects.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import contract as contract_module
from mcgyvr.contract import load
from mcgyvr.deliver import Accepted, DeliveryRefusedError, deliver, place
from mcgyvr.gate import GateResult
from mcgyvr.orchestrator import index as index_module
from mcgyvr.orchestrator.decompose import DepRef, Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import Index, SymbolTable, build_index
from mcgyvr.rename import RenameError
from mcgyvr.rename import apply as rename_apply
from tests import livejournal as lj


def _accepted(repo: Path, contract: Any, text: str) -> Accepted:
    """An `Accepted` minted the only way one can be: read off a tree."""
    (repo / contract.target).write_text(text, encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    lj.git(repo, "checkout", "--", contract.target)
    return bound


# --- PIPE-02: the commit path refuses a target that moved during the run ------


def test_a_commit_refuses_a_target_committed_to_after_the_run_started(
    tmp_path: Path,
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    # Someone commits to the target while the ladder is climbing.
    (repo / contract.target).write_text("x = 2\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "meanwhile")
    head = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "VALUE = 1\n")

    result = deliver(repo=repo, contract=contract, content=bound, base=base)

    assert not result.committed, (
        "the accepted bytes were judged against the base copy; committing them "
        "reverts the commit made during the run"
    )
    assert head[:12] in result.reason
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / contract.target).read_text() == "x = 2\n"
    assert lj.git(repo, "status", "--porcelain") == ""


# --- PIPE-08: place refuses a verdict deliver refuses --------------------------


def test_place_refuses_an_accepted_the_gate_rejected(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    rejected = dataclasses.replace(
        _accepted(repo, contract, "VALUE = 1\n"), accepted=False
    )

    with pytest.raises(DeliveryRefusedError, match="did not accept"):
        place(repo=repo, contract=contract, content=rejected, base=base)

    assert (repo / contract.target).read_text() == "x = 0\n"
    assert lj.git(repo, "status", "--porcelain") == ""


def test_place_refuses_an_accepted_whose_bytes_left_their_digest(
    tmp_path: Path,
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    swapped = dataclasses.replace(
        _accepted(repo, contract, "VALUE = 1\n"), content="VALUE = 2\n"
    )

    with pytest.raises(DeliveryRefusedError, match="not the content its verdict"):
        place(repo=repo, contract=contract, content=swapped, base=base)

    assert (repo / contract.target).read_text() == "x = 0\n"


# --- PIPE-03: acceptance is timed by the run's own --config --------------------

FORMAT_WITH_SLOW_ACCEPTANCE = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
acceptance: ["python3 -c 'import time; time.sleep(6)'"]
scope:
  allow: ["src/**"]
"""


@pytest.mark.skipif(shutil.which("ruff") is None, reason="the floor runs ruff")
def test_the_acceptance_ceiling_is_the_run_configs_not_the_default_one(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT_WITH_SLOW_ACCEPTANCE)
    # The default location allows a minute; the config this run names, one second.
    default = lj.append_policy(
        lj.make_config(tmp_path / "default"), "task_timeout_s: 60\n"
    )
    monkeypatch.setenv("MCGYVR_CONFIG", str(default))
    named = lj.append_policy(lj.make_config(tmp_path / "named"), "task_timeout_s: 1\n")

    started = time.monotonic()
    code = lj.main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(named),
        ]
    )
    elapsed = time.monotonic() - started

    out = capsys.readouterr()
    assert elapsed < 5, (
        f"--config set a 1s ceiling and the acceptance command ran {elapsed:.1f}s: "
        f"it was timed by the default config's 60s"
    )
    assert code != 0, f"stdout: {out.out}\nstderr: {out.err}"


# --- PIPE-04: rename cuts and decodes the file as the index did -----------------


def _renamed_repo(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True)
    for name, data in files.items():
        (root / name).write_bytes(data)
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-qm", "base")
    return root


def test_a_form_feed_does_not_shift_the_line_rename_edits(tmp_path: Path) -> None:
    repo = _renamed_repo(
        tmp_path / "repo",
        {"m.py": b"# a\x0cb\ndef fetch_page():\n    pass\n\n\nfetch_page()\n"},
    )

    report = rename_apply(repo, "fetch_page", "get_page")

    assert (repo / "m.py").read_bytes() == (
        b"# a\x0cb\ndef get_page():\n    pass\n\n\nget_page()\n"
    )
    assert report.occurrences == 2


def test_a_crlf_file_keeps_its_line_endings(tmp_path: Path) -> None:
    repo = _renamed_repo(
        tmp_path / "repo",
        {"m.py": b"def fetch_page():\r\n    pass\r\n\r\n\r\nfetch_page()\r\n"},
    )

    rename_apply(repo, "fetch_page", "get_page")

    assert (repo / "m.py").read_bytes() == (
        b"def get_page():\r\n    pass\r\n\r\n\r\nget_page()\r\n"
    )


def test_a_byte_strict_utf8_refuses_is_renamed_around_not_raised_on(
    tmp_path: Path,
) -> None:
    """The index reads it; the rename must too, and must not half-apply first.

    JavaScript, because its extractor reads a file holding a byte strict UTF-8
    refuses, and the rename then met that file after rewriting ``a.js``.
    """
    repo = _renamed_repo(
        tmp_path / "repo",
        {
            "a.js": b"export function fetchPage() {}\n",
            "b.js": b'// caf\xe9\nimport { fetchPage } from "./a.js";\nfetchPage();\n',
        },
    )

    report = rename_apply(repo, "fetchPage", "getPage")

    assert (repo / "a.js").read_bytes() == b"export function getPage() {}\n"
    assert (repo / "b.js").read_bytes() == (
        b'// caf\xe9\nimport { getPage } from "./a.js";\ngetPage();\n'
    )
    assert report.files == ("a.js", "b.js")


def test_a_rename_that_substitutes_nothing_the_index_found_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index and the file disagree about every line: nothing is renamed,
    and that is not reported as a rename."""
    original = b"def fetch_page():\n    pass\n"
    repo = _renamed_repo(tmp_path / "repo", {"m.py": original})

    def elsewhere(root: Path, **kwargs: Any) -> Index:
        built = index_module.build_index(root, **kwargs)
        moved = tuple(
            dataclasses.replace(symbol, line=symbol.line + 100)
            for symbol in built.symbols.all()
        )
        return dataclasses.replace(built, symbols=SymbolTable(moved))

    monkeypatch.setattr("mcgyvr.rename.build_index", elsewhere)

    with pytest.raises(RenameError):
        rename_apply(repo, "fetch_page", "get_page")

    assert (repo / "m.py").read_bytes() == original


# --- SEAM-01: one definition of "this target is a pattern" ----------------------

BRACKET_TARGET = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: "src/pkg/a]b.py"
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def test_a_target_the_loader_takes_as_one_file_is_delivered_as_one_file(
    tmp_path: Path,
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = contract_module.loads(BRACKET_TARGET)
    (repo / contract.target).write_text("VALUE = 1\n", encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    (repo / contract.target).unlink()

    result = deliver(repo=repo, contract=contract, content=bound)

    assert result.committed, result.reason
    assert lj.git(repo, "show", "HEAD:src/pkg/a]b.py") == "VALUE = 1\n"


# --- ORC-7: two dependencies from one file are one dependency entry -------------


def test_two_symbols_from_one_file_emit_a_contract_the_loader_takes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "util.py").write_text(
        "def first(x: int) -> int:\n    return x\n\n\n"
        "def second(y: str) -> str:\n    return y\n"
    )
    (root / "main.py").write_text("def main():\n    return 0\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-qm", "seed")
    proposal = Proposal(
        task_type="bug_fix",
        task="main() should use both helpers.",
        target="main.py",
        interface="main() -> int",
        deps=(
            DepRef("util.py", "first", "call this first"),
            DepRef("util.py", "second", "then this"),
        ),
        stop_conditions=("a helper's contract is ambiguous",),
        acceptance=("pytest -q",),
        demonstration=("pytest -q tests/test_main.py",),
    )

    result = decompose(
        build_index(root), "use the helpers", propose=RecordedProposer((proposal,))
    )

    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    (dep,) = built.deps
    assert dep.path == "util.py"
    assert "def first(x: int) -> int" in dep.signature
    assert "def second(y: str) -> str" in dep.signature
    assert "call this first" in dep.note
    assert "then this" in dep.note
