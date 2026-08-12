export function sortByLen(words: string[]): string[] {
  const ordered = [...words];
  ordered.sort((a, b) =>
    a.length === b.length ? a.localeCompare(b) : a.length - b.length,
  );
  return ordered;
}
