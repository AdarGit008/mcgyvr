export function powerOf(base: number, power: number): number {
  if (power < 0) {
    throw new Error("a power cannot fall below nothing");
  }
  let total = 1;
  for (let i = 0; i < power; i += 1) {
    total *= base;
  }
  return total;
}
