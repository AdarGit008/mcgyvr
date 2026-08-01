"""The change set is the keystone of the gate: every check reads from it.

These tests hold it to the two properties the epic (#33) makes acceptance
criteria — a subprocess count that stays flat as the change grows, and
added-line attribution that matches a per-case reference exactly — and to the
failure modes a naive implementation would hit: untracked files, a repository
with no commit yet, deletions, binaries, and filenames that a quoting bug
would drop.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.changeset import (
    ChangeSet,
    ChangeSetError,
    FileChange,
    read_added_text,
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")


def commit_all(repo: Path, message: str = "base") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def change_for(repo: Path, path: str) -> FileChange:
    cs = ChangeSet.detect(repo)
    return next(f for f in cs if f.path == path)


def test_detect_rejects_a_non_repo(tmp_path: Path) -> None:
    with pytest.raises(ChangeSetError, match="not a git repository"):
        ChangeSet.detect(tmp_path)


def test_untracked_file_is_wholly_added(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "seed.txt").write_text("seed\n")
    commit_all(tmp_path)

    (tmp_path / "new.py").write_text("a = 1\nb = 2\nc = 3\n")
    change = change_for(tmp_path, "new.py")
    assert change.status == "A"
    assert change.added_line_numbers() == (1, 2, 3)


def test_repository_with_no_commit_attributes_everything(tmp_path: Path) -> None:
    """With no HEAD to diff against, the whole first change is added."""
    init_repo(tmp_path)
    (tmp_path / "first.py").write_text("x = 1\ny = 2\n")

    cs = ChangeSet.detect(tmp_path)
    assert cs.paths() == ("first.py",)
    assert cs.files[0].added_line_numbers() == (1, 2)


def test_pre_existing_lines_are_not_attributed(tmp_path: Path) -> None:
    """Only the worker's edit is attributed — untouched lines are not.

    This is the property the whole gate leans on: a check that fires on added
    lines must never be handed a line the worker did not write.
    """
    init_repo(tmp_path)
    (tmp_path / "m.py").write_text("one\ntwo\nthree\nfour\nfive\n")
    commit_all(tmp_path)

    # Change only line 3.
    (tmp_path / "m.py").write_text("one\ntwo\nTHREE\nfour\nfive\n")
    change = change_for(tmp_path, "m.py")
    assert change.added_line_numbers() == (3,)


def test_insertion_shifts_later_line_numbers(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "m.py").write_text("one\ntwo\nthree\n")
    commit_all(tmp_path)

    # Insert two lines after "one": the new lines are 2 and 3.
    (tmp_path / "m.py").write_text("one\nINS_A\nINS_B\ntwo\nthree\n")
    change = change_for(tmp_path, "m.py")
    assert change.added_line_numbers() == (2, 3)


def test_deletion_adds_nothing(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "gone.py").write_text("x\ny\n")
    commit_all(tmp_path)

    (tmp_path / "gone.py").unlink()
    change = change_for(tmp_path, "gone.py")
    assert change.status == "D"
    assert change.is_deletion
    assert change.added_line_numbers() == ()


def test_binary_change_is_flagged_not_attributed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02seed")
    commit_all(tmp_path)

    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03changed\xff")
    change = change_for(tmp_path, "blob.bin")
    assert change.is_binary
    assert change.added_line_numbers() == ()


def test_non_ascii_and_spaced_paths_are_not_dropped(tmp_path: Path) -> None:
    """A quoting bug silently loses these; -z carries them through intact."""
    init_repo(tmp_path)
    (tmp_path / "seed.txt").write_text("seed\n")
    commit_all(tmp_path)

    weird = "src/café ütfÿ.py"
    (tmp_path / "src").mkdir()
    (tmp_path / weird).write_text("π = 3.14\n")
    spaced = "a file with spaces.txt"
    (tmp_path / spaced).write_text("hi\n")

    cs = ChangeSet.detect(tmp_path)
    assert weird in cs.paths()
    assert spaced in cs.paths()
    assert next(f for f in cs if f.path == weird).added_line_numbers() == (1,)


def test_ignored_paths_are_excluded(tmp_path: Path) -> None:
    """A change to an ignored path can't be delivered, so it isn't in scope."""
    init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("secret.env\n")
    commit_all(tmp_path)

    (tmp_path / "secret.env").write_text("TOKEN=abc\n")
    (tmp_path / "real.py").write_text("ok = True\n")
    assert ChangeSet.detect(tmp_path).paths() == ("real.py",)


def _write_n_changed_files(repo: Path, n: int) -> None:
    for i in range(n):
        (repo / f"f{i}.py").write_text(f"value_{i} = {i}\nother_{i} = {i * 2}\n")


def test_subprocess_count_is_flat_across_change_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1, 10 and 25 changed files must cost the same number of git spawns.

    This is the whole point of computing the change once: local-ai measured 3
    spawns against 51 for a 25-file change before the diff was shared.
    """
    real_run = subprocess.run

    counts: list[int] = []

    def counting_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
            counting_run.n += 1  # type: ignore[attr-defined]
        return real_run(cmd, *args, **kwargs)

    for n in (1, 10, 25):
        repo = tmp_path / f"repo_{n}"
        init_repo(repo)
        (repo / "seed.txt").write_text("seed\n")
        commit_all(repo)
        _write_n_changed_files(repo, n)

        counting_run.n = 0  # type: ignore[attr-defined]
        monkeypatch.setattr("mcgyvr.gate.changeset.subprocess.run", counting_run)
        cs = ChangeSet.detect(repo)
        monkeypatch.undo()

        assert len([f for f in cs if f.path.startswith("f")]) == n
        counts.append(counting_run.n)  # type: ignore[attr-defined]

    assert counts[0] == counts[1] == counts[2], (
        f"subprocess count grew with change size: {counts}"
    )


def _reference_added_lines(base: str, new: str) -> set[int]:
    """A deliberately independent attribution, for the gate to be checked against.

    Longest-common-subsequence over lines: a new-file line is *added* unless it
    is part of the LCS with the base. On the unambiguous edits these tests use,
    this agrees with git line-for-line, which is what the acceptance criterion
    asks us to demonstrate.
    """
    a = base.split("\n")
    b = new.split("\n")
    la, lb = len(a), len(b)
    lcs = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la - 1, -1, -1):
        for j in range(lb - 1, -1, -1):
            lcs[i][j] = (
                lcs[i + 1][j + 1] + 1
                if a[i] == b[j]
                else max(lcs[i + 1][j], lcs[i][j + 1])
            )
    added: set[int] = set()
    i = j = 0
    while j < lb:
        if i < la and a[i] == b[j]:
            i += 1
            j += 1
        elif i < la and lcs[i + 1][j] >= lcs[i][j + 1]:
            i += 1
        else:
            added.add(j + 1)  # 1-based new-file line number
            j += 1
    # The trailing empty element from a final newline is not a real line.
    added.discard(lb)
    return added


@pytest.mark.parametrize(
    "base,new",
    [
        ("a\nb\nc\n", "a\nb\nc\nd\ne\n"),  # append
        ("a\nb\nc\n", "a\nX\nc\n"),  # replace middle
        ("a\nb\nc\nd\n", "a\nc\nd\n"),  # delete a line
        ("a\nb\nc\n", "Z\na\nY\nb\nc\nW\n"),  # scattered inserts
        ("one\n", "one\ntwo\nthree\nfour\n"),  # grow a lot
    ],
)
def test_attribution_matches_reference_case_for_case(
    tmp_path: Path, base: str, new: str
) -> None:
    init_repo(tmp_path)
    (tmp_path / "f.py").write_text(base)
    commit_all(tmp_path)
    (tmp_path / "f.py").write_text(new)

    change = change_for(tmp_path, "f.py")
    assert change.added_lines == _reference_added_lines(base, new)


def test_read_added_text_returns_only_worker_lines(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "m.py").write_text("keep1\nkeep2\n")
    commit_all(tmp_path)
    (tmp_path / "m.py").write_text("keep1\nNEW_A\nkeep2\nNEW_B\n")

    change = change_for(tmp_path, "m.py")
    text = read_added_text(change, tmp_path)
    assert set(text.values()) == {"NEW_A", "NEW_B"}
    assert 1 not in text  # keep1 was pre-existing


def test_explicit_base_is_respected(tmp_path: Path) -> None:
    """Diffing against an older commit attributes everything since as added."""
    init_repo(tmp_path)
    (tmp_path / "f.py").write_text("v1\n")
    commit_all(tmp_path, "c1")
    first = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()

    (tmp_path / "f.py").write_text("v1\nv2\n")
    commit_all(tmp_path, "c2")
    (tmp_path / "f.py").write_text("v1\nv2\nv3\n")  # uncommitted worker edit

    against_first = ChangeSet.detect(tmp_path, base=first)
    change = next(f for f in against_first if f.path == "f.py")
    assert change.added_line_numbers() == (2, 3)
