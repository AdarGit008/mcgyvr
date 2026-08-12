export function relaySplits(marks: number[]): number[] {
  const splits: number[] = [];
  let previous = 0;
  for (const mark of marks) {
    if (mark <= previous) {
      throw new Error("clock reading did not advance: " + String(mark));
    }
    splits.push(mark - previous);
    previous = mark;
  }
  return splits;
}
