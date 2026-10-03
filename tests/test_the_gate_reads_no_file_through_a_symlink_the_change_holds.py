"""The gate reads no file through a symlink the change holds.

A worker hands back text and never a link; a symlink in the change was left by
a command, and the gate runs on the host. A link ``src/pkg/a.py`` to an
absolute path, made inside a container, names a path on the host when the host
reads it, so a gate that followed it would read a file of the user's that no
container could reach, and could carry what it read out in a finding — into
the journal, and into the prompt of the next attempt.

So a symlink in the change is not text the gate scans: the secret scan, the
structural rungs and the host-side checkers read nothing through it. Git still
sees it — the change lists it, and the scope rung judges its name like any
other path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.gate.adapters.python import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, read_added_text
from mcgyvr.gate.secrets import scan_secrets
from tests import livejournal as lj

#: The first line of a file outside the workspace: a secret-shaped assignment,
#: then an import nothing uses, so both the scan and the linter would speak.
OUTSIDE = 'api_key = "test-outside-0000"\nimport os\n'


@pytest.fixture
def changed(tmp_path: Path) -> ChangeSet:
    outside = tmp_path / "outside.py"
    outside.write_text(OUTSIDE, encoding="utf-8")
    repo = lj.make_repo(tmp_path / "workspace")
    (repo / "src" / "pkg" / "linked.py").symlink_to(outside)
    return ChangeSet.detect(repo)


def _linked(changeset: ChangeSet) -> list[str]:
    return [c.path for c in changeset.files if c.path == "src/pkg/linked.py"]


def test_the_change_still_lists_the_link(changed: ChangeSet) -> None:
    assert _linked(changed) == ["src/pkg/linked.py"]


def test_no_added_text_is_read_through_the_link(changed: ChangeSet) -> None:
    (change,) = [c for c in changed.files if c.path == "src/pkg/linked.py"]
    assert read_added_text(change, changed.repo) == {}


def test_the_secret_scan_reads_nothing_through_the_link(changed: ChangeSet) -> None:
    assert scan_secrets(changed) == []


def test_no_language_adapter_takes_the_link_as_its_file(changed: ChangeSet) -> None:
    # The host-side checkers are handed what `owned()` returns, so this is
    # where a link is kept from them. A run of ruff over the link is no pin:
    # ruff already said nothing about it before the link was dropped here.
    assert PythonAdapter().owned(changed.files) == []
