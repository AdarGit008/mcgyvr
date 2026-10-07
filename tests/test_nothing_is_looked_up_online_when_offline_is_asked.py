"""Nothing is looked up online when offline is asked.

Owner, 2026-10-07: model knowledge is read online "when a network is
available", and "offline falls back to the shipped catalog". Plan section
4.3: ``--offline`` (or ``HF_HUB_OFFLINE=1``) uses the cache and the shipped
catalog only; a network that does not answer is named and the plan is still
made.

Promises:

* Asked offline, by the flag or by ``HF_HUB_OFFLINE``, the refresh asks no
  URL at all and says it was offline.
* ``mcgyvr recommend --offline`` makes its plan from the cache and the shipped
  catalog, asks no URL, and its plan says the knowledge was offline.
* Online, the refresh asks the Hub for each known model and the boards of the
  use case, and files what it read in the cache, each number with its source
  and date; a model whose revision has not moved keeps the numbers it had.
* A network that does not answer stops the lookups at once with the reason,
  and the plan is made from the cache and the shipped catalog.

The rig is invented; the Hub and board answers are the ones recorded on
2026-10-07 (``tests/fixtures/knowledge_online/``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, cli
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.knowledge import boards, online
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from tests.knowledge_online import Recorded, never
from tests.test_recommend import FREE_MIB, HOST, _is_scan_read, scan_json

DAY = date(2026, 10, 7)
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def online_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(online.OFFLINE_ENV, raising=False)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invented rig that answers its scan, and no decision endpoint."""

    def ssh(host: str, command: str) -> str:
        assert _is_scan_read(command), command
        return scan_json(host, FREE_MIB)

    def probe(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source="recommend", live=False, reason="stub", how="stub", elapsed_s=0.0
        )

    monkeypatch.setattr(scan_module, "_ssh", ssh)
    monkeypatch.setattr(availability, "probe_endpoint", probe)


def _known() -> tuple[kr.ModelRecord, ...]:
    return ks.offline().records


@pytest.mark.usefixtures("home", "online_allowed")
def test_the_offline_flag_asks_no_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(online, "urllib_get", never)
    done = online.refresh(_known(), use_case="coding", offline=True)
    assert done.mode == online.OFFLINE
    assert done.written == () and done.failed == ()


@pytest.mark.usefixtures("home")
@pytest.mark.parametrize("said", ["1", "true", "YES", "on"])
def test_hf_hub_offline_asks_no_url(monkeypatch: pytest.MonkeyPatch, said: str) -> None:
    monkeypatch.setenv(online.OFFLINE_ENV, said)
    monkeypatch.setattr(online, "urllib_get", never)
    done = online.refresh(_known(), use_case="coding", offline=False)
    assert done.mode == online.OFFLINE


def test_recommend_takes_offline_on_its_command_line() -> None:
    parser = cli.build_parser()
    argv = ["recommend", "--use-case", "coding", "--users", "1", "--host", HOST]
    assert parser.parse_args([*argv, "--offline"]).offline is True
    assert parser.parse_args(argv).offline is False


@pytest.mark.usefixtures("home", "online_allowed", "rig")
def test_an_offline_recommend_asks_no_url_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(online, "urllib_get", never)
    argv = ["recommend", "--use-case", "coding", "--users", "1", "--host", HOST]
    assert cli.main([*argv, "--offline"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["knowledge"]["mode"] == online.OFFLINE
    assert plan["source"] == "hf-catalog"


@pytest.mark.usefixtures("home", "online_allowed")
def test_online_the_hub_and_the_boards_are_asked_and_the_cache_filed() -> None:
    server = Recorded()
    done = online.refresh(
        _known(), use_case="coding", offline=False, get=server, today=DAY
    )
    assert done.mode == online.ONLINE

    asked = server.urls()
    assert online.api_url(f"{CODER_7B}-GGUF") in asked
    assert set(asked) >= {b.url for b in boards.boards_for("coding")}
    # The 7B's revision has not moved since the catalog read it: its numbers
    # are kept, and no header is read again.
    assert not [u for u in asked if u.endswith(".gguf")]

    cached = {one.model_id: one for one in ks.offline().records}
    shipped = {one.model_id: one for one in ks.shipped()}
    assert ks.cache_file(CODER_7B, "Q4_K_M") in done.written
    assert cached[CODER_7B].size_bytes == shipped[CODER_7B].size_bytes
    # The models the recorded answers do not hold are named, not guessed.
    assert {what for what, _why in done.failed} >= {
        "Qwen/Qwen2.5-Coder-14B-Instruct Q4_K_M"
    }


@pytest.mark.usefixtures("home", "online_allowed", "rig")
def test_a_network_that_does_not_answer_is_named_and_the_plan_still_made(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[str] = []

    def down(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
        asked.append(url)
        raise online.NoNetworkError(f"{url} did not answer: timed out")

    monkeypatch.setattr(online, "urllib_get", down)
    argv = ["recommend", "--use-case", "coding", "--users", "1", "--host", HOST]
    assert cli.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(asked) == 1, "the first silence stops every other lookup"
    assert plan["knowledge"]["mode"] == online.ONLINE
    (failed,) = plan["knowledge"]["failed"]
    assert failed["what"] == "network"
    assert "timed out" in failed["why"]
    assert plan["source"] == "hf-catalog"
    assert plan["placement"] is not None
