export function bracketSeedOrder(count: number): number[] {
  if (!Number.isInteger(count) || count < 2 || (count & (count - 1)) !== 0) {
    throw new Error("count must be a power of two, at least 2");
  }
  let sheet = [1];
  let size = 1;
  while (size < count) {
    size *= 2;
    const grown: number[] = [];
    for (const seed of sheet) {
      grown.push(seed, size + 1 - seed);
    }
    sheet = grown;
  }
  return sheet;
}
