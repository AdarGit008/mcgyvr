export function addOne(
  tally: Record<string, number>,
  name: string,
  amount: number,
): Record<string, number> {
  return { ...tally, [name]: (tally[name] ?? 0) + amount };
}

export function mergeTally(
  left: Record<string, number>,
  right: Record<string, number>,
): Record<string, number> {
  let merged = { ...left };
  for (const name of Object.keys(right)) {
    merged = addOne(merged, name, right[name]);
  }
  return merged;
}
