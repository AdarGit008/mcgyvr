"""Scan the added text of a change set for credential-shaped lines.

Each pattern carries a stable finding code, a human message, and the compiled
regex. A matching added line produces one ``Finding`` on that line; nothing is
read from lines the worker did not add, and non-text changes (binary, deleted,
symlink) are skipped upstream by ``ChangeSet.text_changes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mcgyvr.credential_shapes import VALUE_SHAPES, scan_pattern
from mcgyvr.gate.changeset import ChangeSet, read_added_text
from mcgyvr.gate.findings import Finding


@dataclass(frozen=True)
class _Pattern:
    code: str
    message: str
    regex: re.Pattern[str]


def _p(code: str, message: str, pattern: str, flags: int = 0) -> _Pattern:
    return _Pattern(code=code, message=message, regex=re.compile(pattern, flags))


# The high-signal provider shapes come from the one shared vocabulary
# (`mcgyvr.credential_shapes`), each compiled for a search anywhere in a line,
# followed here by one conservative assignment heuristic the shared shapes do
# not cover. Order is load-bearing, because a line reports only the first
# pattern that matches it, so the specific provider shapes stay ahead of the
# broad assignment rule.
_PATTERNS: tuple[_Pattern, ...] = (
    *(_Pattern(s.code, s.message, scan_pattern(s)) for s in VALUE_SHAPES),
    # Broadest rule: a credential-sounding name assigned a quoted literal. It
    # stays last so a line holding a real token prefix is reported by the
    # specific pattern above, and it deliberately ignores non-literal values
    # such as env lookups or attribute references.
    _p(
        "hardcoded-credential",
        "credential-shaped assignment to a literal",
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key"
        r"|auth[_-]?token|client[_-]?secret|private[_-]?key)\b"
        r"\s*[:=]\s*(['\"])[^'\"]{5,}\1",
    ),
)


def scan_secrets(changeset: ChangeSet) -> list[Finding]:
    """Return one finding for each added line that looks like a credential.

    Only text changes are examined. For each of them the added lines are read
    from the working tree, and every line is matched against ``_PATTERNS`` in
    order, stopping at the first hit so a single line never yields duplicates.
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
                    break  # one finding per line: the most specific pattern wins
    return findings
