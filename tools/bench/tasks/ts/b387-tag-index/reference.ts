export function tagsOf(line: unknown): string[] {
  if (typeof line !== "string") {
    throw new Error("a line must be text");
  }
  return line
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag !== "");
}

export function tagIndex(lines: string[]): Record<string, string[]> {
  const index: Record<string, string[]> = {};
  for (const line of lines) {
    for (const tag of tagsOf(line)) {
      if (!(tag in index)) {
        index[tag] = [];
      }
      index[tag].push(line);
    }
  }
  return index;
}
