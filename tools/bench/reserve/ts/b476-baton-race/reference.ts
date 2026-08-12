export function batonRace(legs: number[], handover: number): number {
  if (legs.length === 0) {
    return 0;
  }
  let total = 0;
  for (const leg of legs) {
    total += leg;
  }
  return total + handover * (legs.length - 1);
}
