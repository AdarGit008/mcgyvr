"""The decomposer takes located checkers from a caller instead of reading the disk.

`type_annotation` needs the checker the repository declared, and
:func:`~mcgyvr.orchestrator.decompose._acceptance_for` finds it by asking the
owning adapter to read the repository's configuration. A server that holds an
index assembled from a document (mcorch) has no repository under
``index.root`` — the root is a label there — so ``decompose`` takes the
located commands as an argument, adapter name → argv, and when given uses
them in place of any read of the disk: a located command becomes the
acceptance exactly as given, a missing one is the same refusal the disk gives
("declares no type checker"), and nothing is ever guessed. Without the
argument nothing changes: `mcgyvr delegate` keeps reading the repository.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.orchestrator.decompose import RecordedProposer, decompose
from mcgyvr.orchestrator.index import Index, build_index
from tests.livejournal import git
from tests.test_orchestrator_decompose import an_annotation, declaring_mypy


def _repo(tmp_path: Path) -> Index:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text(
        "def listing(items):\n    return list(items)\n", encoding="utf-8"
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def test_a_located_command_is_the_acceptance_without_a_read_of_the_disk(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)  # declares no checker on disk
    (built,) = decompose(
        repo,
        "annotate",
        propose=RecordedProposer((an_annotation(),)),
        located={"python": ["mypy", "--strict"]},
    ).contracts
    assert built.acceptance == ("mypy --strict",)


def test_an_empty_located_map_refuses_even_where_the_disk_declares_a_checker(
    tmp_path: Path,
) -> None:
    repo = declaring_mypy(_repo(tmp_path))
    result = decompose(
        repo, "annotate", propose=RecordedProposer((an_annotation(),)), located={}
    )
    assert result.contracts == ()
    (refusal,) = result.refusals
    assert refusal.subject == "listing.py"
    assert "declares no type checker" in refusal.reason
    assert "type_annotation" in refusal.reason


def test_without_the_argument_the_disk_is_read_as_before(tmp_path: Path) -> None:
    repo = declaring_mypy(_repo(tmp_path))
    (built,) = decompose(
        repo, "annotate", propose=RecordedProposer((an_annotation(),))
    ).contracts
    assert built.acceptance == ("mypy",)


def test_a_proposals_own_acceptance_still_wins_over_a_located_command(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (built,) = decompose(
        repo,
        "annotate",
        propose=RecordedProposer((an_annotation(acceptance=("make typecheck",)),)),
        located={"python": ["mypy"]},
    ).contracts
    assert built.acceptance == ("make typecheck",)
