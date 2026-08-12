export function partCheck(
  total: number,
  parts: number[],
  tolerance: number,
): boolean {
  let summed = 0;
  for (const part of parts) {
    summed += part;
  }
  return Math.abs(total - summed) <= tolerance;
}
