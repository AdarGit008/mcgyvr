export function dropOuter(entries: string[]): string[] {
  if (entries.length <= 2) {
    return [];
  }
  return entries.slice(1, -1);
}
