"""The endpoint, key and model a custom provider points at are exported.

At the end of a successful setup (and a serve up), mcgyvr writes
``provider.env`` holding ``MCGYVR_ENDPOINT``, ``MCGYVR_API_KEY`` and
``MCGYVR_MODEL``, and prints the same three on stdout. The key is read from
the unit key file mcgyvr already keeps — never minted a second time — and a
unit that asks for no key exports an empty key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import handoff, unitkey
from mcgyvr.config import Config, Ladder, Unit


def _config(*, address: str, model: str = "example-org/Coder-S-GGUF") -> Config:
    return Config(
        path=Path("/nowhere/setup"),
        data={},
        units={"first": Unit(name="first", address=address, model=model)},
        ladder=Ladder(names=("first",)),
    )


def test_endpoint_adds_v1_once() -> None:
    assert handoff.endpoint_of("http://box:8080") == "http://box:8080/v1"
    assert handoff.endpoint_of("http://box:8080/v1") == "http://box:8080/v1"
    assert (
        handoff.endpoint_of("https://api.example.com") == "https://api.example.com/v1"
    )


def test_from_config_takes_the_first_ladder_unit() -> None:
    provider = handoff.from_config(
        _config(address="http://localhost:8080/v1", model="qwen2.5-coder:7b")
    )

    assert provider is not None
    assert provider.endpoint == "http://localhost:8080/v1"
    assert provider.model == "qwen2.5-coder:7b"
    assert provider.api_key is None, "a localhost unit asks for no key"


def test_from_config_reads_the_units_existing_key() -> None:
    unitkey.ensure("box1", 8080)
    key = unitkey.for_address("http://box1:8080/v1")
    assert key is not None

    provider = handoff.from_config(_config(address="http://box1:8080/v1"))
    assert provider is not None and provider.api_key == key


def test_from_config_has_no_handoff_for_an_empty_ladder() -> None:
    config = Config(
        path=Path("/nowhere/setup"),
        data={},
        units={},
        ladder=Ladder(names=()),
    )
    assert handoff.from_config(config) is None


def test_render_and_write_export_the_three_variables(tmp_path: Path) -> None:
    provider = handoff.Provider(
        endpoint="http://box1:8080/v1", api_key="k" * 43, model="m/1"
    )
    path = handoff.write(tmp_path, provider)

    assert path == tmp_path / "provider.env"
    text = path.read_text(encoding="utf-8")
    assert text.splitlines() == [
        "export MCGYVR_ENDPOINT=http://box1:8080/v1",
        f"export MCGYVR_API_KEY={'k' * 43}",
        "export MCGYVR_MODEL=m/1",
    ]


def test_print_provider_lines_up_and_names_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = handoff.Provider(
        endpoint="http://box1:8080/v1", api_key=None, model="m/1"
    )
    handoff.print_provider(provider, tmp_path / "provider.env")

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "endpoint: http://box1:8080/v1"
    assert out[1].startswith("api-key:  (none")
    assert "provider.env" in out[1]
    assert out[2] == "model:    m/1"
