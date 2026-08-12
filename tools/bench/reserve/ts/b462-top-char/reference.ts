export function topChar(text: string): string {
  const counts: Record<string, number> = {};
  for (const ch of text) {
    counts[ch] = (counts[ch] ?? 0) + 1;
  }
  let best = "";
  for (const ch of text) {
    if (best === "" || counts[ch] > counts[best]) {
      best = ch;
    }
  }
  return best;
}
