export function lowOf(pair: number[]): number {
  return pair[0] < pair[1] ? pair[0] : pair[1];
}

/** The pairs in order by their smaller number. */
export function orderPairs(pairs: number[][]): number[][] {
  const ordered = [...pairs];
  ordered.sort((a, b) => lowOf(a) - lowOf(b));
  return ordered;
}
