"""A relative ``geometry_json`` is resolved once, at load, or the load fails.

RED. Every test here fails on this commit.

``models.<id>.geometry_json`` may be written relative, and the live config
writes it that way: ``~/.mcgyvr/config/mcgyvr.yaml`` line 54 says
``geometry_json: ./Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json``. The line means
"the scan filed next to me", and it is resolved against ``self.path.parent`` in
two places — ``Config._pinned`` (``src/mcgyvr/config.py:993``) for the identity,
and ``mcgyvr.serving.declared_models`` (``src/mcgyvr/serving/__init__.py:732``)
for the file that is actually opened. Neither knows where "me" is in two
situations, and each answers differently:

1. **There is no path.** ``parse(text)`` takes ``path=None``, and both sites
   guard on it — ``config.py:989`` returns ``data`` unpinned, and
   ``serving/__init__.py:734`` leaves ``where`` relative and hands it to
   ``open``. So the config's identity carries the word ``./x.json``, which
   names a different file from every directory, and the run opens whatever
   sits in the process's working directory. Measured against the live config
   on 2026-09-08: loaded from its path it identifies as ``cfg-02ab991e…`` and
   canonicalises the geometry as
   ``/home/adaramir/.mcgyvr/config/Qwen3.6-….geometry.json``; parsed from the
   same bytes with no path it identifies as ``cfg-68b454c9…`` and canonicalises
   ``./Qwen3.6-….geometry.json``, which exists from nowhere.

   That contradicts :meth:`Config.canonical`, which promises without
   qualification that "loading this text back yields the same config, and the
   same digest" (``config.py:974``) — :func:`keep` files the canonical text
   under the journal, and a relative name written through re-resolves against
   the journal directory on the way back in.

2. **The path goes through a symlink.** ``records/plans/config-library.md``
   §6/D5 proposes selecting a ladder by linking it to the default config path.
   Reached through the link, ``self.path.parent`` is the link's directory and
   not the entry's, so one file with one set of bytes gets two identities, and
   the geometry named by one of them is not on disk. Measured the same day on
   a copy of the live config: entry ``cfg-25d592ef…``, link ``cfg-97b08fad…``,
   identical bytes.

What these tests pin is one answer, reached once: a config resolves the file it
names when it can say where it is, and refuses to load when it cannot. Nothing
here asserts a spelling of the message beyond the key it must name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load, parse

BASE = """\
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

RELATIVE = BASE + 'models:\n  a-model:\n    geometry_json: "./geometry.json"\n'


def _config_beside_its_scan(directory: Path) -> Path:
    """A config and the scan it names, filed together, as an entry would be."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "geometry.json").write_text("[]", encoding="utf-8")
    where = directory / "mcgyvr.yaml"
    where.write_text(RELATIVE, encoding="utf-8")
    return where


def test_a_relative_geometry_json_with_nowhere_to_read_it_beside_is_refused() -> None:
    """No path is not a default: it is a question the text cannot answer.

    ``./geometry.json`` names a different file from every directory, so a
    config with no location does not name a geometry at all. Today
    ``config.py:989`` and ``serving/__init__.py:734`` both take that as
    permission to carry the word unresolved, which is how a kept snapshot ends
    up naming a file next to the journal and a run ends up opening whatever the
    working directory holds. This repo refuses rather than guesses when the
    fact it needs is absent — ``emit.py`` will not report an unscanned host,
    and ``check_contract_against_rung`` says "an invented window is the defect
    this function exists to end" — and the same answer is the only one here
    that does not silently mean something different per caller.

    The refusal has to name the key: an operator reading it has one line to
    change, either by loading the file from its path or by writing the path out
    in full.
    """
    with pytest.raises(ConfigSchemaError) as raised:
        parse(RELATIVE)
    assert "models.a-model.geometry_json" in str(raised.value)


def test_a_config_reached_through_a_symlink_is_the_same_config(
    tmp_path: Path,
) -> None:
    """Identity is a property of the config, not of the route taken to it.

    A ladder selected by symlinking its entry to the default path (the design
    in ``records/plans/config-library.md`` §6/D5) is read through the link. The
    scan sits beside the entry, because that is where the entry's author filed
    it — so "beside me" is the entry's directory, and reaching the same bytes
    two ways must not produce two setups, one of which names a file that was
    never written.
    """
    entry = _config_beside_its_scan(tmp_path / "library" / "big")
    link = tmp_path / "config" / "mcgyvr.yaml"
    link.parent.mkdir()
    link.symlink_to(entry)

    through_link = load(link)
    named = Path(through_link.data["models"]["a-model"]["geometry_json"])
    assert named == entry.parent / "geometry.json"
    assert named.exists(), "the identity names a scan that is not on disk"
    assert through_link.digest() == load(entry).digest()


def test_the_geometry_a_run_opens_is_the_one_the_identity_names(
    tmp_path: Path,
) -> None:
    """One resolution, read by both the digest and the code that opens the file.

    ``Config._pinned`` resolves for the identity and
    ``mcgyvr.serving.declared_models`` resolves again for the load. Two sites
    deriving one meaning is how they come apart: through a symlink they already
    disagree, and a digest that names a file the run does not open is evidence
    about a setup that was never served.
    """
    from mcgyvr.serving import declared_models

    entry = _config_beside_its_scan(tmp_path / "library" / "big")
    link = tmp_path / "config" / "mcgyvr.yaml"
    link.parent.mkdir()
    link.symlink_to(entry)

    config = load(link)
    named = config.data["models"]["a-model"]["geometry_json"]
    assert named in config.canonical()
    # The scan is an empty list: it is the right file, and it carries no row.
    # What matters is which path the refusal names.
    with pytest.raises(Exception, match=str(entry.parent / "geometry.json")):
        declared_models(config)
