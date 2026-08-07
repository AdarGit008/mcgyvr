export function gaugeBuckets(
  pulses: number[],
  base: number,
  width: number,
  pockets: number,
): number[] {
  const tallies = new Array(pockets + 2).fill(0);
  const top = base + width * pockets;
  for (const pulse of pulses) {
    if (pulse < base) {
      tallies[0] += 1;
    } else if (pulse >= top) {
      tallies[pockets + 1] += 1;
    } else {
      tallies[1 + Math.floor((pulse - base) / width)] += 1;
    }
  }
  return tallies;
}
