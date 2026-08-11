export function runIndex(
  entries: string[],
  value: string,
  nth: number,
): number {
  if (nth <= 0) {
    throw new Error("nth must be positive");
  }
  let seen = 0;
  for (let i = 0; i < entries.length; i += 1) {
    if (entries[i] === value) {
      seen += 1;
      if (seen === nth) {
        return i;
      }
    }
  }
  return -1;
}
