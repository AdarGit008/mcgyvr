"""One vocabulary of what a credential looks like: the value shapes and the
name words every credential check in the product shares.

Four checks used to decide, each from its own private list, whether something is
a credential: the gate's secret scan (``mcgyvr.gate.secrets``), the config
loader's refusal of a pasted key (``mcgyvr.config``), the sandbox's environment
filter and its rc-file check (``mcgyvr.sandbox.base``). The lists disagreed — a
GitHub token had to be exactly 36 characters in one and 20-or-more in another,
an ``sk-`` key allowed ``-`` and ``_`` in one and not the other, the name words
were four different sets — so a key could pass one check and be refused by the
next. This module is the single place that policy lives; each check still keeps
its own *anchoring* (the scan looks anywhere in a line, the config loader matches
the whole value) and its own *match rule* for names (an exact key, a word inside
a variable name, a word followed by ``=``), but the shapes and the words are
defined here once.

Where the old lists disagreed on a value shape, the shape kept here is the
widest of them — the smaller length floor, the larger character class — so
unifying can only refuse *more*, never less: nothing any check refused before is
let through now. ``VALUE_SHAPES`` carries, per provider, the unanchored core
regex plus whether the gate should bound it with ``\\b``; :func:`scan_pattern`
compiles it for a search anywhere in a line and :func:`whole_value_pattern`
for a whole-value match. ``CREDENTIAL_WORDS`` is the union of every name word
the checks held, and ``KNOWN_CREDENTIAL_VARS`` the full environment-variable
names the substring rule would otherwise miss.

Stdlib only, and importing nothing from the rest of the package, so every check
can depend on it without a cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ValueShape:
    """One provider's credential value shape.

    ``body`` is the core regex with no anchoring of its own, so each check can
    wrap it the way it reads its input. ``word_bounded`` says whether the gate's
    anywhere-in-a-line scan should fence it with ``\\b`` on both sides: true for
    a token that is a run of word characters (so it is not caught mid-identifier),
    false for the private-key header, which begins with ``-----`` and carries its
    own boundary.
    """

    code: str
    message: str
    body: str
    word_bounded: bool


# The value shapes, widest form of each. Order is load-bearing for the gate: a
# line reports the first shape that matches it, so the specific provider shapes
# come before any broader rule the caller appends. Length floors are the lower
# of the two old lists (GitHub 36 -> 20, Google 35 -> 30, GitHub PAT 22 -> 20)
# and character classes the wider (``sk-`` gains ``-`` and ``_`` and drops to 16,
# the shape a ``sk-proj-...`` key needs), so no old refusal is lost. Stripe and
# the private-key header were the gate's alone; keeping them here means the
# config loader refuses them too.
VALUE_SHAPES: tuple[ValueShape, ...] = (
    ValueShape(
        "private-key",
        "private key block",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        word_bounded=False,
    ),
    ValueShape(
        "aws-access-key-id",
        "AWS access key id",
        r"AKIA[0-9A-Z]{16}",
        word_bounded=True,
    ),
    ValueShape(
        "github-token",
        "GitHub token",
        r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}",
        word_bounded=True,
    ),
    ValueShape(
        "github-pat",
        "GitHub fine-grained token",
        r"github_pat_[A-Za-z0-9_]{20,}",
        word_bounded=True,
    ),
    ValueShape(
        "slack-token",
        "Slack token",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        word_bounded=True,
    ),
    ValueShape(
        "google-api-key",
        "Google API key",
        r"AIza[0-9A-Za-z_\-]{30,}",
        word_bounded=True,
    ),
    ValueShape(
        "stripe-secret-key",
        "Stripe secret key",
        r"(?:sk|rk)_live_[A-Za-z0-9]{16,}",
        word_bounded=True,
    ),
    ValueShape(
        "openai-key",
        "OpenAI-style secret key",
        r"sk-[A-Za-z0-9_\-]{16,}",
        word_bounded=True,
    ),
)


def scan_pattern(shape: ValueShape) -> re.Pattern[str]:
    """Compile ``shape`` for a search anywhere in a line (the gate's anchoring).

    A word-bounded shape is fenced with ``\\b`` so it is not matched inside a
    longer identifier; the private-key header is left as it is.
    """
    core = rf"\b{shape.body}\b" if shape.word_bounded else shape.body
    return re.compile(core)


def whole_value_pattern(shape: ValueShape) -> re.Pattern[str]:
    """Compile ``shape`` for a whole-value match (the config loader's anchoring):
    the entire value, start to end, must be the credential and nothing else."""
    return re.compile(rf"^(?:{shape.body})$")


# The name words, the union of every list that decided a name meant a credential:
# the config loader's exact keys, the sandbox env filter's substring words and
# its known full names, and the rc-file check's words. Lowercased; each check
# applies its own rule to them (``config`` an exact key match, the env filter a
# substring of the variable name, the rc-file check the word followed by ``=``).
CREDENTIAL_WORDS: frozenset[str] = frozenset(
    {
        "access_key",
        "api_key",
        "apikey",
        "auth",
        "auth_token",
        "credential",
        "credentials",
        "key",
        "passwd",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "session",
        "token",
    }
)


# Full environment-variable names a credential uses whose spelling the substring
# rule would not catch on its own kept here as the backstop the sandbox env
# filter consults alongside the word match.
KNOWN_CREDENTIAL_VARS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
)


def _words_alternation() -> str:
    """The credential words as a regex alternation, longest first so a longer
    word is preferred where one is a prefix of another."""
    return "|".join(sorted(map(re.escape, CREDENTIAL_WORDS), key=len, reverse=True))


#: The credential words as a substring pattern: any of them appearing anywhere in
#: a name, case-insensitive. The sandbox env filter uses this to decide a
#: variable name holds a credential.
NAME_SUBSTRING = re.compile(f"(?:{_words_alternation()})", re.IGNORECASE)

#: The credential words as a ``word...=`` pattern: one of them, then any word
#: characters, then ``=`` or ``:``. The sandbox rc-file check uses this to spot a
#: login line in a ``.npmrc``-style file.
NAME_ASSIGNMENT = re.compile(rf"(?:{_words_alternation()})\w*\s*[=:]", re.IGNORECASE)
