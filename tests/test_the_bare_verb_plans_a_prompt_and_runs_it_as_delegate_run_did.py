"""`mcgyvr PROMPT` is what `mcgyvr delegate PROMPT --run` was, and nothing else.

The bare verb takes a prompt as its first word, has the proposer bound in the
config plan it, and runs what comes back. It is no new machinery: it parses to
the namespace `delegate --run` parsed to, and is handed to the same handler,
so the journal's results, the tree and the `--log` record it writes are the
ones that handler writes when called with `delegate --run`'s arguments —
checked here byte for byte, on two copies of one repository, with the
proposer's reply and each contract's run stood in for. The old command's
code is gone, so its parity is pinned where it can be: its namespace, and the
handler both are given. `--output DIR` stops once the contracts are planned:
they are written and none runs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.delegate as delegate
from mcgyvr.cli.commands import delegate as command
from mcgyvr.cli.dispatcher import _build
from mcgyvr.delegate_log import DelegateKind, read
from mcgyvr.local_pool import Protocol
from mcgyvr.result import RunResult, result_path, run_stamp, write
from mcgyvr.runner import Completion, StopReason
from mcgyvr.session import Session
from tests import livejournal as lj

CONFIG = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
ladder:
- planner
orchestrator:
  unit: planner
  model: planner-model
journal:
  dir: {journal}
"""

PROMPT = "Fix listing to return the items sorted."
PROPOSAL = {
    "task_type": "code",
    "task": "Fix listing to return the items sorted.",
    "target": "listing.py",
    "stop_conditions": ["the documented behaviour is ambiguous"],
}
#: What differs between two runs of one batch on two copies of a repository:
#: when it ran, where it journaled, and the commit's hash.
VARIES = frozenset({"run", "started", "finished", "journal", "commit"})


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture(autouse=True)
def no_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A HOME of the test's own, no session in it and no setup discovered."""
    (tmp_path / "home").mkdir()
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))


def repository(where: Path) -> Path:
    where.mkdir(parents=True)
    git(where, "init", "-q", "-b", "main")
    (where / "listing.py").write_text("def listing(items):\n    return items\n")
    git(where, "add", "-A")
    git(where, "commit", "-q", "-m", "seed")
    return where


def setup(where: Path) -> tuple[Path, Path]:
    """A config binding a proposer, journaling under `where`; and the journal."""
    journal = where / "journal"
    path = where / "mcgyvr.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG.format(journal=journal), encoding="utf-8")
    return path, journal


def proposes(monkeypatch: pytest.MonkeyPatch, reply: str) -> list[str]:
    """The proposer answers `reply` to every request; the requests are kept."""
    asked: list[str] = []

    def answer(source_map: Any, role: Any, request: Any, *, capacity: Any = None):  # type: ignore[no-untyped-def]
        asked.append(request.prompt)
        return Completion(
            text=reply,
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="planner-model",
            source="planner",
            protocol=Protocol.OPENAI,
            max_output_tokens=2000,
            latency_s=0.0,
            output_tokens=120,
        )

    monkeypatch.setattr(delegate, "dispatch_role", answer)
    return asked


def runs_land(monkeypatch: pytest.MonkeyPatch, ran: list[str]) -> None:
    """Each contract's run is stood in for: it commits a change and says so."""

    def run(args: argparse.Namespace) -> int:
        from mcgyvr.config import load

        contract = json.loads(Path(args.contract).read_text())
        repo = Path(args.repo)
        ran.append(contract["id"])
        # A prompt's runs are handed no result path and no seed.
        assert (args.result, args.notes_from) == (None, None)
        (repo / contract["target"]).write_text(
            "def listing(items):\n    return sorted(items)\n"
        )
        git(repo, "commit", "-q", "-am", contract["id"])
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        journal = Path(load(Path(args.config)).get("journal.dir"))
        report = RunResult(
            contract=contract["id"],
            task_type=contract["task_type"],
            target=contract["target"],
            session=args.session.name,
            outcome="accepted",
        )
        report.committed, report.commit = True, head
        write(result_path(journal, contract["id"], run_stamp()), report)
        return 0

    monkeypatch.setattr(command, "_run", run)


def old_delegate_run(
    repo: Path, config: Path, log: Path, session: str
) -> argparse.Namespace:
    """The namespace `mcgyvr delegate PROMPT --run` parsed to, before it went."""
    return argparse.Namespace(
        prompt=PROMPT,
        repo=str(repo),
        config=str(config),
        into=None,
        budget=None,
        output=None,
        run=True,
        jobs=1,
        sandbox=None,
        commit=None,
        branch=None,
        record=None,
        log=str(log),
        session_id=session,
        func=command._delegate,
    )


def written(journal: Path) -> dict[str, Any]:
    """What a batch left in its journal, less what differs from run to run."""
    found: dict[str, Any] = {}
    for path in sorted((journal / "results").glob("*.json")):
        doc = json.loads(path.read_text())
        found[doc["contract"]] = {k: v for k, v in doc.items() if k not in VARIES}
    for path in sorted((journal / "trees").glob("*.json")):
        tree = json.loads(path.read_text())
        found["tree"] = [
            {
                # The contract each row runs from is compared as text: its
                # path is under each journal.
                k: Path(v).read_text() if k == "document" else v
                for k, v in row.items()
                if k not in VARIES | {"result", "batch"}
            }
            for row in tree["contracts"]
        ]
    return found


def test_the_bare_verb_parses_to_what_delegate_run_parsed_to(tmp_path: Path) -> None:
    _, prompt, _ = _build()
    repo, config, log = tmp_path / "r", tmp_path / "c.yaml", tmp_path / "log.json"
    argv = [PROMPT, "--repo", str(repo), "--config", str(config)]
    args = prompt.parse_args([*argv, "--log", str(log), "--session", "s1"])
    args.run = args.output is None

    old = vars(old_delegate_run(repo, config, log, "s1"))
    new = vars(args)
    assert {k: new[k] for k in old} == old
    # The two flags `direct` gave the set are the only ones it adds, both unset.
    assert {k: v for k, v in new.items() if k not in old} == {
        "result": None,
        "notes_from": None,
    }


def test_the_bare_verb_writes_the_journal_and_log_delegate_run_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposes(monkeypatch, json.dumps([PROPOSAL]))
    ran: list[str] = []
    runs_land(monkeypatch, ran)

    then, now = tmp_path / "then", tmp_path / "now"
    repo = repository(then / "repo")
    repository(now / "repo")

    # The old way: the handler, with `delegate PROMPT --run`'s arguments.
    config, journal = setup(then)
    log = then / "log.json"
    args = old_delegate_run(repo, config, log, "s1")
    args.session = Session("s1")
    old_code = command._delegate(args)

    # The bare verb, on the other copy.
    new_config, new_journal = setup(now)
    new_log = now / "log.json"
    new_code = lj.main(
        [
            PROMPT,
            "--repo",
            str(now / "repo"),
            "--config",
            str(new_config),
            "--log",
            str(new_log),
            "--session",
            "s1",
        ]
    )

    assert new_code == old_code == 0
    assert len(ran) == 2 and ran[0] == ran[1]
    assert written(new_journal) == written(journal)
    assert written(journal)[ran[0]]["outcome"] == "accepted"
    before, after = read(log), read(new_log)
    assert after.kind is before.kind is DelegateKind.EMITTED
    # The whole record is the same, less nothing: printed contracts have no
    # path, and every other field is the handler's own.
    assert after == before


def test_output_writes_the_contracts_and_runs_none_with_no_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposes(monkeypatch, json.dumps([PROPOSAL]))
    ran: list[str] = []
    runs_land(monkeypatch, ran)
    repo = repository(tmp_path / "repo")
    config, journal = setup(tmp_path)
    out = tmp_path / "contracts"

    code = lj.main(
        [PROMPT, "--repo", str(repo), "--config", str(config), "--output", str(out)]
    )

    assert code == 0
    assert ran == []
    (contract,) = out.glob("*.json")
    assert json.loads(contract.read_text())["target"] == "listing.py"
    assert not (journal / "results").exists()


def test_running_a_prompt_with_no_session_asks_no_proposer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = proposes(monkeypatch, json.dumps([PROPOSAL]))
    repo = repository(tmp_path / "repo")
    config, _ = setup(tmp_path)

    code = lj.main([PROMPT, "--repo", str(repo), "--config", str(config)])

    assert code == 2
    assert asked == []
