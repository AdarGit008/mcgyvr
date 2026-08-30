"""The mission runner reads a delivered file back the way the tree wrote it.

``tools/missions/run.py`` records what was delivered by reading it off the
worktree rather than carrying it from the reply — that is pattern B, and it is
right. The read itself was ``read_text(encoding="utf-8")``, which is strict, and
strict is the one thing this project's byte convention says a reader may not be:
:func:`mcgyvr.deliver.deliver` writes through ``surrogateescape``
(``deliver._encoded``) and refuses *only* a lone surrogate, so a target holding a
byte that is not valid UTF-8 is committed successfully and then cannot be read
back by the line that follows the commit.

What that costs is not a mangled record. ``UnicodeDecodeError`` is not
``DeliveryError``, so it is caught by nothing: it leaves ``run_task`` after the
commit and before ``_write_record``, which is exactly the outcome the
``DeliveryError`` handler twelve lines above exists to prevent — *"ends the
mission with earlier contracts already committed and no record written"*. The
contract is in the repository's history and the run that put it there left no
trace of itself.

The fix is the spelling every other reader in this repository already uses —
``read_bytes().decode("utf-8", "surrogateescape")``, as in
:meth:`mcgyvr.deliver.Accepted.read`, :func:`mcgyvr.pending.resume`,
``gate.changeset``, ``orchestrator.index`` — and not, say, ``errors="replace"``
or a ``try``/``except`` that records a placeholder. Both of those would let the
run finish; both would also make the record's copy of the delivered file a
different sequence of bytes from the one in the commit beside it, which is the
substitution this whole pattern was written to close.

So the assertion here is on the **bytes**, not on the absence of an exception. A
test that only asked "did ``run_task`` return?" would pass against
``errors="replace"``, which is the wrong fix; it would also pass against a bare
``except UnicodeDecodeError: continue``, which is worse than the defect. What is
asserted is that the file in the commit and the string in
``MissionResult.files`` encode to the same bytes.

The control is the same run with ordinary ASCII content. It says the harness
below actually reaches the read-back — five stand-ins stand between a test and
that line, and a scaffolding mistake in any of them would produce a green test
that never executed the code under test.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import Family
from mcgyvr.config import parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deliver import Accepted, digest_of
from mcgyvr.escalate import Assurance, Delivered, Judgement
from mcgyvr.route import Verdict

KEYLESS = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

TARGET = "src/pkg/fixture.txt"

CONTRACT = f"""
id: fixture-bytes
task_type: function_implementation
task: Rewrite the fixture the way the corpus holds it.
target: {TARGET}
stop_conditions:
  - The fixture's encoding is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**"]
"""

#: A byte that is not valid UTF-8, as it exists in a string once the project's
#: convention has decoded it: ``surrogateescape`` parks 0xE9 at U+DCE9. Written
#: as an escape rather than as the character, because the character is not one.
LATIN1_E_ACUTE = "caf\udce9 fixture\n"
LATIN1_E_ACUTE_BYTES = b"caf\xe9 fixture\n"

ASCII = "plain fixture\n"
ASCII_BYTES = b"plain fixture\n"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising with stderr on failure."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def make_repo(where: Path, files: dict[str, str]) -> Path:
    """A real git repository holding ``files``, committed once."""
    for name, body in files.items():
        path = where / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git(where.parent, "init", "-q", str(where))
    git(where, "config", "user.email", "readback@example.invalid")
    git(where, "config", "user.name", "readback")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


@pytest.fixture
def missions_run() -> Any:
    """``tools/missions/run.py``, loaded by path — it is a script, not a module."""
    path = Path(__file__).resolve().parent.parent / "tools" / "missions" / "run.py"
    spec = importlib.util.spec_from_file_location("missions_run_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module uses `from __future__ import
    # annotations`, so `@dataclass` resolves its string annotations through
    # `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _attempt_module() -> types.SimpleNamespace:
    """The sibling ``run_task`` asks for, reduced to what this path touches.

    ``acceptance_files_from`` and ``acceptance_for`` are called through
    ``_construct``, which reads their signatures, so they are written as real
    functions with the keyword names the runner offers rather than as
    ``**kwargs`` catch-alls that would accept a runner passing the wrong thing.
    """

    def acceptance_files_from(
        *, repo_root: Path, sha: str, test_paths: tuple[str, ...]
    ) -> dict[str, str]:
        return {}

    def acceptance_for(
        *, target: str, base: Path, test_paths: tuple[str, ...]
    ) -> tuple[str, ...]:
        return ("true",)

    class AttemptError(Exception):
        pass

    return types.SimpleNamespace(
        acceptance_files_from=acceptance_files_from,
        acceptance_for=acceptance_for,
        MissionSandbox=lambda worktree: worktree,
        AttemptError=AttemptError,
    )


def _delivered(accepted: Accepted) -> Delivered:
    """A climb that passed, carrying the binding item 3 minted off the tree."""
    family = Family(name="local", rank=0, doc="the cheap rung")
    return Delivered(
        family=family,
        rung="local_qwen-7b",
        assurance=Assurance.UNVERIFIED,
        judgement=Judgement(verdict=Verdict.PASSED, accepted=accepted),
        entered=(family,),
        history=(),
        attempts_spent=1,
        escalations=0,
    )


def _run(
    missions_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
) -> tuple[Any, Path, list[Path]]:
    """Drive ``run_task`` as far as the read-back, and no further.

    Everything before the delivery loop is a stand-in — the plan, the climb, the
    sibling modules, the whole-tree test run and the record writer — because
    each of them wants a live pool, a live worker or a live ruff, and none of
    them is what this file is about. What is *not* stood in for is the pair
    under test: :func:`mcgyvr.deliver.deliver` really writes and really commits
    into a real git repository, and the runner really reads the file back.

    Returns the :class:`MissionResult`, the worktree, and the list the record
    writer appended to — empty when the run never reached it.
    """
    repo = make_repo(tmp_path / "repo", {TARGET: "fixture\n"})
    contract: Contract = load_contract(CONTRACT)
    task = types.SimpleNamespace(
        sha="0" * 40, repo_root=repo, test_paths=("tests/test_fixture.py",)
    )
    plan = types.SimpleNamespace(
        task=task,
        worktree=repo,
        index=None,
        pool=object(),
        proposer=object(),
        proposer_binding=("role orchestrator", "qwen2.5-coder:7b", None),
        decomposition=types.SimpleNamespace(contracts=(contract,)),
        declared_refusals=(),
    )
    accepted = Accepted(content=content, accepted=True, digest=digest_of(content))

    written: list[Path] = []

    def write_record(*args: Any, **kwargs: Any) -> Path:
        where = tmp_path / "records" / "written"
        written.append(where)
        return where

    monkeypatch.setattr(missions_run, "_sibling", lambda name: _attempt_module())
    monkeypatch.setattr(missions_run, "plan_task", lambda *a, **k: plan)
    monkeypatch.setattr(missions_run, "escalate", lambda *a, **k: _delivered(accepted))
    monkeypatch.setattr(missions_run, "_run_test", lambda *a, **k: None)
    monkeypatch.setattr(missions_run, "_write_record", write_record)

    result = missions_run.run_task(
        task,
        parse(KEYLESS),
        db_path=tmp_path / "corpus.sqlite3",
        into=tmp_path / "into",
        attempt_for=lambda contract: lambda this: None,
        records_root=tmp_path / "records",
    )
    return result, repo, written


def test_a_delivered_byte_that_is_not_utf8_reaches_the_record(
    missions_run: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The commit happens either way; what is at stake is the record beside it.

    Asserted on bytes rather than on the run completing, because a run that
    completes is what ``errors="replace"`` also buys — and it buys it by putting
    a different file in the record from the one in the commit, which is the
    substitution :class:`mcgyvr.deliver.Accepted` exists to make impossible.
    """
    result, repo, written = _run(missions_run, monkeypatch, tmp_path, LATIN1_E_ACUTE)

    assert (repo / TARGET).read_bytes() == LATIN1_E_ACUTE_BYTES, (
        "delivery did not write the bytes it was handed, so nothing about the "
        "read-back is being tested"
    )
    assert written, (
        "no record was written: the run ended between the commit and "
        "`_write_record`, which is the failure the `DeliveryError` handler "
        "above the read-back exists to prevent"
    )
    assert result.files[TARGET].encode("utf-8", "surrogateescape") == (
        LATIN1_E_ACUTE_BYTES
    ), (
        "the record's copy of the delivered file is not the bytes in the "
        "commit; the read-back substituted them rather than carrying them"
    )
    assert result.commits and result.commits[0][0] == "fixture-bytes"


def test_an_ordinary_delivery_still_reaches_the_record(
    missions_run: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control: ASCII goes all the way through, before and after the fix.

    Without it, a harness that never reached the read-back at all would make the
    test above look like a statement about decoding when it was a statement
    about five stand-ins.
    """
    result, repo, written = _run(missions_run, monkeypatch, tmp_path, ASCII)

    assert (repo / TARGET).read_bytes() == ASCII_BYTES
    assert written, "the control never reached `_write_record`"
    assert result.files[TARGET].encode("utf-8", "surrogateescape") == ASCII_BYTES
