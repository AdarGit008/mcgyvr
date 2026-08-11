export function dupeKeys(ids: string[]): string[] {
  const seen = new Set<string>();
  const repeated: string[] = [];
  for (const key of ids) {
    if (seen.has(key) && !repeated.includes(key)) {
      repeated.push(key);
    }
    seen.add(key);
  }
  return repeated;
}
