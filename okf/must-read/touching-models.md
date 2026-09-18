# touching-models

Choosing, comparing, quantising or deleting a checkpoint on disk.

## The filename is not evidence. Sum the tensor table.

**A GGUF header carries the truth and costs nothing to read.**
`python -m mcgyvr.serving.ggufscan <gguf>` reads headers only — never weights —
and returns params, layer count, expert count, top-k, KV head layout, per-type
byte totals and the expert / non-expert split. Do it before you plan around a
file.

**Labels lie, and the lies change decisions.** A filename can state one
quantisation while the header states a far larger one, and a name can imply a
mixture-of-experts model where the header declares no experts at all. Never
schedule a deletion or pick
an offload candidate on a label; a header scan settles both without running
anything.

**Bits-per-weight computed from file size over parameter count is a guess.**
Sum the tensor table instead. Watch the type map in particular — a reader
missing a newer ggml type falls back to the widest one and can overstate a file
several-fold.

**For a safetensors checkpoint, read `config.json` → `quantization_config`**
(bits, group size, `desc_act`, `sym`) and record it on the config row. Do not
look only for `quantize_config.json` — a repo need not ship one, and a check on
that file alone reports the right checkpoint as missing its quantisation.

**Table figures are decimal GB; sizing code is GiB.** Convert where a
capability-table figure crosses into a fit, and nowhere else.

## Identical geometry is not identical weights

**Two checkpoints can agree on every structural field and still be different
models.** A community fine-tune inherits its base model's architecture exactly
and is usually quantised by the same pipeline at the same settings, so file
size, layer count, expert bytes, quant mix — even a byte-identical tail — can
all match while the weights, the entire point of the fine-tune, differ.

**Never delete a checkpoint as a duplicate on anything less than a full
hash.** Matching size is a reason to hash, not a verdict. Genuine
one-file-stored-twice duplicates exist; hash those too before deleting either
copy.

## Sparsity, not size, sets decode speed

**Bytes read per token is expert bytes times top-k over expert count, and it is
nearly independent of total parameters.** A very large, very sparse model reads
*fewer* bytes per token than a much smaller model with denser routing, despite
being several times the file. **Ranking checkpoints by size predicts speed
backwards.**

**KV cost is set by the layers that cache, not by the layer count.** Some
architectures cache on an interval; some declare the head count as a per-layer
array with only a handful of attention layers among many. Cheap KV is VRAM you
get to spend on experts, so it compounds with sparsity.
→ `okf/must-read/touching-rigs.md`

## Housekeeping

**A rename is applied on every rig, or it has not happened.** Check that no live
config references the old name before renaming. A pre-rename name surviving
inside a historical record is correct and is left alone.

**Files sort by what the header declares, not by what the name implies** —
anything with experts under the MoE path, anything without under the dense one.
Audit by tensor table, not by directory listing.
