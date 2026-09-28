# always

Read at session start. Each is an owner ruling or has burned a session.

**The work is split across two repositories.** Owner ruling. The product repo
holds the product and what its code, tests and data read: measurements,
evidence, corpora and fleet locks. The lab repo holds research notes, plans,
session logs and superseded code, under the paths they would have here. A
citation spelled `mcgyvr-lab/<path>` is in the lab, and so is a cited
`archive/` or `records/plans/` path that is not on disk here.

**`archive/` and the lab are not read. Asked to, they are still not an
authority.**

**Superseded code is archived in the lab, never deleted.** The old module or
function goes to the lab under `archive/<its path here>`, with the tests that
exist only to call it. The lab commit lands first; the merge that supersedes the
code removes it and names that lab commit. Deleting drops the only record of
what the old code claimed. `archive/` here may keep only what code or tests
still read; anything else in it belongs in the lab.

**A run is expandable until its first measurement, and frozen from then on.**

**The rigs swap hardware. Never quote a stored spec — read it.**

**A "do not re-derive" label is not evidence.** Recompute every headline ratio
from the journals before quoting it.

**A claim with no artifact is not a finding.**

**Results are data points.** Owner ruling. A newer result does not invalidate an
older one, and setups are not ranked against each other. Record what a named
config did, under the conditions it did it.

**No prose is created without an explicit request.** Default to changing code,
tests and results. A finding goes in the commit message or an existing file.

**Bits-per-weight is a guess; the tensor table is not.**

**Say it about the config, not about the rig.** Owner ruling. "srv1 goes mapped"
is a fact about one machine on one afternoon and is worth nothing a week later;
"config `<tag>` places this host mapped" is reproducible, comparable and
falsifiable. Write the second. A number tied to a rig's name rots silently; a
number tied to a config tag is either still emitted by that tag or is not.
