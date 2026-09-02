"""A declared ``.json`` artifact is read back as JSON, and a stamp never lands in it.

``5-correctness.sh`` declares ``correctness.json`` and ``6-moe-slots.sh``
``placement-null.json`` beside its TSV. Gate 7 stamped ``### RIGMOVED`` into
every declared file by name alone, so the one run where those files most
needed to stay readable — a rig that moved — was the run that broke them
(``json.loads``: Extra data). And gate 8 ran the TSV parser over them, which
skips every line that is neither ``###`` nor tab-separated: any JSON
"parsed", and the green line said it was checked.

So gate 7 appends the stamp only to ``*.tsv``; for any other declared file it
writes the line to a ``<name>.RIGMOVED`` sidecar and names it on stderr. Gate
8 validates ``*.json`` with ``json.loads`` and everything else with
``rows.read``, so ``checked`` means checked.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import onedoor


def _json_step(env_file: Path, after: str, *, json_text: str = '{"flips": 0}') -> str:
    body = onedoor.probe_step(env_file, after=after)
    body = body.replace(
        "# RUN_ARTIFACTS: probe.tsv\n", "# RUN_ARTIFACTS: probe.tsv probe.json\n"
    )
    return body.replace(
        '} > "$out"\n',
        '} > "$out"\n'
        + f"printf '%s\\n' '{json_text}' > \"${{RUN_OUT_DIR:?}}/probe.json\"\n",
    )


def test_a_rig_that_moved_leaves_the_json_readable_and_notes_it_beside(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root, "alpha", "1-probe.sh", _json_step(tmp_path / "e", f"touch '{flag}'")
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    rig = onedoor.rig_stub(stubs, "srv1", moved_flag=flag)
    env = onedoor.door_env(root, stubs, rig=rig)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 1, (result.stdout, result.stderr)
    out_dir = onedoor.envelope(root, "alpha")
    assert json.loads((out_dir / "probe.json").read_text(encoding="utf-8")) == {
        "flips": 0
    }
    tsv = (out_dir / "probe.tsv").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("### RIGMOVED") for line in tsv), tsv
    sidecar = out_dir / "probe.json.RIGMOVED"
    assert sidecar.is_file(), onedoor.written_under_records(root)
    assert sidecar.read_text(encoding="utf-8").startswith("### RIGMOVED "), (
        sidecar.read_text()
    )
    assert "probe.json" in result.stderr, result.stderr


def test_a_json_artifact_that_does_not_parse_is_exit_1_and_named(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _json_step(tmp_path / "e", "", json_text='{"flips": '),
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.json" in result.stderr, result.stderr
    assert "run.sh: green" not in result.stderr, result.stderr
    assert (onedoor.envelope(root, "alpha") / "probe.json").read_text(
        encoding="utf-8"
    ) == '{"flips": \n'
