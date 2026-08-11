export function keyPath(
  store: Record<string, string>,
  head: string,
): string[] {
  const found: string[] = [];
  const lead = head + ".";
  for (const key of Object.keys(store)) {
    if (key.startsWith(lead)) {
      const rest = key.slice(lead.length);
      if (!rest.includes(".")) {
        found.push(rest);
      }
    }
  }
  return found;
}
