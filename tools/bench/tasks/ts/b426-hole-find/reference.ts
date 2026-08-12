export function stepsOn(first: number, count: number): number[] {
  const wanted: number[] = [];
  for (let i = 0; i < count; i += 1) {
    wanted.push(first + i);
  }
  return wanted;
}

export function holeFind(
  seen: number[],
  first: number,
  count: number,
): number {
  for (const wanted of stepsOn(first, count)) {
    if (!seen.includes(wanted)) {
      return wanted;
    }
  }
  return 0;
}
