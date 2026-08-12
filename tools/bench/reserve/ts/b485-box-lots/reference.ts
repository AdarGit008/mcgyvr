export function boxLots(entries: string[], size: number): string[][] {
  const packed: string[][] = [];
  let lot: string[] = [];
  for (const entry of entries) {
    lot.push(entry);
    if (lot.length === size) {
      packed.push(lot);
      lot = [];
    }
  }
  if (lot.length > 0) {
    packed.push(lot);
  }
  return packed;
}
