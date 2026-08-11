export function splitAt(entries: string[], marker: string): string[][] {
  for (let i = 0; i < entries.length; i += 1) {
    if (entries[i] === marker) {
      return [entries.slice(0, i), entries.slice(i + 1)];
    }
  }
  return [entries.slice(), []];
}
