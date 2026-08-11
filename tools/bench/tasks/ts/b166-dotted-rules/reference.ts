export function matchSetting(rules: Record<string, string>, name: string): string | null {
  if (typeof name !== "string" || name === "" || name.includes("*")) {
    throw new Error("name must be a star-free non-empty string");
  }
  let exact: string | null = null;
  let best: string | null = null;
  let bestLength = -1;
  for (const [selector, value] of Object.entries(rules)) {
    if (typeof value !== "string") throw new Error("every rule value must be a string");
    const wildcard = selector === "*" || selector.endsWith(".*");
    if (selector.includes("*") && (!wildcard || selector.indexOf("*") < selector.length - 1)) {
      throw new Error("a star may only stand alone or end a selector");
    }
    if (selector === name) exact = value;
    if (wildcard && name.startsWith(selector.slice(0, -1)) && selector.length > bestLength) {
      [best, bestLength] = [value, selector.length];
    }
  }
  return exact ?? best;
}
