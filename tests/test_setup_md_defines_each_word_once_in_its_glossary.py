"""SETUP.md carries a glossary: each word mcgyvr uses, defined once.

The words a request meets — how a prompt becomes contracts, where they run,
what a hub shares, who and what is named — are defined in one table in
`mcgyvr.docgen`, rendered into the generated SETUP.md. Every word is there,
each once, and the retired words have no entry.
"""

from __future__ import annotations

from mcgyvr import docgen

#: The words the glossary must define (owner's list, I-06).
WORDS = (
    "decomposition",
    "scaffold",
    "fill",
    "draft",
    "vet",
    "proposer",
    "direct",
    "delegate",
    "rung",
    "top rung",
    "ladder",
    "unit",
    "standing session",
    "hitchhike",
    "general pool",
    "crew pool",
    "rig",
    "host",
    "system",
    "session",
    "writer",
    "family",
    "floor",
)


def test_every_word_has_one_entry_and_nothing_else_does() -> None:
    terms = [term for term, _ in docgen.GLOSSARY]
    assert sorted(terms) == sorted(WORDS)
    assert len(set(terms)) == len(terms)


def test_the_retired_words_have_no_entry() -> None:
    terms = {term for term, _ in docgen.GLOSSARY}
    assert "orchestrator" not in terms
    assert not any("relief" in term for term in terms)
    assert not any("relief rung" in meaning for _, meaning in docgen.GLOSSARY)


def test_setup_md_renders_each_entry_under_its_own_heading() -> None:
    text = docgen.render_setup()
    start = text.index("## Glossary\n")
    section = text[start : text.index("\n## ", start + 1)]
    flat = " ".join(section.split())
    for term, meaning in docgen.GLOSSARY:
        assert f"- **{term}** — {' '.join(meaning.split())}" in flat, term
