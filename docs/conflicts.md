# Name conflicts in the code

A review found several places where one name means more than one thing. None is
a runtime bug today; each is a trap — a reader, or a future import, that picks
the wrong one gets a value that looks right and is not.

## Already fixed in this change

- **`config.py` and `contract.py` each had their own strict-YAML loader.** Two
  copies of the same "refuse duplicate keys" guard had drifted apart: config
  also refused a list used as a key, contract did not. Both now use one shared
  loader (`src/mcgyvr/strict_yaml.py`), with each schema's own error type
  injected.

## Still open (documented, not changed)

### `os_machine_id` means two different things

- `src/mcgyvr/scan.py` — `os_machine_id()` returns a **sha256[:16]** of
  `/etc/machine-id`: a stable id for a *machine record*.
- `src/mcgyvr/serving/gatelib.py` — `os_machine_id()` returns the **first 12
  characters** of `/etc/machine-id` (or the hostname): the *OS install* the
  door's fleet lease keys on.

Same name, two values. Fleet/lease identity and scan-record filing use
incompatible machine-identity schemes under one colliding name. (`scan.load_prior`
also shadows the function with a parameter of the same name.)

### `digest_of` is two different functions

- `src/mcgyvr/deliver.py` — `digest_of(content: str)` hashes a **string**; it is
  the identity of accepted bytes, and callers must not compute it twice.
- `src/mcgyvr/orchestrator/index.py` — `digest_of(raw: bytes)` is **BLAKE2b
  truncated to 128 bits**; it fingerprints files for the orchestrator cache.

Same name, different input type and algorithm. Both mean "content identity", but
a value minted by one is not comparable with the other.

### The verdict vocabulary is split and partly untyped

- `route.Verdict` — `passed` / `failed` / `declined`.
- `verify` — the strings `"accepted"` / `"rejected"`.
- `escalate.Outcome` — seven terminal words.
- `record.Attempt.verdict` — a raw `str`, not the enum, so the enum and the
  record can drift.

Four spellings of "what came of this run" that a reader has to reconcile.

### Generic names reused for different concepts

`Outcome`, `Verdict`, `Accepted`, `Plan`, `Machine`, `Proposal`, `Evidence`,
`Attempt`, `Entry`, `Gpu` and `Rung` each name two different classes in two
different modules (for example `scan.Gpu` carries `vram_gb: float` while
`detect.Gpu` carries `Vram{total_mib, used_mib, free_mib}` ints). The names are
fine as English; they collide as import targets.
