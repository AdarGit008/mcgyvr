export function rankCandidates(
  candidates: string[],
  query: string,
  limit: number,
): string[] {
  if (typeof query !== "string" || query.length === 0) {
    throw new Error("query must be a non-empty string");
  }
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("limit must be a positive integer");
  }
  if (!Array.isArray(candidates) || candidates.some((c) => typeof c !== "string")) {
    throw new Error("candidates must be a list of strings");
  }
  const needle = query.toLowerCase();
  const scored: { tier: number; len: number; pos: number; text: string }[] = [];
  candidates.forEach((text, pos) => {
    const hay = text.toLowerCase();
    let tier = 0;
    if (hay === needle) {
      tier = 3;
    } else if (hay.startsWith(needle)) {
      tier = 2;
    } else if (hay.includes(needle)) {
      tier = 1;
    }
    if (tier > 0) {
      scored.push({ tier, len: text.length, pos, text });
    }
  });
  scored.sort((a, b) => b.tier - a.tier || a.len - b.len || a.pos - b.pos);
  return scored.slice(0, limit).map((s) => s.text);
}
