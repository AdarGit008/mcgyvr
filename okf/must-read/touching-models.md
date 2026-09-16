# touching-models

Choosing, comparing, quantising or deleting a checkpoint on disk.

## The filename is not evidence. Sum the tensor table.

**A GGUF header carries the truth and costs nothing to read.** The header scan
reads headers only — never weights — and returns params, layer count, expert
count, top-k, KV head layout, per-type byte totals and the expert / non-expert
split for every file on a rig in seconds. Do it before you plan around a file.

**Labels lie, and the lies change decisions.** Checkpoints here have been found
whose filename states one quantisation while the header states a far larger one,
and whose name implied a mixture-of-experts model where the header declares no
experts at all. One was scheduled for deletion on the strength of its label; the
other was ranked the top offload candidate when `--n-cpu-moe` is a **no-op** on a
dense model. Both were caught by a header scan, without running anything.

**Bits-per-weight computed from file size over parameter count is a guess.** Two
defensible estimates of one file's expert bytes disagreed by double digits and
both were wrong. Watch the type map in particular — a reader missing a newer
type falls back to the widest one and can overstate a file several-fold.

## Identical geometry is not identical weights

**Two checkpoints can agree on every structural field and still be different
models.** A community fine-tune inherits its base model's architecture exactly
and is usually quantised by the same pipeline at the same settings, so file
size, layer count, expert bytes, quant mix — even a byte-identical tail — can
all match while the weights, the entire point of the fine-tune, differ.
Everything short of a full hash has said "duplicate" here and been wrong.

**Never delete a checkpoint as a duplicate on anything less than a full
hash.** Matching size is a reason to hash, not a verdict. Genuine
one-file-stored-twice duplicates do exist on these rigs; hash those too before
deleting either copy.

## Sparsity, not size, sets decode speed

**Bytes read per token is expert bytes times top-k over expert count, and it is
nearly independent of total parameters.** A very large, very sparse model reads
*fewer* bytes per token than a much smaller model with denser routing, despite
being several times the file. **Ranking checkpoints by size predicts speed
backwards** — one of the smallest files here is among the slowest to decode.

**KV cost is set by the layers that cache, not by the layer count.** Some
architectures cache on an interval; some declare the head count as a per-layer
array with only a handful of attention layers among many. Cheap KV is VRAM you
get to spend on experts, so it compounds with sparsity.
→ `okf/must-read/touching-rigs.md`

## Housekeeping

**A rename is applied on both rigs, or it has not happened.** Check that no live
config references the old name before renaming. A pre-rename name surviving
inside a historical record is correct and is left alone.

**Files sort by what the header declares, not by what the name implies** —
anything with experts under the MoE path, anything without under the dense one.
Audit by tensor table, not by directory listing.
