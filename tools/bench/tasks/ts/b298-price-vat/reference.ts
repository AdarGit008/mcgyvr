/** A net price with a whole-percent tax added, in whole pence. */
export function grossPrice(net: number, rate: number): number {
  return net + Math.floor((net * rate) / 100);
}
