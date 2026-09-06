"""A config that ran has an identity, and every result names it.

Owner's ruling R2 (2026-09-06): every result must be traceable to the exact
config that produced it, and a known-good setup must be re-selectable by that
identity in one command. Today a journal row names the round, the product
digest, the prompt and the reply — and not the config: two runs made under two
ladders on one day read the same, and the config that produced a result may
have been edited since.

The identity is a digest of the config *as loaded and validated*, never of the
file's bytes: a comment, a blank line, a reordered key or a defaulted key spelled
out must not change it, because none of them changes what ran; a changed value
must. It is prefixed ``cfg-`` so it can never be mistaken for a product digest.

What must be observably true:

* ``Config.digest()`` is the same for two files that load to the same config
  and differs for two that do not, and does not depend on where the file is;
* every journal row names the digest of the config that produced it, and a
  floor run made with no config carries no digest rather than a null one;
* the result file names it too;
* the config that ran is kept under the journal by its digest, so the setup
  a result names is re-selectable in one command
  (``MCGYVR_CONFIG=<journal>/configs/<digest>.yaml``);
* ``mcgyvr --version`` prints the digest beside the product version;
* the door files the digest in the run's envelope header, written by gate 5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj
from tests import onedoor
from tests.red_port.conftest import required

PREFIX = "cfg-"

BASE = """\
version: 1
sources:
  local:
    base_url: "http://localhost:8080"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: only
      source: local
      model: "a-model"
sandbox:
  mode: tempdir
budgets:
  task_timeout_s: 7
"""

#: The same config: comments, blank lines, key order and a default spelled out.
SAME = """\
# a comment nobody ran
budgets:
  task_timeout_s: 7

sandbox:
  mode: tempdir   # the default sandbox

ladder:
  tiers:
    - model: "a-model"
      source: local
      name: only
profile: live
sources:
  local:
    max_parallel: 1
    api: openai
    base_url: "http://localhost:8080"
version: 1
"""

#: One value moved.
OTHER = BASE.replace("task_timeout_s: 7", "task_timeout_s: 8")

#: A contract the deterministic floor finishes without a config.
FORMAT = """\
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


def _identity(config: Any) -> str:
    """``config.digest()`` — the seam a RED run names rather than errors on."""
    return str(
        required(
            "name a loaded config by a digest of what it loads to",
            lambda: config.digest(),
        )
    )


def _digest(text: str) -> str:
    from mcgyvr.config import parse

    return _identity(parse(text))


# --- the identity ----------------------------------------------------------------


def test_the_same_config_spelled_differently_has_one_digest() -> None:
    assert _digest(BASE) == _digest(SAME)
    assert _digest(BASE).startswith(PREFIX), _digest(BASE)


def test_a_changed_value_changes_it() -> None:
    assert _digest(BASE) != _digest(OTHER)


def test_where_the_file_is_does_not_change_it(tmp_path: Path) -> None:
    from mcgyvr.config import load

    a = tmp_path / "a" / "mcgyvr.yaml"
    b = tmp_path / "b" / "copy.yaml"
    for path in (a, b):
        path.parent.mkdir()
        path.write_text(BASE, encoding="utf-8")
    assert _identity(load(a)) == _identity(load(b)) == _digest(BASE)


# --- the journal -----------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(home, "s1")
    return home


def _one_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """One recorded run under a config; the journal dir and the config's digest."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "state" / "journal"
    text = lj.LADDER + f"journal:\n  dir: {journal}\n"
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(text, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    code = lj.main(lj.run_args(contract, repo, config))
    assert code == 0
    return journal, _digest(text)


def _rows(journal: Path) -> list[dict[str, Any]]:
    from mcgyvr.telemetry import fold

    return list(fold(path=journal / "claude-s1.jsonl"))


def test_a_journal_row_names_the_config_that_produced_it(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal, digest = _one_run(tmp_path, monkeypatch)
    (row,) = _rows(journal)
    assert row.get("config_digest") == digest, row


def test_the_result_file_names_it_too(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal, digest = _one_run(tmp_path, monkeypatch)
    (result,) = sorted((journal / "results").glob("*.json"))
    doc = json.loads(result.read_text(encoding="utf-8"))
    assert doc.get("config_digest") == digest, doc


def test_the_config_that_ran_is_kept_by_its_digest_and_reselects_the_same_setup(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2's second half: the identity a result names is one command away.

    The copy is content-addressed, so a second run under the same setup writes
    nothing new, and loading the copy yields the digest it is filed under."""
    from mcgyvr.config import load

    journal, digest = _one_run(tmp_path, monkeypatch)
    kept = journal / "configs" / f"{digest}.yaml"
    assert kept.is_file(), sorted(str(p) for p in journal.rglob("*"))
    assert _identity(load(kept)) == digest


def test_a_floor_run_with_no_config_carries_no_digest(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent, not null: a key present on some rows and null on others invites
    a reader to coerce it, and a coerced absence reads as an identity."""
    from mcgyvr.telemetry import fold

    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    code = lj.main(["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"])
    assert code == 0
    sink = home / ".local" / "state" / "mcgyvr" / "journal" / "claude-s1.jsonl"
    rows = list(fold(path=sink))
    assert rows, "the floor run journaled nothing"
    for row in rows:
        assert "config_digest" not in row, row


# --- the version line ------------------------------------------------------------


def test_version_prints_the_product_and_the_config_it_would_run(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import mcgyvr
    from mcgyvr.cli import main

    config = tmp_path / "dev.yaml"
    config.write_text(BASE, encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(config))
    with pytest.raises(SystemExit) as left:
        main(["--version"])
    assert left.value.code == 0
    out = capsys.readouterr().out
    assert f"mcgyvr {mcgyvr.__version__}" in out, out
    assert _digest(BASE) in out, out
    assert str(config) in out, out


def test_version_with_no_config_says_so(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import mcgyvr
    from mcgyvr.cli import main

    with pytest.raises(SystemExit) as left:
        main(["--version"])
    assert left.value.code == 0
    out = capsys.readouterr().out
    assert f"mcgyvr {mcgyvr.__version__}" in out, out
    assert PREFIX not in out and "none" in out, out


# --- the envelope ----------------------------------------------------------------

CAMPAIGN = "digest-probe"


def test_the_envelope_header_names_the_config_digest(tmp_path: Path) -> None:
    """Gate 5 files a header for the run beside the step's artifacts: the run
    id, the round, the profile and the config's digest, before the step runs.
    An artifact says what it measured; the header says what measured it."""
    root = onedoor.fixture_repo(tmp_path)
    config = tmp_path / "dev.yaml"
    config.write_text("profile: dev\n" + BASE, encoding="utf-8")
    step = onedoor.add_step(
        root, CAMPAIGN, "1-probe.sh", onedoor.probe_step(tmp_path / "env.txt")
    )
    done = onedoor.door(
        root,
        onedoor.Scenario(campaign=CAMPAIGN, step=str(step)),
        env_extra={"MCGYVR_CONFIG": str(config)},
    )
    assert done.returncode == 0, done.stderr[-1500:]
    run_id = f"{onedoor.RUN_DATE}-{CAMPAIGN}-probe"
    header = onedoor.envelope(root, CAMPAIGN) / f"{run_id}.run.json"
    assert header.is_file(), onedoor.written_under_records(root)
    doc = json.loads(header.read_text(encoding="utf-8"))
    assert doc.get("run_id") == run_id, doc
    assert doc.get("config_digest") == _digest("profile: dev\n" + BASE), doc
    assert doc.get("profile") == "dev", doc
    assert doc.get("round") == onedoor.pinned(root)[0], doc


# --- what an adversarial pass found -----------------------------------------------


def test_a_kept_copy_a_crash_left_short_is_replaced_not_trusted(
    tmp_path: Path,
) -> None:
    """Content-addressed means the bytes hash to the name; a file under the
    right name with the wrong bytes is a copy that will never load, and
    ``exists()`` alone would keep it forever."""
    from mcgyvr.config import CONFIGS_DIR, keep, load, parse

    config = parse(BASE)
    journal = tmp_path / "journal"
    short = journal / CONFIGS_DIR / f"{_identity(config)}.yaml"
    short.parent.mkdir(parents=True)
    short.write_text(config.canonical()[:40], encoding="utf-8")
    kept = keep(config, journal)
    assert kept == short
    assert _identity(load(kept)) == _identity(config)


def test_a_relative_geometry_file_is_part_of_the_identity(tmp_path: Path) -> None:
    """A relative ``geometry_json`` is read beside the config. Two copies of
    one file in two directories name two geometry files, so they are two
    setups — and the kept copy, which sits elsewhere, must still name the
    file the original did."""
    from mcgyvr.config import CONFIGS_DIR, keep, load

    text = BASE + 'models:\n  m:\n    geometry_json: "geo/m.json"\n'
    a = tmp_path / "a" / "mcgyvr.yaml"
    b = tmp_path / "b" / "mcgyvr.yaml"
    for path in (a, b):
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
    assert _identity(load(a)) != _identity(load(b))
    kept = keep(load(a), tmp_path / "journal")
    assert kept.parent == tmp_path / "journal" / CONFIGS_DIR
    assert _identity(load(kept)) == _identity(load(a))
    assert str(a.parent / "geo" / "m.json") in kept.read_text(encoding="utf-8")


def test_version_with_a_config_that_cannot_be_located_says_so(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from mcgyvr.cli import main

    monkeypatch.setenv("MCGYVR_CONFIG", "~nosuchuser-mcgyvr/dev.yaml")
    with pytest.raises(SystemExit) as left:
        main(["--version"])
    assert left.value.code == 0
    out = capsys.readouterr().out
    assert "config:" in out and "located" in out, out
