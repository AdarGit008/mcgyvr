export function halfLife(count: number, steps: number): number {
  let left = count;
  for (let i = 0; i < steps; i += 1) {
    left = Math.floor(left / 2);
  }
  return left;
}
