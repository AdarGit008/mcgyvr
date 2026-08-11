export function putOne(
  store: Record<string, string>,
  key: string,
  value: string,
): Record<string, string> {
  if (key === "") {
    throw new Error("a key must be named");
  }
  return { ...store, [key]: value };
}

/** Several keys set at once, the given store left untouched. */
export function putAll(
  store: Record<string, string>,
  pairs: string[][],
): Record<string, string> {
  let out = store;
  for (const pair of pairs) {
    out = putOne(out, pair[0], pair[1]);
  }
  return out;
}
