export function loadVans(parcels: number[]): number[] {
  if (parcels.length === 0) {
    throw new Error("no parcels");
  }
  for (const p of parcels) {
    if (!Number.isInteger(p) || p < 1) {
      throw new Error("weights must be positive integers");
    }
  }
  const order = parcels
    .map((weight, index) => ({ weight, index }))
    .sort((a, b) => b.weight - a.weight || a.index - b.index);
  let first = 0;
  let second = 0;
  for (const { weight } of order) {
    if (first <= second) {
      first += weight;
    } else {
      second += weight;
    }
  }
  return [first, second];
}
