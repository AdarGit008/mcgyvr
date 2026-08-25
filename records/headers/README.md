# Run headers — what a run is *for*

One file per header, `<date>-<slug>.json`, record type `run-header/1`.
`run.json` records what a run **was**; these record what it is **for**: the
question, the arms, the rigs, the cost and its source, what else the run could
have carried, what was left on the table and why, the prerequisites, and what
would make it void.

- The spine is closed. `tools/bench/headers.py` holds `KEYS`; a key it does not
  name is refused, and prose goes under `notes` — free text does not aggregate.
- `unknown` is a value and carries provenance:
  `{"unknown": true, "searched": [...]}`. A field nobody can fill is a gap
  found at the moment someone tried to fill it. A bare `"unknown"` is refused.
- v1 requires four fields only: `record`, `id`, `declared`, `question`. Which of
  the rest become required is the review's decision, not a guess made now.

```
uv run --no-sync python tools/bench/headers.py list
```

prints one line per header and ends with the count toward the review. **At ten
headers carrying a `run` block, the field review is owed**: read them, promote
every field filled on all ten, drop every field filled on none, write
`run-header/2` to `tools/baseline/schema/record.run-header.schema.json`, and
append the decision to #330 with its date. Until that schema exists the listing
exits non-zero and says so — the owed state is code, not memory.

The gate that writes a header before a run starts is #322. #330 is the record
type, the home, the listing and the review point. Checks:
`tests/test_run_headers.py`.
