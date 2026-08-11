export function meterDelta(
  before: number,
  after: number,
  ceiling: number,
): number {
  if (before >= ceiling || after >= ceiling) {
    throw new Error("reading is beyond the meter's ceiling");
  }
  return after >= before ? after - before : ceiling - before + after;
}
