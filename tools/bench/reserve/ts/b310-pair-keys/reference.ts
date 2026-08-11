export function pairKeys(
  names: string[],
  codes: string[],
): Record<string, string> {
  const paired: Record<string, string> = {};
  const shared = Math.min(names.length, codes.length);
  for (let i = 0; i < shared; i += 1) {
    paired[names[i]] = codes[i];
  }
  return paired;
}
