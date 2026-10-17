""

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


#
#
#
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
    #
    #
    #
    _p(
        "hardcoded-credential",
        "credential-shaped assignment to a literal",
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key"
        r"|auth[_-]?token|client[_-]?secret|private[_-]?key)\b"
        r"\s*[:=]\s*(['\"])[^'\"]{5,}\1",
    ),
)


def scan_secrets(changeset: ChangeSet) -> list[Finding]:
    ""
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
                    break  #
    return findings
