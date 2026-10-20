"""`setup --api` writes no request timeout, and suggests none.

A hosted unit with no `request_timeout_s` waits for its reply however long it
takes (`test_a_hosted_unit_waits_for_its_reply_however_long_it_takes.py`). A
setup that wrote a number there, or put one beside the commented key as the
thing to bind, would hand the operator back the bound that ends a slow
reply as an `error`.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize, parse_api_unit
from tests.machine_shapes import detection, shape

SPEC = (
    "model=deepseek-v4-pro,"
    "address=https://api.deepseek.com,"
    "api_key_env=DEEPSEEK_API_KEY"
)


def test_an_api_setup_writes_no_request_timeout(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(
        path, detection=detection(shape("bare")), api_units=(parse_api_unit(SPEC),)
    )

    written = "\n".join(
        (path / name).read_text(encoding="utf-8")
        for name in (FLEET_FILENAME, POLICY_FILENAME)
    )
    keyed = [line for line in written.splitlines() if "request_timeout_s" in line]
    assert keyed, "the key is no longer shown, so an operator cannot find it"
    for line in keyed:
        assert line.lstrip().startswith("#"), f"a timeout was bound: {line!r}"
        assert not re.search(r"\d", line), (
            f"the commented key suggests a number to bind: {line!r}"
        )

    config = load_config(path)
    assert all(unit.request_timeout_s is None for unit in config.units.values())
