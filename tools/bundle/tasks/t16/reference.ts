const MODULUS = 1000000007;

/** The nth Fibonacci number, modulo 1000000007. */
export function fibMod(n: number): number {
  if (!Number.isInteger(n) || n < 0) {
    throw new Error(`n must be a non-negative integer, got ${n}`);
  }
  let previous = 0;
  let current = 1;
  for (let index = 0; index < n; index += 1) {
    const next = (previous + current) % MODULUS;
    previous = current;
    current = next;
  }
  return previous;
}
