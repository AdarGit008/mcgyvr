export function spliceShifts(sheets: number[][]): number[] {
  const seen = new Set<number>();
  for (const sheet of sheets) {
    for (const badge of sheet) {
      seen.add(badge);
    }
  }
  return [...seen].sort((a, b) => a - b);
}
