/** Levenshtein distance with a rolling one-row dynamic program. */
export function editDistance(a: string, b: string): number {
  if (typeof a !== "string" || typeof b !== "string") {
    throw new Error("both arguments must be strings");
  }
  const rows = a.length;
  const cols = b.length;
  let previous: number[] = Array.from({ length: cols + 1 }, (_, j) => j);
  for (let i = 1; i <= rows; i++) {
    const current: number[] = new Array(cols + 1);
    current[0] = i;
    for (let j = 1; j <= cols; j++) {
      if (a[i - 1] === b[j - 1]) {
        current[j] = previous[j - 1];
      } else {
        current[j] = 1 + Math.min(previous[j - 1], previous[j], current[j - 1]);
      }
    }
    previous = current;
  }
  return previous[cols];
}
