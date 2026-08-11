export function halfSplit(entries: string[]): string[][] {
  const cut = Math.ceil(entries.length / 2);
  return [entries.slice(0, cut), entries.slice(cut)];
}
