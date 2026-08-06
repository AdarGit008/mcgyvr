/** Knuth-Morris-Pratt with overlap continuation after each match. */
export function findAll(text: string, pattern: string): number[] {
  if (pattern.length === 0) {
    throw new Error("pattern must be a non-empty string");
  }
  const m = pattern.length;
  const lps: number[] = new Array(m).fill(0);
  for (let i = 1, len = 0; i < m; ) {
    if (pattern[i] === pattern[len]) {
      len += 1;
      lps[i] = len;
      i += 1;
    } else if (len > 0) {
      len = lps[len - 1];
    } else {
      lps[i] = 0;
      i += 1;
    }
  }
  const out: number[] = [];
  let j = 0;
  for (let i = 0; i < text.length; i++) {
    while (j > 0 && text[i] !== pattern[j]) j = lps[j - 1];
    if (text[i] === pattern[j]) j += 1;
    if (j === m) {
      out.push(i - m + 1);
      j = lps[m - 1];
    }
  }
  return out;
}
