/** How many of a store's values reach a floor. */
export function overCount(
  store: Record<string, number>,
  floor: number,
): number {
  let found = 0;
  for (const key of Object.keys(store)) {
    if (store[key] >= floor) {
      found += 1;
    }
  }
  return found;
}
