"""Gate 5 guards the envelope; a step argument must not route around it.

Six of the eight kernel-arms steps kept an output override from their bare-run
days (``--out PATH``, ``--out-dir DIR``) and three a ``--force`` that waived
their own exists-check. The door passes everything after ``--`` to the step
verbatim, and gate 5's write-once check, gate 7's ``### RIGMOVED`` stamp and
gate 8's read-back all look only at ``$RUN_OUT_DIR/<declared>``: through the
door, ``-- --out <the recorded 2026-09-02 file>`` overwrote committed evidence
while the door printed green, and ``-- --out-dir <anywhere>`` filed a run where
no gate could see it.

The door owns the envelope. It refuses those tokens before gate 1 — nothing is
checked, nothing is made, no rig is read — and the steps no longer parse them:
the sanctioned re-run path is ``--suffix`` over a ``RUN_REWRITES`` declaration.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import onedoor

ESCAPES = (
    ["--out", "/tmp/elsewhere.tsv"],
    ["--out=/tmp/elsewhere.tsv"],
    ["--out-dir", "/tmp/elsewhere"],
    ["--out-dir=/tmp/elsewhere"],
    ["--force"],
)

FLAG_CASE = re.compile(r"^\s*(--out|--out-dir|--force)(\s*\|\s*[-\w=*]+)*\)")


@pytest.mark.parametrize(
    "args", ESCAPES, ids=[a[0].split("=")[0] + str(i) for i, a in enumerate(ESCAPES)]
)
def test_an_output_or_force_token_after_the_dashes_is_refused_before_any_gate(
    tmp_path: Path, args: list[str]
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1", "--", *args], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert args[0].split("=")[0] in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists(), "the step ran with an output override"
    assert onedoor.docker_log(Path(env["RUN_DOCKER"])) == [], "a gate ran first"


def test_no_kernel_arms_step_parses_an_output_override_or_force() -> None:
    offenders: dict[str, list[str]] = {}
    for step in sorted(onedoor.KERNEL_ARMS.glob("[0-9]*-*.sh")):
        hits = [
            line.strip()
            for line in step.read_text(encoding="utf-8").splitlines()
            if FLAG_CASE.match(line)
        ]
        if hits:
            offenders[step.name] = hits
    assert not offenders, (
        f"steps still parse an output override or --force: {offenders}; the "
        "door owns the envelope and a re-run is --suffix over RUN_REWRITES"
    )
