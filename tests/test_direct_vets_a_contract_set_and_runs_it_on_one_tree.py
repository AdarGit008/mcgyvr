"""`mcgyvr direct FILE... | DIR` vets the contracts it is given, runs them as one tree.

The contracts are someone's own, not a proposer's, and from there the process
is the bare verb's: each is put to the checks a proposal is put to
(`mcgyvr.vet`, through `decompose.emit_one`), a refusal is printed with what
to change and logged, and what passed is dispatched by `_run_delegated` on one
dependency tree, so `depends_on` is honoured. The runs below are real: each
contract is a deterministic `operation: format` on a real repository, so no
model is asked, and `landed` is read from what HEAD holds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.cli.commands.run import _run as run_one
from mcgyvr.delegate_log import DelegateKind, read
from tests import livejournal as lj

MESSY = "x   =  { 'k' :1 }\ny=[1,\n2]\n"

FORMAT = """\
id: {cid}
task_type: code
operation: format
task: Reformat the module.
target: {target}
scope:
  allow: ["{target}"]
"""


@pytest.fixture
def repo(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lj.clean_env(monkeypatch, home)
    root = tmp_path / "work"
    (root / "src" / "pkg").mkdir(parents=True)
    for name in "abc":
        (root / "src" / "pkg" / f"{name}.py").write_text(MESSY)
    (root / ".gitignore").write_text("__pycache__/\n")
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-q", "-m", "base")
    return root


def contract(
    folder: Path, cid: str, target: str, *, depends_on: tuple[str, ...] = ()
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    text = FORMAT.format(cid=cid, target=target)
    if depends_on:
        text += f"depends_on: {json.dumps(list(depends_on))}\n"
    path = folder / f"{cid}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def direct(tmp_path: Path, repo: Path, *named: Path | str, extra: tuple[str, ...] = ()):  # type: ignore[no-untyped-def]
    """`mcgyvr direct` on `named`, journaled under the test, with a log; its
    exit and the log read back."""
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=tmp_path / "journal")
    log = tmp_path / "log.json"
    argv = ["direct", *map(str, named), "--repo", str(repo), "--sandbox", "tempdir"]
    argv += ["--config", str(config), "--commit", "--session", "s1", "--log", str(log)]
    code = lj.main([*argv, *extra])
    return code, read(log)


def results(tmp_path: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted((tmp_path / "journal" / "results").glob("*.json")):
        doc = json.loads(path.read_text())
        found[doc["contract"]] = doc
    return found


def committed(repo: Path) -> list[str]:
    """The subjects of the commits on HEAD, oldest first, the seed left out."""
    return lj.git(repo, "log", "--reverse", "--format=%s").splitlines()[1:]


def test_a_directory_of_three_runs_as_one_tree_and_honours_depends_on(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "contracts"
    # `tidy-a` waits on `tidy-c`, which sorts after it: the tree, not the
    # order of the files, decides what runs first.
    contract(folder, "tidy-a", "src/pkg/a.py", depends_on=("tidy-c",))
    contract(folder, "tidy-b", "src/pkg/b.py")
    contract(folder, "tidy-c", "src/pkg/c.py")
    started: list[str] = []
    real = run_one

    def watched(args):  # type: ignore[no-untyped-def]
        started.append(Path(args.contract).stem)
        return real(args)

    monkeypatch.setattr(command, "_run", watched)

    code, log = direct(tmp_path, repo, folder)

    assert code == 0
    assert started.index("tidy-c") < started.index("tidy-a")
    assert set(started) == {"tidy-a", "tidy-b", "tidy-c"}
    assert {r["outcome"] for r in results(tmp_path).values()} == {"accepted"}
    (tree,) = (tmp_path / "journal" / "trees").glob("*.json")
    rows = json.loads(tree.read_text())["contracts"]
    assert {r["contract"]: r["state"] for r in rows} == dict.fromkeys(
        ("tidy-a", "tidy-b", "tidy-c"), "landed"
    )
    assert log.kind is DelegateKind.EMITTED
    assert log.message == "3 contract(s) vetted."
    assert [c.path for c in log.contracts] == [
        str(folder / f"tidy-{n}.yaml") for n in "abc"
    ]


def test_files_are_named_one_by_one_too(tmp_path: Path, repo: Path) -> None:
    folder = tmp_path / "contracts"
    one = contract(folder, "tidy-b", "src/pkg/b.py")

    code, log = direct(tmp_path, repo, one)

    assert code == 0
    assert committed(repo) == ["tidy-b: Reformat the module."]
    assert [c.id for c in log.contracts] == ["tidy-b"]


def test_a_refused_contract_is_printed_with_what_to_change_and_the_rest_runs(
    tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-a", "src/pkg/a.py")
    contract(folder, "tidy-gone", "src/pkg/gone.py")
    contract(folder, "tidy-waits", "src/pkg/b.py", depends_on=("tidy-gone",))

    code, log = direct(tmp_path, repo, folder)

    err = capsys.readouterr().err
    assert code == 0
    assert committed(repo) == ["tidy-a: Reformat the module."]
    gone, waits = str(folder / "tidy-gone.yaml"), str(folder / "tidy-waits.yaml")
    assert f"refused: {gone}: no such file in the index" in err
    assert "change: name a path the index holds" in err
    assert log.kind is DelegateKind.EMITTED_WITH_REFUSALS
    by_file = {r.subject: r for r in log.refusals}
    assert set(by_file) == {gone, waits}
    assert by_file[gone].field == "target"
    assert by_file[gone].what_to_change.startswith("name a path the index holds")
    # What waits on a refused contract could never start: it is refused too.
    assert by_file[waits].field == "depends_on"
    assert "tidy-gone" in by_file[waits].reason


def test_a_set_with_nothing_that_passes_is_none_emitted_and_runs_nothing(
    tmp_path: Path, repo: Path
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-gone", "src/pkg/gone.py")
    (folder / "broken.yaml").write_text("id: broken\ntask_type: code\n")
    # The same id twice: the second file is refused, whatever it holds.
    twin = folder / "twin.yaml"
    twin.write_text(FORMAT.format(cid="tidy-gone", target="src/pkg/a.py"))

    code, log = direct(tmp_path, repo, folder)

    assert code == 3
    assert committed(repo) == []
    assert not (tmp_path / "journal" / "results").exists()
    assert log.kind is DelegateKind.NONE_EMITTED
    by_file = {Path(r.subject).name: r for r in log.refusals}
    assert set(by_file) == {"broken.yaml", "tidy-gone.yaml", "twin.yaml"}
    assert by_file["broken.yaml"].what_to_change
    assert by_file["twin.yaml"].field == "id"


def test_the_same_unit_of_work_twice_is_refused_as_a_proposal_is(
    tmp_path: Path, repo: Path
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-1", "src/pkg/a.py")
    contract(folder, "tidy-2", "src/pkg/a.py")

    code, log = direct(tmp_path, repo, folder)

    assert code == 0
    (refusal,) = log.refusals
    assert refusal.subject == str(folder / "tidy-2.yaml")
    assert refusal.field == "task"
    assert "duplicates contract" in refusal.reason


def test_output_writes_what_passed_vetting_and_runs_nothing(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-a", "src/pkg/a.py")
    contract(folder, "tidy-gone", "src/pkg/gone.py")
    out = tmp_path / "vetted"
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=tmp_path / "journal")

    # No session: nothing runs, so none is needed.
    argv = ["direct", str(folder), "--repo", str(repo), "--config", str(config)]
    code = lj.main([*argv, "--output", str(out)])

    assert code == 0
    assert [p.name for p in out.iterdir()] == ["tidy-a.json"]
    assert committed(repo) == []


def test_notes_from_seeds_the_contract_its_result_names_and_result_is_one_file(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-a", "src/pkg/a.py")
    contract(folder, "tidy-b", "src/pkg/b.py")
    earlier = tmp_path / "earlier.json"
    earlier.write_text(json.dumps({"contract": "tidy-b", "attempts": []}))
    handed: dict[str, Any] = {}

    def run(args):  # type: ignore[no-untyped-def]
        handed[Path(args.contract).stem] = (args.notes_from, args.result)
        return 0

    monkeypatch.setattr(command, "_run", run)

    code, _ = direct(tmp_path, repo, folder, extra=("--notes-from", str(earlier)))

    assert code == 0
    assert handed == {"tidy-a": (None, None), "tidy-b": (str(earlier), None)}

    handed.clear()
    mine = tmp_path / "mine.json"
    code, _ = direct(
        tmp_path, repo, folder / "tidy-a.yaml", extra=("--result", str(mine))
    )
    assert handed == {"tidy-a": (None, str(mine))}


def test_a_seed_for_no_contract_in_the_set_is_refused_before_any_run(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "contracts"
    contract(folder, "tidy-a", "src/pkg/a.py")
    stray = tmp_path / "stray.json"
    stray.write_text(json.dumps({"contract": "someone-else"}))
    monkeypatch.setattr(command, "_run", lambda args: pytest.fail("it ran"))

    code, log = direct(tmp_path, repo, folder, extra=("--notes-from", str(stray)))

    assert code == 2
    assert log.kind is DelegateKind.USAGE_INVALID
    assert "someone-else" in log.message
