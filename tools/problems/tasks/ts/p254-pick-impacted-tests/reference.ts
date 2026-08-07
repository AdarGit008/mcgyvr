export function pickImpactedTests(
  coverage: Record<string, string[]>,
  edited: string[],
): string[] {
  if (coverage === null || typeof coverage !== "object" || Array.isArray(coverage)) {
    throw new Error("the coverage table must be a table of test names");
  }
  if (!Array.isArray(edited)) {
    throw new Error("the edited paths must be a list");
  }
  for (const path of edited) {
    if (typeof path !== "string") {
      throw new Error("every edited path must be a string");
    }
  }
  const touched = new Set(edited);
  const picked: string[] = [];
  for (const [name, paths] of Object.entries(coverage)) {
    if (name === "") {
      throw new Error("a test name cannot be empty");
    }
    if (!Array.isArray(paths)) {
      throw new Error(`coverage for ${name} must be a list`);
    }
    if (paths.length === 0) {
      throw new Error(`coverage for ${name} is empty`);
    }
    const seen = new Set<string>();
    for (const path of paths) {
      if (typeof path !== "string") {
        throw new Error(`coverage for ${name} holds a non-string path`);
      }
      if (seen.has(path)) {
        throw new Error(`coverage for ${name} repeats ${path}`);
      }
      seen.add(path);
    }
    if (touched.size === 0) {
      continue;
    }
    const blanket = paths.length === 1 && paths[0] === "*";
    if (blanket || paths.some((path) => touched.has(path))) {
      picked.push(name);
    }
  }
  return picked.sort();
}
