export function binRotate(entries: string[], places: number): string[] {
  if (entries.length === 0) {
    return [];
  }
  const shift = places % entries.length;
  const out: string[] = [];
  for (let i = 0; i < entries.length; i += 1) {
    out.push(entries[(i - shift + entries.length) % entries.length]);
  }
  return out;
}
