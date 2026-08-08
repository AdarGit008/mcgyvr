export function cappedCompositions(total: number, parts: number, lo: number, hi: number): number {
  if (!Number.isInteger(total)) {
    throw new Error("total must be an integer");
  }
  if (!Number.isInteger(parts) || parts < 1) {
    throw new Error("parts must be a positive integer");
  }
  if (!Number.isInteger(lo) || lo < 0 || !Number.isInteger(hi) || hi < 0) {
    throw new Error("bounds must be non-negative integers");
  }
  if (lo > hi) {
    throw new Error("lo must not exceed hi");
  }
  if (total < parts * lo || total > parts * hi) {
    return 0;
  }
  let ways = new Map<number, number>([[0, 1]]);
  for (let p = 0; p < parts; p++) {
    const grown = new Map<number, number>();
    for (const [sum, count] of ways) {
      for (let value = lo; value <= hi; value++) {
        const reached = sum + value;
        if (reached > total) {
          break;
        }
        grown.set(reached, (grown.get(reached) ?? 0) + count);
      }
    }
    ways = grown;
  }
  return ways.get(total) ?? 0;
}
