export function tallyPageTerms(
  entries: string[],
  skips: string[],
): Record<string, number> {
  if (!Array.isArray(entries) || !Array.isArray(skips)) {
    throw new Error("entries and skips must both be lists");
  }
  const tally: Record<string, number> = {};
  for (const entry of entries) {
    if (typeof entry !== "string" || entry === "") {
      throw new Error("every entry must be a non-empty string");
    }
    let head = entry.toLowerCase();
    if (head.endsWith("s") && head.length > 4) {
      head = head.slice(0, head.length - 1);
    }
    if (skips.includes(head)) {
      continue;
    }
    tally[head] = (tally[head] ?? 0) + 1;
  }
  return tally;
}
