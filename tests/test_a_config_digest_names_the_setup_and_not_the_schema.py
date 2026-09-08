"""A config's identity names the setup, and a kept copy names its own contents.

RED. Every test here fails on this commit, and none of them is fixed here:
this file is the specification, and what it specifies is a decision the owner
has to make.

Owner's ruling R2 (2026-09-06), quoted at ``src/mcgyvr/config.py:1003``: the
digest is taken over "the loaded and validated tree and never over the file's
bytes, because an identity that moved when a comment was added would name the
edit and not the setup". :meth:`Config.canonical` renders that tree *with every
default the loader filled in written out* (``config.py:960``), so the tree it
hashes is not only what the file says — it is what the file says plus whatever
the schema of the day supplies. Add one optional key to the schema and every
config that predates it renders one more line and re-identifies, with no byte
changing on disk.

That is not a typo in the code. It follows from R2 being right: if identity
covers the settings, and a new key with a default is a new setting, then the
settings genuinely changed. What is wrong is that the change is silent, that
nothing checks it, and that it leaves stored evidence whose name is a false
statement about its contents.

The evidence, read out of the live journal on 2026-09-08 after
``ladder.tiers.*.output_tokens`` merged:

* ``~/.mcgyvr/config/mcgyvr.yaml`` went ``cfg-a049…`` to ``cfg-6a01…`` with no
  edit to the file;
* ``<journal>/configs/cfg-ff6ea286809c40da07….yaml``, written before the key
  existed, now recomputes to ``cfg-0ae9515b37af030c…`` — the snapshot
  ``config.py:560`` documents as the way to re-select a past run's setup
  (``MCGYVR_CONFIG=<dir>/configs/<digest>.yaml``) is filed under a name that no
  longer hashes to what is inside it;
* the snapshot in the same directory that *does* declare the key still matches,
  which is what makes the first one a lie rather than a convention.

The schema change is simulated here rather than depended on. A test that
imported the real ``output_tokens`` field would pass the day someone renamed
it and prove nothing; the property is about *any* optional key nobody set, so
the tests add one to ``SCHEMA`` and hold the digest to it.

These tests pin behaviour, not a spelling. Nothing below asserts on a prefix,
a schema fingerprint or a rendering — only on which digests must be equal.
That is what makes the first test the fork: canonicalising the identity over
what a config *declares* turns it green, and making the schema visible in the
digest instead does not, because a visible prefix still moves. Choosing the
second is choosing to overrule the first, and it is worth doing on purpose
rather than by leaving a suite red.

Note that ``cfg-v1-…`` spelled from ``SCHEMA_VERSION`` (``config.py:44``) is
not one of the answers: that number is "bumped only by a breaking change to
this file's shape", and adding an optional key is not that, so the prefix would
have been unchanged the day ``output_tokens`` landed.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.config import (
    SCHEMA,
    Field,
    keep,
    load,
    parse,
)

LOCAL_ONLY = """\
version: 1
sources:
  local:
    base_url: "http://localhost:8080"
    api: openai
ladder:
  tiers:
    - name: only
      source: local
      model: a-model
"""

WITH_GEOMETRY = (
    LOCAL_ONLY
    + """\
models:
  a-model:
    geometry_json: geometry.json
"""
)

#: An optional key of the shape that caused this: a rung-level number nobody is
#: obliged to state, whose absence the loader fills in with ``None``. It is the
#: shape ``output_tokens`` has, deliberately, and it is not that field: the
#: property is about any such key, and a test bound to one real field would go
#: green the day that field was renamed.
UNSET_OPTIONAL = Field(
    "output_pace",
    "int",
    "A rung-level number no config in this test states.",
    min_value=1,
    bind_hint="e.g. 8",
)


def _schema_gaining(path: tuple[str, ...], extra: Field) -> tuple[Field, ...]:
    """``SCHEMA`` with ``extra`` added to the block at the dotted ``path``.

    A build of mcgyvr one merge later, in other words. Rebuilt rather than
    mutated because :class:`Field` is frozen and the nested blocks are shared
    tuples: appending in place would leave every other test running under a
    schema this one invented.
    """

    def descend(fields: tuple[Field, ...], rest: tuple[str, ...]) -> tuple[Field, ...]:
        head, *tail = rest
        out: list[Field] = []
        for field in fields:
            if field.name != head:
                out.append(field)
            elif tail:
                out.append(replace(field, block=descend(field.block, tuple(tail))))
            else:
                out.append(replace(field, block=(*field.block, extra)))
        return tuple(out)

    return descend(SCHEMA, path)


def test_a_digest_does_not_move_when_a_key_this_config_never_set_is_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing one. A digest names the setup, so a key nobody set is not
    part of it.

    Adding ``output_tokens`` re-identified every config on the machine that had
    never heard of it. The digest is what a journal row, a result file and
    ``MCGYVR_CONFIG`` all resolve through (``config.py:560``), so a digest that
    moves for a reason no operator can see makes two runs of one unchanged
    setup unjoinable, and makes "the config changed" unfalsifiable — which is
    the failure R2 was ruled to prevent.

    Failing this is the decision. One answer turns it green — a defaulted key
    is not identity, so the digest is taken over what the config declares. The
    other answer on the table, making the schema visible in the digest so a
    cross-schema comparison is loud rather than silent, leaves this red by
    design: it says the movement is real and must be seen. Nothing here asserts
    a spelling, so either can be argued; what cannot be argued is today, where
    the movement happens and nobody is told.
    """
    before = parse(LOCAL_ONLY).digest()

    monkeypatch.setattr(
        "mcgyvr.config.SCHEMA",
        _schema_gaining(("ladder", "tiers"), UNSET_OPTIONAL),
    )
    after = parse(LOCAL_ONLY).digest()

    assert after == before, (
        f"the same unchanged config identifies as {before} under one schema and "
        f"{after} under the next, because canonical() renders the key it never "
        f"set. Nothing in the file changed, so nothing about the setup did."
    )


def test_a_kept_config_hashes_to_the_name_it_was_filed_under(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot's filename is a claim about its contents, and it must stay true.

    ``keep`` files ``canonical()`` at ``<journal>/configs/<digest>.yaml``
    (``config.py:1049``) and ``config.py:560`` sells that path as how a past
    run's setup is re-selected. The claim is checked nowhere. There is a file
    in the live journal today for which it is false, and a reader who trusts
    the name gets a config that is not the one the name says.

    This is a round trip, so it should hold forever and across every build that
    can still load the file: a snapshot that no longer means what its name says
    must be refused loudly, not read as if it did.
    """
    kept = keep(parse(LOCAL_ONLY), tmp_path / "journal")

    monkeypatch.setattr(
        "mcgyvr.config.SCHEMA",
        _schema_gaining(("ladder", "tiers"), UNSET_OPTIONAL),
    )
    reloaded = load(kept)

    assert reloaded.digest() == kept.stem, (
        f"{kept.name} holds a config that hashes to {reloaded.digest()}. The "
        f"file is intact and still loads; its name is the part that is wrong, "
        f"and MCGYVR_CONFIG={kept} now re-selects a setup under an identity "
        f"nothing will match."
    )


def test_a_kept_config_reloads_to_the_setup_it_was_kept_from(tmp_path: Path) -> None:
    """The same lie, with no schema change at all: canonical() reads a fact off
    the caller.

    ``canonical`` promises that "loading this text back yields the same config,
    and the same digest" (``config.py:974``), unconditionally. It cannot: a
    relative ``geometry_json`` is written out absolute against ``self.path``
    (``_pinned``, ``config.py:986``), and a config parsed from text nobody
    filed — :func:`parse` takes ``path=None``, and ``gate/semantic_driver.py``
    calls it that way — has no ``self.path`` to resolve against, so the
    relative name is written through unchanged. ``keep`` then stores it beside
    the journal, where re-loading it resolves that name against the *journal's*
    directory and yields a different setup under a different digest.

    Same family as the two above and the same remedy is not automatic: the
    digest here moves because ``canonical()`` renders something the config's
    declared tree does not contain. Whatever answer settles the schema question
    has to settle this one too, or a snapshot goes on naming a geometry file
    that is not where the name says.
    """
    config = parse(WITH_GEOMETRY)
    kept = keep(config, tmp_path / "journal")
    reloaded = load(kept)

    assert reloaded.digest() == kept.stem, (
        f"{kept.name} reloads as {reloaded.digest()}: the kept text names "
        f"`geometry.json` relative to wherever it is read from, so the copy "
        f"filed to be re-selectable is the one copy that resolves it wrong."
    )
