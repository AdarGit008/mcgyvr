"""An `agent` worker is given its contract's `sources`, numbered, with their content.

E2e run 2, R11: the prompt asked the model to cite `[n]` sources it was never
given — `sources` never reached the worker — so both rungs answered that no
sources were provided. Owner decision: the sources are rendered into the agent
worker prompt, numbered, with their content, read under the rules every other
read of the tree for a worker follows:

- from the run's sandbox workspace, the tree the run started from — HEAD's
  tracked files for a git repository — as the target's own content is;
- through :func:`mcgyvr.scope.inside`, so an absolute path, ``..``, a symlink or
  ``.git`` is refused rather than followed;
- never a file the sandbox's non-git copy leaves behind for holding a secret
  (``.env``, keys, credential folders), nor a binary or oversized file;
- whole, and bounded by the contract's `context.max_input_tokens` through the
  prompt's existing fit check — never silently truncated.

A source that cannot be read refuses the attempt before anything is sent.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.contract import ContractSchemaError, loads
from mcgyvr.worker.prompt import build_prompt, render_user_message

AGENT = """\
id: brief
task_type: agent
task: Explain how the store saves a record.
sources: ["src/app/store.py", "tests/test_store.py"]
"""

STORE = 'def save(record):\n    """Write 1.5 records."""\n    json.dump(record, f)\n'
TESTS = "def test_save():\n    assert save({}) is None\n"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "app" / "store.py").write_text(STORE, encoding="utf-8")
    (root / "tests" / "test_store.py").write_text(TESTS, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


# --- the prompt --------------------------------------------------------------


def test_each_source_is_numbered_from_one_with_its_content_fenced() -> None:
    contract = replace(loads(AGENT), source_content=(STORE, TESTS))

    user = build_prompt(contract).user

    assert "SOURCES" in user, user
    first = user.index("[1] src/app/store.py\n```\n" + STORE + "```")
    second = user.index("[2] tests/test_store.py\n```\n" + TESTS + "```")
    assert first < second
    # Before the output instruction: the material, then what to do with it.
    assert second < user.index("OUTPUT:")


def test_the_agent_bundle_points_at_the_numbered_sources() -> None:
    system = build_prompt(replace(loads(AGENT), source_content=(STORE, TESTS))).system
    assert "SOURCES" in system, system
    assert "[n]" in system, system


def test_a_fence_inside_a_source_does_not_close_its_block() -> None:
    fenced = "Example:\n```python\nx = 1\n```\n"
    contract = replace(loads(AGENT), sources=("docs/a.md",), source_content=(fenced,))
    user = render_user_message(contract.worker_view())
    assert "[1] docs/a.md\n````\n" + fenced + "````" in user, user


def test_the_worker_view_names_the_sources_before_they_are_read() -> None:
    """`mcgyvr contract --worker-view` shows the paths; content is read at dispatch."""
    view = loads(AGENT).worker_view()
    assert view["sources"] == [
        {"path": "src/app/store.py", "content": None},
        {"path": "tests/test_store.py", "content": None},
    ]
    user = render_user_message(view)
    assert "[1] src/app/store.py" in user, user
    assert "[2] tests/test_store.py" in user, user


def test_a_contract_without_sources_has_no_sources_section() -> None:
    chat = loads("id: sky\ntask_type: chat\ntask: Why is the sky blue?\n")
    assert "SOURCES" not in build_prompt(chat).user


def test_sources_count_against_the_prompt_ceiling_and_are_never_cut() -> None:
    big = "word " * 4000
    contract = replace(loads(AGENT), source_content=(big, TESTS))
    prompt = build_prompt(contract)
    assert not prompt.fits
    assert big in prompt.user


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        ("/etc/passwd", "absolute"),
        ("../outside.txt", ".."),
        ("src/**/*.py", "pattern"),
        (".git/config", ".git"),
        ("", "empty"),
    ],
)
def test_a_source_that_names_no_file_in_the_tree_is_refused_at_load(
    entry: str, said: str
) -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(AGENT.replace('"tests/test_store.py"', f'"{entry}"'))
    message = str(exc.value)
    assert message.startswith("sources.1:"), message
    assert said in message, message


def test_a_source_named_twice_is_refused_at_load() -> None:
    with pytest.raises(ContractSchemaError, match=r"sources\.1:.*twice"):
        loads(AGENT.replace("tests/test_store.py", "src/app/store.py"))


# --- the read, in the attempt ------------------------------------------------


def _attempt(repo: Path, document: str, monkeypatch: pytest.MonkeyPatch, *replies: str):  # type: ignore[no-untyped-def]
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.local_pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from tests.drives import LADDER, _driven

    config = parse_config(LADDER)
    sent = _driven(monkeypatch, *replies)
    with TempDirSandbox(repo) as sandbox:
        judgement = worker_attempt(
            config, source_map(config), loads(document), sandbox
        )(Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1))
    return judgement, sent


def test_the_attempt_reads_each_source_from_the_tree_the_run_started_from(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Uncommitted: the sandbox holds HEAD's tracked files, as for the target.
    (repo / "src" / "app" / "store.py").write_text("edited\n", encoding="utf-8")

    judgement, sent = _attempt(repo, AGENT, monkeypatch, "It writes JSON [1].")

    assert judgement.accepted is not None
    assert len(sent) == 1
    assert "[1] src/app/store.py\n```\n" + STORE + "```" in sent[0], sent[0]
    assert "[2] tests/test_store.py\n```\n" + TESTS + "```" in sent[0], sent[0]
    assert "edited" not in sent[0]


@pytest.mark.parametrize(
    ("name", "make", "said"),
    [
        ("src/app/missing.py", None, "not a file in the tree"),
        (".env", lambda p: p.write_text("TOKEN=x\n", encoding="utf-8"), "secret"),
        (
            "src/app/blob.bin",
            lambda p: p.write_bytes(b"\x00\x01\x02"),
            "binary",
        ),
        (
            "src/app/link.py",
            lambda p: p.symlink_to(p.parent / "store.py"),
            "symlink",
        ),
    ],
)
def test_a_source_that_cannot_be_read_refuses_the_attempt_before_anything_is_sent(
    name: str,
    make: object,
    said: str,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.escalate import DispatchRaisedError

    if callable(make):
        make(repo / name)
        _git(repo, "add", "-A", "-f")
        _git(repo, "commit", "-q", "-m", "more")
    document = AGENT.replace("tests/test_store.py", name)

    with pytest.raises(DispatchRaisedError) as exc:
        _attempt(repo, document, monkeypatch)

    assert exc.value.rows == 0
    message = str(exc.value.__cause__ or exc.value)
    assert f"sources.1: {name!r}" in message, message
    assert said in message, message
    assert "nothing was sent" in message, message
