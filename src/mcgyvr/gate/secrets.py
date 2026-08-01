"""Scan worker-added lines for credentials.

A model-authored change is a credible way for a secret to enter a repository —
hallucinated, or copied out of the context the model was given. This check is
deterministic pattern matching, not entropy heuristics: recognizable key
prefixes, private-key blocks, and credential-shaped assignments. It runs on the
added lines of every changed text file (which, for a brand-new untracked file,
is the whole file) and skips binaries.

**Conservative by design.** For an autonomous gate, blocking a dummy password
is the correct trade against leaking a real one, so a placeholder-looking
literal still fails. What the patterns deliberately do *not* flag is a value
that is plainly a reference rather than a secret — an environment lookup, a
config key with no literal — because those are the common, safe shapes and
flagging them would train users to disable the check.

Ordering is the runner's job: this must run before the expensive checks so a
leak fails fast, and it is a hard failure, never a warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mcgyvr.gate.changeset import ChangeSet, read_added_text
from mcgyvr.gate.findings import Finding


@dataclass(frozen=True)
class _Pattern:
    code: str
    message: str
    regex: re.Pattern[str]


def _p(code: str, message: str, pattern: str, flags: int = 0) -> _Pattern:
    return _Pattern(code=code, message=message, regex=re.compile(pattern, flags))


# High-confidence token shapes: a match is almost never a false positive, so
# these carry the strongest signal. Prefixes and lengths follow each issuer's
# published format.
_PATTERNS: tuple[_Pattern, ...] = (
    _p(
        "private-key",
        "private key block",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
    ),
    _p("aws-access-key-id", "AWS access key id", r"\bAKIA[0-9A-Z]{16}\b"),
    _p(
        "github-token",
        "GitHub token",
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b",
    ),
    _p("slack-token", "Slack token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    _p("google-api-key", "Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _p(
        "stripe-secret-key", "Stripe secret key", r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"
    ),
    _p("openai-key", "OpenAI-style secret key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    # Credential-shaped assignment: a secret-ish name bound to a quoted literal.
    # Requires the literal immediately after the operator, so an env lookup or a
    # bare reference (`token = os.environ["X"]`) does not match.
    _p(
        "hardcoded-credential",
        "credential-shaped assignment to a literal",
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key"
        r"|auth[_-]?token|client[_-]?secret|private[_-]?key)\b"
        r"\s*[:=]\s*(['\"])[^'\"]{5,}\1",
    ),
)


def scan_secrets(changeset: ChangeSet) -> list[Finding]:
    """Findings for every worker-added line that matches a secret pattern.

    Runs on non-binary, non-deleted changes only; binaries have no lines to
    scan and a deletion adds nothing. Because a new file's added lines are the
    whole file, untracked additions are scanned end to end.
    """
    findings: list[Finding] = []
    for change in changeset.text_changes():
        added = read_added_text(change, changeset.repo)
        for line_no in sorted(added):
            text = added[line_no]
            for pattern in _PATTERNS:
                if pattern.regex.search(text):
                    findings.append(
                        Finding(
                            check="secret",
                            path=change.path,
                            line=line_no,
                            code=pattern.code,
                            message=pattern.message,
                        )
                    )
                    break  # one finding per line is enough to fail it
    return findings
