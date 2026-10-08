"""The offline core names the hub no more than it does today.

The hub is reached through ``src/mcgyvr/rig/`` and the ``mcgyvr rig`` command,
and should be known nowhere else. Today it is: relief rungs, riders and
hitchhiking are threaded through config, the escalation ladder, the pool and
the runner. Those are to move out, a step at a time; this
file makes sure no step goes backwards.

:data:`tests.hub_borders.WORDS_NOT_YET_MOVED` is every tracked file of the
offline core that holds one of :data:`tests.hub_borders.HUB_WORDS`, with how
many times; the module says which words and how they are read. The scan must
find exactly the list:

* a file or a word that is not listed, or a count above the listed one, is a
  hub word that entered the core, and fails;
* a count below the listed one, or a listed file that no longer holds the
  word, fails too, until the list is lowered to what the tree holds. A list
  with slack in it is one a later change could refill in silence; lowering it
  in the change that cleaned the file keeps the ratchet at the tree.

Both directions are the growth rule of the uninvented-machines list
(:func:`tests.uninvented_machines.growth`), once each way. That a pull request
did not raise the list itself is CI's to see (``tests/hub_borders.py
--compare``). What the scan does not hold: one hub word replaced by another of
the same word in a listed file keeps the count and passes.
"""

from __future__ import annotations

import re

from tests.hub_borders import (
    HF_HUB_FILES,
    HUB_WORDS,
    NOT_CORE_DIRS,
    NOT_CORE_FILES,
    SRC,
    WORDS_NOT_YET_MOVED,
    counted,
    in_core,
    scan_words,
)
from tests.uninvented_machines import growth


def test_no_hub_word_enters_the_offline_core() -> None:
    grown = growth(WORDS_NOT_YET_MOVED, scan_words())
    assert not grown, (
        "a hub word entered the offline core (src/mcgyvr/ but cli.py and rig/); "
        "keep it in rig/ or the rig command, and never raise "
        "WORDS_NOT_YET_MOVED:\n  " + "\n  ".join(grown)
    )


def test_the_list_holds_no_more_than_the_core_does() -> None:
    slack = growth(scan_words(), WORDS_NOT_YET_MOVED)
    assert not slack, (
        "the core holds fewer hub words than WORDS_NOT_YET_MOVED says (found -> "
        "listed); lower the list to what the tree holds, an entry at 0 is "
        "removed:\n  " + "\n  ".join(slack)
    )


def test_what_the_core_is_not_exists() -> None:
    """The exclusions name real places, so a rename cannot widen the core's
    blind spot or quietly drop the hub client into it."""
    for rel in NOT_CORE_FILES:
        assert (SRC / rel).is_file(), rel
    for rel in NOT_CORE_DIRS:
        assert (SRC / rel / "__init__.py").is_file(), rel


def test_each_file_that_names_the_hugging_face_hub_still_does() -> None:
    """``hub`` goes unread only where the Hugging Face Hub is named, so the
    exemption cannot outlive the reason for it: a file that no longer names
    that Hub leaves :data:`tests.hub_borders.HF_HUB_FILES`, and ``hub`` is
    read there again."""
    hub = HUB_WORDS["hub"]
    for rel in sorted(HF_HUB_FILES):
        assert in_core(rel), f"{rel} is not in the core"
        text = (SRC / rel).read_text(encoding="utf-8")
        assert re.search(hub, text), f"{rel} names no Hub; take it off HF_HUB_FILES"


def test_hub_is_left_unread_in_those_files_and_only_there() -> None:
    found = scan_words()
    assert not [rel for rel in HF_HUB_FILES if "hub" in found.get(rel, {})]
    assert "hub" in found["runner.py"]


def test_the_words_are_read_in_every_spelling_where_the_hub_is_meant() -> None:
    text = (
        "A relief rung is lent through the hub to a rider (hitchhike); "
        "on_hub_error, MCGYVR_HUB_API_KEY, a crew and its pool session, a pooled "
        "unit. class ReliefRung, RELIEF_UNAVAILABLE, RIDER_LIMIT, HITCHHIKE_ON, "
        "POOLED, CREW_SIZE, HUB_URL, HubClient, pool_session, mcgyvr.pool.session."
    )
    assert counted(text) == {
        "hub": 5,
        "hitchhik": 2,
        "relief": 3,
        "rider": 2,
        "crew": 2,
        "pool session": 3,
        "pooled": 2,
    }


def test_what_only_looks_like_a_hub_word_is_not_read() -> None:
    text = (
        "github, GitHub, GITHUB_TOKEN, HF_HUB_OFFLINE, HUGGING_FACE_HUB_TOKEN, "
        "a screw, a provider, an override, ride along, it lends its card."
    )
    assert counted(text) == {}


def test_both_directions_of_the_ratchet_refuse_a_change() -> None:
    listed = {"a.py": {"relief": 2}}
    assert growth(listed, {"a.py": {"relief": 2}}) == []
    assert growth({"a.py": {"relief": 2}}, listed) == []
    assert growth(listed, {"a.py": {"relief": 3}}) == ["a.py: relief 2 -> 3"]
    assert growth(listed, {"a.py": {"relief": 2, "hub": 1}}) == ["a.py: hub 0 -> 1"]
    assert growth(listed, {"a.py": {"relief": 2}, "b.py": {"rider": 1}}) == [
        "b.py: rider 0 -> 1"
    ]
    assert growth({"a.py": {"relief": 1}}, listed) == ["a.py: relief 1 -> 2"]
    assert growth({}, listed) == ["a.py: relief 0 -> 2"]
