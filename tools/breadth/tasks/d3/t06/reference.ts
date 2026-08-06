/** Sliding window with a deficit counter over required multiplicities. */
export function minWindow(s: string, t: string): string {
  if (t.length === 0) return "";
  const need: Map<string, number> = new Map();
  for (const c of t) need.set(c, (need.get(c) ?? 0) + 1);
  let missing = t.length;
  let bestLen = Infinity;
  let bestStart = 0;
  let left = 0;
  for (let right = 0; right < s.length; right++) {
    const c = s[right];
    const n = need.get(c);
    if (n !== undefined) {
      if (n > 0) missing -= 1;
      need.set(c, n - 1);
    }
    while (missing === 0) {
      if (right - left + 1 < bestLen) {
        bestLen = right - left + 1;
        bestStart = left;
      }
      const lc = s[left];
      const ln = need.get(lc);
      if (ln !== undefined) {
        need.set(lc, ln + 1);
        if (ln + 1 > 0) missing += 1;
      }
      left += 1;
    }
  }
  return bestLen === Infinity ? "" : s.slice(bestStart, bestStart + bestLen);
}
