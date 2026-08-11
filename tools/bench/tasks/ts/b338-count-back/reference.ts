/** The numbers from a start down to one. */
export function countBack(start: number): number[] {
  const counted: number[] = [];
  for (let value = start; value >= 1; value -= 1) {
    counted.push(value);
  }
  return counted;
}
