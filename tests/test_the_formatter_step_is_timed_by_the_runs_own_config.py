"""The formatter step is timed by the run's own ``--config``, as acceptance is.

A deterministic contract (``format``) runs its program on the floor: ``mcgyvr
run`` hands each step to :func:`mcgyvr.drive.run_tool_step`, which holds it to
the task ceiling. The floor called it without the run's config, so the step
was given the ceiling of the config at the *default* location, not the one
``--config`` named: a run that allowed 45 s gave its formatter 60 s, and a run
that allowed a minute could have its formatter cut at someone else's second.
Acceptance has been timed by the named config since PIPE-03
(``test_delivery_writes_what_was_judged_where_the_contract_said``); the step
before it now is too.

Judged by the ceiling the sandbox was given, not by how long the run took:
the machine running this may be busy.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


@pytest.mark.skipif(shutil.which("ruff") is None, reason="the floor runs ruff")
def test_the_formatter_is_given_the_run_configs_ceiling_not_the_default_ones(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    # The default location allows a minute; the config this run names, 45 s.
    default = lj.append_policy(
        lj.make_config(tmp_path / "default"), "task_timeout_s: 60\n"
    )
    monkeypatch.setenv("MCGYVR_CONFIG", str(default))
    named = lj.append_policy(lj.make_config(tmp_path / "named"), "task_timeout_s: 45\n")

    real_run = TempDirSandbox.run
    given: list[tuple[tuple[str, ...], float | None]] = []

    def run(self: TempDirSandbox, command: Any, **kwargs: Any) -> Any:
        given.append((tuple(command), kwargs.get("timeout")))
        return real_run(self, command, **kwargs)

    monkeypatch.setattr(TempDirSandbox, "run", run)

    lj.main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(named),
        ]
    )

    out = capsys.readouterr()
    formatter = [timeout for argv, timeout in given if argv[:2] == ("ruff", "format")]
    assert formatter, f"the formatter never ran: {given}\n{out.out}\n{out.err}"
    assert formatter == [45.0], (
        f"--config set a 45 s ceiling and the formatter was given {formatter}: "
        f"it was timed by the default config's 60 s"
    )
