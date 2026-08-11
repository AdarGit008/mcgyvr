function matchesPattern(item: string, pattern: string): boolean {
  const star = pattern.indexOf("*");
  if (star === -1) {
    return item === pattern;
  }
  const head = pattern.slice(0, star);
  const tail = pattern.slice(star + 1);
  if (item.length < head.length + tail.length) {
    return false;
  }
  return item.startsWith(head) && item.endsWith(tail);
}

export function assignBins(
  rules: [string, string[]][],
  items: string[],
): { bins: Record<string, string[]>; leftover: string[] } {
  if (!Array.isArray(rules)) {
    throw new Error("rules must be a list");
  }
  const bins: Record<string, string[]> = {};
  for (const rule of rules) {
    if (!Array.isArray(rule) || rule.length !== 2) {
      throw new Error("a rule is a [name, patterns] pair");
    }
    const [name, patterns] = rule;
    if (typeof name !== "string" || name === "") {
      throw new Error("rule names must be non-empty strings");
    }
    if (Object.hasOwn(bins, name)) {
      throw new Error("rule names must not repeat");
    }
    if (!Array.isArray(patterns) || patterns.length === 0) {
      throw new Error("patterns must be a non-empty list");
    }
    for (const pattern of patterns) {
      if (typeof pattern !== "string" || pattern === "") {
        throw new Error("patterns must be non-empty strings");
      }
      if (pattern.indexOf("*") !== pattern.lastIndexOf("*")) {
        throw new Error("a pattern holds at most one star");
      }
    }
    bins[name] = [];
  }
  if (!Array.isArray(items) || items.some((item) => typeof item !== "string")) {
    throw new Error("items must be a list of strings");
  }
  const leftover: string[] = [];
  for (const item of items) {
    const hit = rules.find((rule) => rule[1].some((p) => matchesPattern(item, p)));
    (hit ? bins[hit[0]] : leftover).push(item);
  }
  return { bins, leftover };
}
