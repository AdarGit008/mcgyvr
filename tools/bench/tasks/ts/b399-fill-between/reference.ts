export function fillBetween(entries: string[], filler: string): string[] {
  if (entries.length < 2) {
    return entries.slice();
  }
  const out = [entries[0]];
  for (const entry of entries.slice(1)) {
    out.push(filler);
    out.push(entry);
  }
  return out;
}
