"""``RUN_ID`` names one door invocation, so no two invocations may mint one.

``RUN_ID`` is ``<RUN_DATE>-<campaign>-<step>[-<suffix>]`` (DECISIONS), it is the
token a ``### START`` carries, the prefix every container is named with and
the key a ``### RIGMOVED`` or a refusal is filed under. The first cut of gate
5 let a ``RUN_REWRITES`` step run twice on one day with no ``--suffix``: the
superseded file and its successor both carried
``run_id=2026-09-02-alpha-probe``, two measurements under one id, and only a
THIRD run was refused — with a message stating the rule the second had
already broken.

So gate 5 refuses to supersede a file whose ``run_id`` equals the id this run
is about to mint: the re-run needs ``--suffix``. Nothing is moved, the step
does not start.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor


def test_superseding_under_the_same_run_id_is_refused_with_the_suffix_hint(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", directive="RUN_REWRITES"),
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs)
    first = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert first.returncode == 0, (first.stdout, first.stderr)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    text = artifact.read_text(encoding="utf-8")
    before = onedoor.written_under_records(root)
    (tmp_path / "e").unlink()

    second = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert second.returncode == 2, (second.stdout, second.stderr)
    assert "--suffix" in second.stderr, second.stderr
    assert "probe.tsv" in second.stderr, second.stderr
    assert onedoor.written_under_records(root) == before, "the refusal moved something"
    assert artifact.read_text(encoding="utf-8") == text
    assert not (tmp_path / "e").exists(), "the step ran under a second-hand run id"

    third = onedoor.door(
        root, ["alpha", "probe", "--host", "srv1", "--suffix", "pass2"], env
    )
    assert third.returncode == 0, (third.stdout, third.stderr)
