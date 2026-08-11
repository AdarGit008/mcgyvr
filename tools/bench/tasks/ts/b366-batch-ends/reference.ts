/** The position of the last entry of each full batch. */
export function batchEnds(count: number, size: number): number[] {
  const ends: number[] = [];
  for (let start = 0; start + size <= count; start += size) {
    ends.push(start + size - 1);
  }
  return ends;
}
