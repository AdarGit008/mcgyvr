function walk(
  before: Record<string, any>,
  after: Record<string, any>,
  prefix: string,
  lines: string[]
): void {
  for (const key of Object.keys(after)) {
    const path = prefix === "" ? key : prefix + "/" + key;
    if (key in before) {
      walk(before[key], after[key], path, lines);
    } else {
      lines.push("added " + path);
    }
  }
  for (const key of Object.keys(before)) {
    if (!(key in after)) {
      const path = prefix === "" ? key : prefix + "/" + key;
      lines.push("removed " + path);
    }
  }
}

export function outlineDiff(
  before: Record<string, any>,
  after: Record<string, any>
): string[] {
  const lines: string[] = [];
  walk(before, after, "", lines);
  lines.sort();
  return lines;
}
