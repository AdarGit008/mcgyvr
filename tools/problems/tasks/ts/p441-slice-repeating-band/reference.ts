type Cut = { motif: number; into: number; joins: number; runs: number };

function isWhole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function sliceRepeatingBand(
  motifs: number[],
  stripWidth: number,
  stripCount: number,
): Cut[] {
  if (!Array.isArray(motifs)) {
    throw new Error("the motifs are a list of lengths");
  }
  if (motifs.length === 0) {
    throw new Error("a run holds at least one motif");
  }
  const opens: number[] = [];
  let total = 0;
  for (const length of motifs) {
    if (!isWhole(length) || length < 1) {
      throw new Error("a motif length is a whole number of one or more");
    }
    opens.push(total);
    total += length;
  }
  if (!isWhole(stripWidth) || stripWidth < 1 || stripWidth > 1000) {
    throw new Error("stripWidth is a whole number from 1 through 1000");
  }
  if (!isWhole(stripCount) || stripCount < 0 || stripCount > 500) {
    throw new Error("stripCount is a whole number from 0 through 500");
  }

  const joinAt = new Set<number>(opens);
  const cuts: Cut[] = [];
  for (let strip = 0; strip < stripCount; strip++) {
    const left = strip * stripWidth;
    const offset = left % total;
    let motif = 0;
    for (let i = 0; i < opens.length; i++) {
      if (opens[i] <= offset) {
        motif = i;
      }
    }
    let joins = 0;
    for (let at = left + 1; at < left + stripWidth; at++) {
      if (joinAt.has(at % total)) {
        joins += 1;
      }
    }
    cuts.push({
      motif,
      into: offset - opens[motif],
      joins,
      runs: Math.floor(left / total),
    });
  }
  return cuts;
}
