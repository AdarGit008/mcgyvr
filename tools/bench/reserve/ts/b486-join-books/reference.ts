export function joinBooks(
  first: Record<string, number>,
  second: Record<string, number>,
): Record<string, number> {
  const joined: Record<string, number> = {};
  for (const name of Object.keys(first)) {
    joined[name] = first[name];
  }
  for (const name of Object.keys(second)) {
    if (name in joined && joined[name] !== second[name]) {
      throw new Error("the two books disagree on " + name);
    }
    joined[name] = second[name];
  }
  return joined;
}
