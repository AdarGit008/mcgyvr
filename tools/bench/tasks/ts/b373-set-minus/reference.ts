export function setMinus(entries: string[], remove: string[]): string[] {
  const unwanted = new Set(remove);
  const kept: string[] = [];
  for (const entry of entries) {
    if (!unwanted.has(entry)) {
      kept.push(entry);
    }
  }
  return kept;
}
