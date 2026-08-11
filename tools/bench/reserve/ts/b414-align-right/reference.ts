export function widestOf(entries: string[]): number {
  let widest = 0;
  for (const entry of entries) {
    if (entry.length > widest) {
      widest = entry.length;
    }
  }
  return widest;
}

export function alignRight(entries: string[]): string[] {
  const width = widestOf(entries);
  const out: string[] = [];
  for (const entry of entries) {
    out.push(" ".repeat(width - entry.length) + entry);
  }
  return out;
}
