/** Total the hops a fleet makes climbing to the newest published release. */
export function fleetHops(count: number, lts: number[], builds: number[], hop: number): number {
  const newest = count - 1;
  let total = 0;
  for (const start of builds) {
    if (!Number.isInteger(start) || start < 0 || start > newest) {
      throw new Error("no such release");
    }
    let at = start;
    while (at < newest) {
      let landing = Math.min(at + hop, newest);
      for (const stop of lts) {
        if (stop > at && stop < landing) {
          landing = stop;
        }
      }
      at = landing;
      total += 1;
    }
  }
  return total;
}
