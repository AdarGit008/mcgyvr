"""Facts about models that mcgyvr reads back instead of measuring again.

Every number here carries where it came from and the day it was read: a fact
stated by the Hub API or a file's header, an estimate the model card makes
about itself, or a reading taken on the user's own machine.

The package holds three modules and this one only marks the package:

- `record` is the schema — `ModelRecord`, `Number`, `Score`, `Weights`, the
  boards and sources numbers may name — plus `parse_document`/`dump_document`,
  which reject any document whose keys, kinds, sources or dates do not fit.
- `store` merges the catalog shipped in `mcgyvr/data` with the per-machine
  cache, a cached record winning over the shipped one for the same
  `(model_id, quant)`, and reports the files it could not read as `skipped`.
- `geometry` does the same for GGUF header rows keyed by weights
  `(repo, revision, file)`, and refuses a row whose `source` does not name the
  header of the file it is filed for.
"""
