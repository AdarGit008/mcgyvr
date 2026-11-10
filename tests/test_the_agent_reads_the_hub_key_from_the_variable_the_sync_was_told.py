"""The rig agent and ``rig status`` read the hub key where the sync was told to.

``mcgyvr rig rungs sync --key-env NAME`` reads the rider's personal hub key from
the variable ``NAME`` (``MCGYVR_HUB_API_KEY`` when it is told none), and records
that NAME — never the key — in ``relief.yaml`` as its top-level
``api_key_env``, whether the hub lists rungs or none. The running agent's
refresh and ``rig status`` read the name back from there:

* a refresher is made when the recorded variable holds a key, and each of its
  syncs asks with that key and writes the same name back, so a refresh never
  resets it to the default, even with ``MCGYVR_HUB_API_KEY`` set too;
* a ``relief.yaml`` written before the name was recorded there is read by the
  ``api_key_env`` its rungs name; with no rung, or no file, the name is the
  default;
* ``rig status`` asks for the credits with the key in the recorded variable.

A recorded name that is not a variable's is refused, as the flag refuses it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr.fleet.files import FleetFileError, load_relief, relief_key_env
from mcgyvr.rig import rungs
from tests.rigsyncs import (
    FIRST,
    KEY,
    Hub,
    a_syncing_hub,
    a_syncing_setup,
    cli,
)

#: A rider's own variable, and a second key the default variable holds.
CUSTOM = "MY_HUB_KEY"
OTHER_KEY = "mhu_fedcba9876543210_" + "o" * 40


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_syncing_setup(tmp_path, monkeypatch)


@pytest.fixture
def hub(setup: Path) -> Iterator[Hub]:
    with a_syncing_hub(setup) as made:
        yield made


def _relief(setup: Path) -> str:
    return (setup / "relief.yaml").read_text(encoding="utf-8")


def _synced_by_hand_with_the_custom_name(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch, *rung_ids: str
) -> None:
    monkeypatch.delenv("MCGYVR_HUB_API_KEY")
    monkeypatch.setenv(CUSTOM, KEY)
    hub.answer(hub.listing(*rung_ids))
    assert cli("--key-env", CUSTOM) == 0


def _refresh(made: rungs.Refresher) -> None:
    """Run one refresh to its end: it runs on its own thread."""
    made.tick()
    for running in threading.enumerate():
        if running.name == "relief-rungs":
            running.join(timeout=10)


# --- what a sync records ----------------------------------------------------------


def test_a_sync_records_the_variables_name_beside_the_rungs(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)

    assert f"api_key_env: {CUSTOM}\nrelief:\n" in _relief(setup)
    assert relief_key_env(_relief(setup)) == CUSTOM
    assert rungs.key_env(setup) == CUSTOM
    assert KEY not in _relief(setup)


def test_the_name_is_recorded_when_the_hub_lists_no_rung(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch)

    assert "relief: {}" in _relief(setup)
    assert rungs.key_env(setup) == CUSTOM


def test_a_sync_told_no_name_records_the_default(setup: Path, hub: Hub) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli() == 0

    assert rungs.key_env(setup) == rungs.KEY_ENV == "MCGYVR_HUB_API_KEY"


# --- what the agent's refresh reads ------------------------------------------------


def test_the_refresher_reads_the_key_from_the_recorded_variable(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)
    environ = {CUSTOM: KEY}

    made = rungs.refresher_for(hub.address, environ=environ, folder=setup)

    assert made is not None and made.key_env == CUSTOM
    _refresh(made)
    assert len(hub.asked) == 2
    assert hub.asked[-1]["authorization"] == f"Bearer {KEY}"


def test_a_refresh_writes_the_recorded_name_back_not_the_default(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)
    environ = {CUSTOM: KEY, "MCGYVR_HUB_API_KEY": OTHER_KEY}

    made = rungs.refresher_for(hub.address, environ=environ, folder=setup)
    assert made is not None
    _refresh(made)

    assert hub.asked[-1]["authorization"] == f"Bearer {KEY}"
    assert rungs.key_env(setup) == CUSTOM
    (only,) = load_relief(_relief(setup))["relief"].values()
    assert only["api_key_env"] == CUSTOM


def test_no_refresher_is_made_when_the_recorded_variable_is_unset(
    setup: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)
    environ = {"MCGYVR_HUB_API_KEY": OTHER_KEY}

    assert rungs.refresher_for(hub.address, environ=environ, folder=setup) is None


def test_with_no_relief_file_the_refresher_reads_the_default(
    setup: Path, hub: Hub
) -> None:
    environ = {"MCGYVR_HUB_API_KEY": KEY}

    made = rungs.refresher_for(hub.address, environ=environ, folder=setup)

    assert made is not None and made.key_env == rungs.KEY_ENV
    hub.answer(hub.listing(FIRST))
    _refresh(made)
    assert hub.asked[-1]["authorization"] == f"Bearer {KEY}"
    assert rungs.key_env(setup) == rungs.KEY_ENV


# --- a relief.yaml written before the name was recorded -----------------------------


def _older(api_key_env: str) -> str:
    return (
        "relief:\n"
        f"  hitchhike-{FIRST}:\n"
        "    address: https://hub.example.org/v1\n"
        f"    model: hitchhike@{FIRST}\n"
        f"    api_key_env: {api_key_env}\n"
        "    width: 2\n"
    )


def test_an_older_file_is_read_by_the_name_its_rungs_carry(tmp_path: Path) -> None:
    (tmp_path / "relief.yaml").write_text(_older(CUSTOM), encoding="utf-8")

    assert rungs.key_env(tmp_path) == CUSTOM


@pytest.mark.parametrize("text", ["relief: {}\n", _older("MCGYVR_HUB_API_KEY"), ""])
def test_an_older_file_naming_no_other_variable_keeps_the_default(
    tmp_path: Path, text: str
) -> None:
    (tmp_path / "relief.yaml").write_text(text, encoding="utf-8")

    assert rungs.key_env(tmp_path) == rungs.KEY_ENV


def test_with_no_relief_file_the_name_is_the_default(tmp_path: Path) -> None:
    assert rungs.key_env(tmp_path) == rungs.KEY_ENV


@pytest.mark.parametrize("value", ["'mhu key with spaces'", "1ST", "[A, B]", "''"])
def test_a_recorded_name_that_is_not_a_variables_is_refused(
    tmp_path: Path, value: str
) -> None:
    text = f"api_key_env: {value}\nrelief: {{}}\n"
    (tmp_path / "relief.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(FleetFileError, match="NAME of the variable"):
        load_relief(text)
    with pytest.raises(rungs.SyncError, match="NAME of the variable"):
        rungs.key_env(tmp_path)


# --- what rig status reads ------------------------------------------------------------


def test_status_asks_for_the_credits_with_the_recorded_variable(
    setup: Path,
    hub: Hub,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.rig import verbs

    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)
    asked: list[str] = []

    def balance(hub: str, key: str) -> str:
        asked.append(key)
        return "7.5"

    monkeypatch.setattr(rungs, "balance", balance)
    capsys.readouterr()

    verbs._say_credits(hub.address)

    assert asked == [KEY]
    assert capsys.readouterr().out == "credits: 7.5\n"


def test_status_names_the_recorded_variable_when_it_is_unset(
    setup: Path,
    hub: Hub,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.rig import verbs

    _synced_by_hand_with_the_custom_name(setup, hub, monkeypatch, FIRST)
    monkeypatch.delenv(CUSTOM)
    capsys.readouterr()

    verbs._say_credits(hub.address)

    assert f"set ${CUSTOM} to your personal hub key" in capsys.readouterr().out
