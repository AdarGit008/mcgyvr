export function skipTake(
  entries: string[],
  take: number,
  skip: number,
): string[] {
  const kept: string[] = [];
  let i = 0;
  while (i < entries.length && take > 0) {
    for (let j = 0; j < take && i + j < entries.length; j += 1) {
      kept.push(entries[i + j]);
    }
    i += take + skip;
  }
  return kept;
}
