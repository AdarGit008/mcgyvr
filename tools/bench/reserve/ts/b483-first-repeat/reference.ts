export function firstRepeat(entries: string[]): string {
  const seen = new Set<string>();
  for (const entry of entries) {
    if (seen.has(entry)) {
      return entry;
    }
    seen.add(entry);
  }
  return "";
}
