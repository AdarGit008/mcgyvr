/** a divided by b. */
export function safeDivide(a: number, b: number): number {
  for (const [name, value] of [["a", a], ["b", b]] as const) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error(`${name} must be a finite number, got ${String(value)}`);
    }
  }
  if (b === 0) {
    throw new Error("b must not be zero");
  }
  return a / b;
}
