"""A source that is not a git repository is copied without its secrets.

A git source brings its tracked files only, so an ignored ``.env`` never
reaches a task. A directory with no git has no ignore rules to say what is
whose, and it used to be copied whole, keys and all, into the workspace a
contract's commands run in. Now the copy leaves behind what holds a secret by
name — dotenv files, keys and certificates, ``.netrc``, cloud and SSH
credential folders, a registry login, and a package-manager settings file
carrying a token — and the sandbox says which paths it left behind.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr.sandbox.base import Sandbox
from mcgyvr.sandbox.tempdir import TempDirSandbox

#: Every value below carries this, so finding it anywhere is finding a leak.
MARK = "test-secret-mark-0000"

SECRETS = {
    ".env": f"API_KEY={MARK}\n",
    ".env.production": f"API_KEY={MARK}\n",
    ".envrc": f"export API_KEY={MARK}\n",
    "certs/server.pem": f"-----BEGIN PRIVATE KEY-----\n{MARK}\n",
    "deploy.key": f"{MARK}\n",
    ".netrc": f"machine example.invalid login me password {MARK}\n",
    ".npmrc": f"//registry.npmjs.org/:_authToken={MARK}\n",
    ".pypirc": f"[pypi]\nusername = __token__\npassword = {MARK}\n",
    ".aws/credentials": f"[default]\naws_secret_access_key = {MARK}\n",
    ".gcloud/application_default_credentials.json": f'{{"key": "{MARK}"}}\n',
    ".azure/accessTokens.json": f'[{{"token": "{MARK}"}}]\n',
    ".ssh/id_ed25519": f"{MARK}\n",
    ".docker/config.json": f'{{"auths": {{"r": {{"auth": "{MARK}"}}}}}}\n',
    ".config/gcloud/credentials.db": f"{MARK}\n",
}

#: What the task still gets: the code, and settings files that hold no login.
KEPT = {
    "src/app.py": "x = 1\n",
    "README.md": "# app\n",
    "web/.npmrc": "registry=https://registry.npmjs.org/\n",
    ".docker/daemon.json": "{}\n",
    ".config/tool.toml": "[tool]\n",
}

#: What the sandbox names as left behind: a folder once, a file by its path.
LEFT_OUT = (
    ".aws",
    ".azure",
    ".config/gcloud",
    ".docker/config.json",
    ".env",
    ".env.production",
    ".envrc",
    ".gcloud",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".ssh",
    "certs/server.pem",
    "deploy.key",
)


@pytest.fixture
def opened(tmp_path: Path) -> Iterator[Sandbox]:
    source = tmp_path / "plain"
    for name, text in {**SECRETS, **KEPT}.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(text, encoding="utf-8")
    assert not (source / ".git").exists()
    with TempDirSandbox(source) as sandbox:
        yield sandbox


def test_no_secret_is_copied(opened: Sandbox) -> None:
    for name in SECRETS:
        assert not (opened.workspace / name).exists(), name
    for path in opened.workspace.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(opened.workspace).parts:
            assert MARK not in path.read_text(encoding="utf-8", errors="replace"), path


def test_the_rest_of_the_tree_is_copied(opened: Sandbox) -> None:
    for name, text in KEPT.items():
        assert (opened.workspace / name).read_text(encoding="utf-8") == text, name


def test_the_sandbox_names_every_path_it_left_behind(opened: Sandbox) -> None:
    (note,) = [n for n in opened.notes if "secrets" in n]
    named = note.rsplit(": ", 1)[1].split(", ")
    assert tuple(named) == LEFT_OUT


def test_a_git_source_carries_no_such_note(tmp_path: Path) -> None:
    from tests import livejournal as lj

    repo = lj.make_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        assert not [n for n in sandbox.notes if "secrets" in n]
