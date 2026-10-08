"""Nothing is looked up online when offline is asked.

Owner, 2026-10-07: model knowledge is read online "when a network is
available", and "offline falls back to the shipped catalog". Plan section
4.3: a refresh asked offline (or under ``HF_HUB_OFFLINE=1``) leaves the cache
and the shipped catalog as they are; a network that does not answer is named.

Promises:

* Asked offline, by the flag or by ``HF_HUB_OFFLINE``, the refresh asks no
  URL at all and says it was offline.
* Online, the refresh asks the Hub for each known model and the boards of the
  use case, and files what it read in the cache, each number with its source
  and date; a model whose revision has not moved keeps the numbers it had.
* A network that does not answer stops the lookups at once, and the refresh
  names it with the reason.

The Hub and board answers are the ones recorded on
2026-10-07 (``tests/fixtures/knowledge_online/``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from mcgyvr.knowledge import boards, online
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from tests.knowledge_online import Recorded, never

DAY = date(2026, 10, 7)
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def online_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(online.OFFLINE_ENV, raising=False)


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


@pytest.mark.usefixtures("home", "online_allowed")
def test_a_network_that_does_not_answer_is_named_and_stops_the_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def down(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
        asked.append(url)
        raise online.NoNetworkError(f"{url} did not answer: timed out")

    monkeypatch.setattr(online, "urllib_get", down)
    done = online.refresh(_known(), use_case="coding", offline=False, today=DAY)
    assert len(asked) == 1, "the first silence stops every other lookup"
    assert done.mode == online.ONLINE
    assert done.written == ()
    (failed,) = done.failed
    assert failed[0] == "network"
    assert "timed out" in failed[1]
