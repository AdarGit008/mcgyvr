/** Suffix LCS table, then greedy front-to-back smallest-character rebuild. */
export function lcs(a: string, b: string): string {
  const n = a.length;
  const m = b.length;
  const table: number[][] = [];
  for (let i = 0; i <= n; i++) table.push(new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? 1 + table[i + 1][j + 1]
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  let out = "";
  let i = 0;
  let j = 0;
  while (table[i][j] > 0) {
    let bestChar = "";
    let bestI = -1;
    let bestJ = -1;
    const seen: Set<string> = new Set();
    // The earliest occurrence of a character in each string maximizes the
    // remaining table value, so only the first occurrence needs checking.
    for (let x = i; x < n; x++) {
      const c = a[x];
      if (seen.has(c)) continue;
      seen.add(c);
      if (bestChar !== "" && c >= bestChar) continue;
      const y = b.indexOf(c, j);
      if (y === -1) continue;
      if (1 + table[x + 1][y + 1] === table[i][j]) {
        bestChar = c;
        bestI = x;
        bestJ = y;
      }
    }
    out += bestChar;
    i = bestI + 1;
    j = bestJ + 1;
  }
  return out;
}
