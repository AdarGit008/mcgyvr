export function resolveProfile(
  profiles: Record<string, Record<string, unknown>>,
  wanted: string,
): Record<string, unknown> {
  const chain: string[] = [];
  const seen = new Set<string>();
  let current: string | undefined = wanted;
  while (current !== undefined) {
    if (!(current in profiles)) {
      throw new Error(`unknown profile ${current}`);
    }
    if (seen.has(current)) {
      throw new Error(`inheritance cycle at ${current}`);
    }
    seen.add(current);
    chain.push(current);
    current = profiles[current]["extends"] as string | undefined;
  }
  const resolved: Record<string, unknown> = {};
  for (let i = chain.length - 1; i >= 0; i--) {
    for (const [key, value] of Object.entries(profiles[chain[i]])) {
      if (key !== "extends") {
        resolved[key] = value;
      }
    }
  }
  return resolved;
}
