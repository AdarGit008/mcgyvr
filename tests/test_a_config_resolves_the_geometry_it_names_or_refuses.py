"""A relative ``geometry_json`` is resolved once, at load, or the load fails.

``units.<name>.launch.geometry_json`` may be written relative: the line means
"the scan filed next to me". :func:`mcgyvr.config._resolved_paths` makes it
absolute once, at load, against the config's resolved (symlink-followed)
directory, and refuses a relative value when the config has no path. Two
situations make "next to me" a question:

1. **There is no path.** ``parse(text)`` takes ``path=None``. A canonical
   rendering that carried the word ``./x.json`` would name a different file
   from every directory, and :meth:`Config.canonical` promises that two files
   that load to the same config "render to the same bytes".

2. **The path goes through a symlink.** A ladder selected by linking it to the
   default config path (``mcgyvr-lab/records/plans/config-library.md`` §6/D5)
   is reached through the link. The link's directory is not the entry's, so an
   unresolved join would render one set of bytes two ways, one of which names
   a geometry that is not on disk.

What these tests pin is one answer, reached once: a config resolves the file it
names when it can say where it is, and refuses to load when it cannot. Nothing
here asserts a spelling of the message beyond the key it must name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load, parse

BASE = """\
units:
  only:
    address: http://localhost:8080
    model: a-model
    rig: local
ladder:
- only
"""

RELATIVE = """\
units:
  only:
    address: http://localhost:8080
    model: a-model
    rig: local
    launch:
      geometry_json: "./geometry.json"
ladder:
- only
"""


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
    config with no location does not name a geometry at all. Carrying the word
    unresolved is how a kept snapshot ends up naming a file next to the journal
    and a run ends up opening whatever the working directory holds. This repo
    refuses rather than guesses when the
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
    assert "units.only.launch.geometry_json" in str(raised.value)


def test_a_config_reached_through_a_symlink_is_the_same_config(
    tmp_path: Path,
) -> None:
    """Identity is a property of the config, not of the route taken to it.

    A ladder selected by symlinking its entry to the default path (the design
    in ``mcgyvr-lab/records/plans/config-library.md`` §6/D5) is read through the link.
    The scan sits beside the entry, because that is where the entry's author filed
    it — so "beside me" is the entry's directory, and reaching the same bytes
    two ways must not produce two setups, one of which names a file that was
    never written.
    """
    entry = _config_beside_its_scan(tmp_path / "library" / "big")
    link = tmp_path / "config" / "mcgyvr.yaml"
    link.parent.mkdir()
    link.symlink_to(entry)

    through_link = load(link)
    named = Path(through_link.units["only"].launch["geometry_json"])
    assert named == entry.parent / "geometry.json"
    assert named.exists(), "the rendering names a scan that is not on disk"
    assert through_link.canonical() == load(entry).canonical()


def test_the_geometry_a_run_opens_is_the_one_the_identity_names(
    tmp_path: Path,
) -> None:
    """One resolution, read by both the canonical rendering and the code that
    opens the file.

    The path ``load`` resolved is the one in the canonical text and the one
    ``mcgyvr.serving.declared_models`` opens. A rendering that names a file the
    run does not open is evidence about a setup that was never served.
    """
    from mcgyvr.serving import declared_models

    entry = _config_beside_its_scan(tmp_path / "library" / "big")
    link = tmp_path / "config" / "mcgyvr.yaml"
    link.parent.mkdir()
    link.symlink_to(entry)

    config = load(link)
    named = config.units["only"].launch["geometry_json"]
    assert named in config.canonical()
    # The scan is an empty list: it is the right file, and it carries no row.
    # What matters is which path the refusal names.
    with pytest.raises(Exception, match=str(entry.parent / "geometry.json")):
        declared_models(config)
