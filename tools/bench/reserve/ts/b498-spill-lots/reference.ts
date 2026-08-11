export function spillLots(lots: string[][]): string[] {
  const out: string[] = [];
  for (const lot of lots) {
    for (const entry of lot) {
      if (entry.length > 0) {
        out.push(entry);
      }
    }
  }
  return out;
}
