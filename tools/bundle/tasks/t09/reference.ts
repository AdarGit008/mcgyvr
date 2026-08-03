/** The factorial of n. */
export function factorial(n: number): number {
  if (!Number.isInteger(n) || n < 0) {
    throw new Error(`n must be a non-negative integer, got ${n}`);
  }
  if (n === 0) {
    return 1;
  }
  return n * factorial(n - 1);
}
