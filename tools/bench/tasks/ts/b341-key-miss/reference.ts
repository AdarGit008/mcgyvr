/** A mapping's value for a key, or a fallback when it is absent. */
export function lookUp(
  store: Record<string, string>,
  key: string,
  fallback: string,
): string {
  return key in store ? store[key] : fallback;
}
