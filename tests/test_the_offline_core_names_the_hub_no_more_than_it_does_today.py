"""The offline core names the hub no more than it does today.

The product runs offline for one user. The hub — other people's cards, lent
through a broker — is reached through ``src/mcgyvr/rig/`` and the ``mcgyvr
rig`` command in ``src/mcgyvr/cli.py``, and should be known nowhere else. Today
it is: relief rungs, riders, hitchhiking and the pooled sandbox are threaded
through config, the escalation ladder, the pool and the runner. Those are to
move out, a step at a time; this file makes sure no step goes backwards.

:data:`NOT_YET_MOVED` is every file of the offline core that holds one of
:data:`HUB_WORDS`, with how many times. The offline core is every file under
``src/mcgyvr/`` but ``cli.py`` and ``rig/``, whatever its kind: a shell script
or a prompt shipped in the package is read too. The scan must find exactly the
list:

* a file or a word that is not listed, or a count above the listed one, is a
  hub word that entered the core, and fails;
* a count below the listed one, or a listed file that no longer holds the
  word, fails too, until the list is lowered to what the tree holds. A list
  with slack in it is one a later change could refill in silence; lowering it
  in the change that cleaned the file keeps the ratchet at the tree.

So the list only shrinks: entries may be lowered or removed, never added or
raised. What the scan does not hold: one hub word replaced by another of the
same word in a listed file keeps the count and passes.

The words are read lower case, at the start of a word (``github`` is not a
hub word, ``on_hub_error`` holds one), plus the hub key's variable. A capital
``Hub`` is the Hugging Face Hub throughout the core and is not read; the few
lower-case ``hub`` that also name Hugging Face (a parameter, a source tag) are
listed and marked, and stay.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "mcgyvr"

#: What is not the offline core: the hub client, and the command line that is
#: its one way in (``tests/test_only_the_command_line_imports_the_hub_client.py``).
NOT_CORE_FILES: frozenset[str] = frozenset({"cli.py"})
NOT_CORE_DIRS: frozenset[str] = frozenset({"rig"})

#: The words that name the hub or what it brokers, each with the pattern that
#: reads it. ``crew`` and ``pool session`` are absent from the core today, and
#: listed so that they stay absent.
HUB_WORDS: dict[str, re.Pattern[str]] = {
    "hub": re.compile(r"(?<![a-z])hub"),
    "MCGYVR_HUB": re.compile(r"(?<![A-Z_])MCGYVR_HUB"),
    "hitchhik": re.compile(r"(?<![a-z])hitchhik"),
    "relief": re.compile(r"(?<![a-z])relief"),
    "rider": re.compile(r"(?<![a-z])rider"),
    "crew": re.compile(r"(?<![a-z])crew"),
    "pool session": re.compile(r"(?<![a-z])pool session"),
    "pooled": re.compile(r"(?<![a-z])pooled"),
}

#: Every file of the offline core that holds a hub word, relative to
#: ``src/mcgyvr/``, with how many of each. Entries may only be lowered or
#: removed, never added or raised.
NOT_YET_MOVED: dict[str, dict[str, int]] = {
    "capacity.py": {"hub": 2, "relief": 10, "rider": 1},
    "config.py": {
        "hub": 17,
        "MCGYVR_HUB": 1,
        "hitchhik": 3,
        "relief": 61,
        "rider": 18,
    },
    "contract.py": {"relief": 1, "rider": 1},
    "docgen.py": {"hub": 1, "relief": 2},
    "emit.py": {"hitchhik": 1, "rider": 1},
    "escalate.py": {"hub": 5, "relief": 47, "rider": 8},
    "fleet/files.py": {"hub": 2, "hitchhik": 1, "relief": 20, "rider": 2},
    "initialize.py": {"relief": 4},
    # The Hugging Face Hub's source tags (`hub-api`, `hub-config`); they stay.
    "knowledge/online.py": {"hub": 2},
    "knowledge/record.py": {"hub": 2},
    "pool.py": {"hub": 4, "relief": 39, "rider": 2},
    "route.py": {"relief": 3},
    "runner.py": {"hub": 14, "hitchhik": 5, "relief": 12, "rider": 3, "pooled": 2},
    "sandbox/pooled.py": {"hub": 11, "pooled": 5},
    # The Hugging Face Hub's address, as a parameter and a field; they stay.
    "serving/fetchlist.py": {"hub": 5},
    "serving/gate-scripts/serve-fetch.py": {"hub": 4},
    "weights.py": {"relief": 1},
    "whole.py": {"hub": 1},
}


def _in_core(rel: str) -> bool:
    return rel not in NOT_CORE_FILES and rel.split("/", 1)[0] not in NOT_CORE_DIRS


def _counted(text: str) -> dict[str, int]:
    """How many of each hub word ``text`` holds, words it does not hold left out."""
    counts = {word: len(pattern.findall(text)) for word, pattern in HUB_WORDS.items()}
    return {word: n for word, n in counts.items() if n}


def _scan() -> dict[str, dict[str, int]]:
    """Every file of the offline core that holds a hub word, with the counts."""
    found: dict[str, dict[str, int]] = {}
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SRC).as_posix()
        if not _in_core(rel):
            continue
        counts = _counted(path.read_text(encoding="utf-8", errors="replace"))
        if counts:
            found[rel] = counts
    return found


def _pairs(listing: dict[str, dict[str, int]]) -> dict[tuple[str, str], int]:
    return {
        (rel, word): n for rel, counts in listing.items() for word, n in counts.items()
    }


def _grown(
    found: dict[str, dict[str, int]], listed: dict[str, dict[str, int]]
) -> list[str]:
    """Each file and word ``found`` holds more of than ``listed`` allows."""
    have, allowed = _pairs(found), _pairs(listed)
    return [
        f"{rel}: {word} {allowed.get((rel, word), 0)} -> {n}"
        for (rel, word), n in sorted(have.items())
        if n > allowed.get((rel, word), 0)
    ]


def _slack(
    found: dict[str, dict[str, int]], listed: dict[str, dict[str, int]]
) -> list[str]:
    """Each file and word ``listed`` allows more of than ``found`` holds."""
    have, allowed = _pairs(found), _pairs(listed)
    return [
        f"{rel}: {word} listed {n}, found {have.get((rel, word), 0)}"
        for (rel, word), n in sorted(allowed.items())
        if have.get((rel, word), 0) < n
    ]


def test_no_hub_word_enters_the_offline_core() -> None:
    grown = _grown(_scan(), NOT_YET_MOVED)
    assert not grown, (
        "a hub word entered the offline core (src/mcgyvr/ but cli.py and rig/); "
        "keep it in rig/ or the rig command, and never raise NOT_YET_MOVED:\n  "
        + "\n  ".join(grown)
    )


def test_the_list_holds_no_more_than_the_core_does() -> None:
    slack = _slack(_scan(), NOT_YET_MOVED)
    assert not slack, (
        "the core holds fewer hub words than NOT_YET_MOVED says; lower the "
        "list to what the tree holds (an entry at 0 is removed):\n  "
        + "\n  ".join(slack)
    )


def test_what_the_core_is_not_exists() -> None:
    """The exclusions name real places, so a rename cannot widen the core's
    blind spot or quietly drop the hub client into it."""
    for rel in NOT_CORE_FILES:
        assert (SRC / rel).is_file(), rel
    for rel in NOT_CORE_DIRS:
        assert (SRC / rel / "__init__.py").is_file(), rel


def test_the_words_are_read_where_the_hub_is_meant_and_nowhere_else() -> None:
    text = (
        "A relief rung is lent through the hub to a rider (hitchhike); "
        "on_hub_error, MCGYVR_HUB_API_KEY, a crew and its pool session, a pooled "
        "unit. Not: github, the Hugging Face Hub, HF_HUB_OFFLINE, a screw."
    )
    assert _counted(text) == {
        "hub": 2,
        "MCGYVR_HUB": 1,
        "hitchhik": 1,
        "relief": 1,
        "rider": 1,
        "crew": 1,
        "pool session": 1,
        "pooled": 1,
    }


def test_neither_half_of_the_ratchet_lets_a_change_through() -> None:
    """Both comparisons above, on a synthetic tree and list."""
    listed = {"a.py": {"relief": 2}}
    assert _grown({"a.py": {"relief": 2}}, listed) == []
    assert _slack({"a.py": {"relief": 2}}, listed) == []
    assert _grown({"a.py": {"relief": 3}}, listed) == ["a.py: relief 2 -> 3"]
    assert _grown({"a.py": {"relief": 2, "hub": 1}}, listed) == ["a.py: hub 0 -> 1"]
    assert _grown({"a.py": {"relief": 2}, "b.py": {"rider": 1}}, listed) == [
        "b.py: rider 0 -> 1"
    ]
    assert _slack({"a.py": {"relief": 1}}, listed) == ["a.py: relief listed 2, found 1"]
    assert _slack({}, listed) == ["a.py: relief listed 2, found 0"]
