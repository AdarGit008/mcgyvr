"""The secret scan is the gate's last line against a model leaking a credential.

These tests pin both directions: known credential shapes on an added line fail
hard, and the safe shapes the check must *not* flag — env lookups, bare
references, ordinary code, and secrets the worker did not add — stay clean, so
the check is not one users learn to switch off.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.secrets import scan_secrets


def one_file(
    repo: Path,
    path: str,
    text: str,
    added: set[int] | None,
    *,
    status: str = "A",
    is_binary: bool = False,
) -> ChangeSet:
    """Write ``text`` and build a one-file change set over it.

    ``added=None`` attributes the whole file (the untracked-file case).
    """
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    if added is None:
        added = set(range(1, len(text.split("\n")) + 1))
    change = FileChange(
        path=path,
        status=status,
        added_lines=frozenset(added),
        is_binary=is_binary,
    )
    return ChangeSet(repo=repo, base="HEAD", files=(change,))


def codes(findings: list[Finding]) -> list[str | None]:
    return [f.code for f in findings]


def test_private_key_block_fails(tmp_path: Path) -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n"
    findings = scan_secrets(one_file(tmp_path, "key.pem", text, {1, 2, 3}))
    assert "private-key" in codes(findings)


def test_aws_access_key_fails(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "c.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n', {1})
    assert codes(scan_secrets(cs)) == ["aws-access-key-id"]


def test_github_token_fails(tmp_path: Path) -> None:
    token = "ghp_" + "a" * 36
    cs = one_file(tmp_path, "c.py", f'tok = "{token}"\n', {1})
    assert "github-token" in codes(scan_secrets(cs))


def test_hardcoded_password_fails_even_if_dummy(tmp_path: Path) -> None:
    """Conservative bias: a placeholder still fails — blocking it is the cheap side."""
    cs = one_file(tmp_path, "c.py", 'password = "hunter2placeholder"\n', {1})
    assert codes(scan_secrets(cs)) == ["hardcoded-credential"]


def test_env_lookup_is_not_flagged(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "c.py", 'password = os.environ["DB_PASSWORD"]\n', {1})
    assert scan_secrets(cs) == []


def test_reference_without_literal_is_not_flagged(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "c.py", "api_key = settings.api_key\n", {1})
    assert scan_secrets(cs) == []


def test_ordinary_code_is_not_flagged(tmp_path: Path) -> None:
    text = "count = 5\nname = 'widget'\ntotal = count * 2\n"
    assert scan_secrets(one_file(tmp_path, "c.py", text, {1, 2, 3})) == []


def test_pre_existing_secret_is_not_the_workers(tmp_path: Path) -> None:
    """A secret on a line the worker didn't touch is out of scope."""
    text = 'OLD = "AKIAIOSFODNN7EXAMPLE"\nnew_value = 42\n'
    cs = one_file(tmp_path, "c.py", text, {2})  # worker only added line 2
    assert scan_secrets(cs) == []


def test_untracked_file_is_scanned_whole(tmp_path: Path) -> None:
    text = "def f():\n    return 1\n\n\nSECRET = 'AKIAIOSFODNN7EXAMPLE'\n"
    cs = one_file(tmp_path, "new.py", text, None)  # whole file added
    assert "aws-access-key-id" in codes(scan_secrets(cs))


def test_binary_change_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"AKIAIOSFODNN7EXAMPLE\x00\xff")
    change = FileChange("blob.bin", "M", frozenset({1}), is_binary=True)
    cs = ChangeSet(repo=tmp_path, base="HEAD", files=(change,))
    assert scan_secrets(cs) == []


def test_deletion_is_skipped(tmp_path: Path) -> None:
    change = FileChange("gone.py", "D", frozenset(), is_binary=False)
    cs = ChangeSet(repo=tmp_path, base="HEAD", files=(change,))
    assert scan_secrets(cs) == []


def test_slack_and_google_and_stripe_shapes(tmp_path: Path) -> None:
    # Token shapes are assembled at runtime so no literal secret sits in this
    # source file — otherwise the repo's own push protection flags the fixture.
    slack = "xox" + "b-" + "1" * 12 + "-" + "a" * 16
    google = "AIza" + "B" * 35
    stripe = "sk" + "_live_" + "c" * 24
    text = f"a = '{slack}'\nb = '{google}'\nc = '{stripe}'\n"
    found = set(codes(scan_secrets(one_file(tmp_path, "c.py", text, {1, 2, 3}))))
    assert {"slack-token", "google-api-key", "stripe-secret-key"} <= found
