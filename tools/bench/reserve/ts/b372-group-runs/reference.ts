export function runOf(entries: string[], start: number): number {
  let length = 1;
  while (
    start + length < entries.length &&
    entries[start + length] === entries[start]
  ) {
    length += 1;
  }
  return length;
}

/** The list broken into runs of equal neighbouring values. */
export function groupRuns(entries: string[]): string[][] {
  const runs: string[][] = [];
  let i = 0;
  while (i < entries.length) {
    const length = runOf(entries, i);
    runs.push(entries.slice(i, i + length));
    i += length;
  }
  return runs;
}
