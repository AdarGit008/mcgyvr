# Evidence prose, archived

Per the tree's rule that prose lives under `docs/archive/`, the narrative files
that used to sit beside each evidence directory were moved here on 2026-08-26,
preserving their directory names so a citation still resolves by folder:

    records/evidence/<dir>/README.md  ->  docs/archive/evidence-prose/<dir>/README.md

The data those files describe — `.jsonl` rows, cell definitions, launch logs,
drivers, manifests — stays under `records/evidence/`. Nothing was rewritten; only
internal path references were updated.

**Seven files did not move.** `records/evidence/ghostcall-2026-08-02/` and
`records/evidence/local-ai-2026-08-02/` are third-party source vendored as
evidence and hashed byte for byte in their `MANIFEST.json`. Relocating a file a
manifest pins would invalidate that pin, which is the one thing the manifest
exists to prevent, so those seven `.md` files stay where their hashes say they
are.

**`surface.md` did not move either.** It is a rendering of `surface.json` that
`tools/bench/serving/knobs.py build` regenerates and `tests/test_knobs.py`
byte-diffs. It is generated data wearing a `.md` extension, not prose.

**The provenance contract was taught the new location, not weakened.**
`tests/test_serving.py::test_every_serving_constant_names_the_run_behind_it`
requires every serving constant to name a run directory that carries a README --
that README is what makes the constant citable. It now accepts the README in
either place and still refuses a run that has none.

Some tool comments and test docstrings still cite the old
`records/evidence/**/README.md` paths as prose references. They are citations in
text, not file reads, so nothing breaks at runtime; they are worth a sweep.
