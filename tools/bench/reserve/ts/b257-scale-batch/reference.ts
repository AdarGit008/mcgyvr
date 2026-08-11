export function scaleBatch(amounts: number[], factor: number): number[] {
  if (factor < 0) {
    throw new Error("factor cannot be negative");
  }
  const scaled: number[] = [];
  for (const amount of amounts) {
    scaled.push(Math.ceil(amount * factor));
  }
  return scaled;
}
