export function hasAll(
  store: Record<string, number>,
  needed: string[],
): boolean {
  for (const key of needed) {
    if (!(key in store)) {
      return false;
    }
  }
  return true;
}
