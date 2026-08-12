export function turnTail(entries: string[], count: number): string[] {
  const out: string[] = [];
  const from = entries.length - count;
  const start = from < 0 ? 0 : from;
  for (let i = 0; i < start; i += 1) {
    out.push(entries[i]);
  }
  for (let i = entries.length - 1; i >= start; i -= 1) {
    out.push(entries[i]);
  }
  return out;
}
