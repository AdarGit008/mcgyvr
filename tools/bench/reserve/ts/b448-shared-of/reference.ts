export function inBoth(
  entry: string,
  left: string[],
  right: string[],
): boolean {
  return left.includes(entry) && right.includes(entry);
}

export function sharedOf(left: string[], right: string[]): string[] {
  const shared: string[] = [];
  for (const entry of left) {
    if (inBoth(entry, left, right) && !shared.includes(entry)) {
      shared.push(entry);
    }
  }
  return shared;
}
