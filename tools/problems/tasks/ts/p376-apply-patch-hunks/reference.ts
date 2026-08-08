function readLines(value: unknown, what: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error("the " + what + " must be a list of strings");
  }
  for (const line of value) {
    if (typeof line !== "string") {
      throw new Error("the " + what + " must be a list of strings");
    }
  }
  return value as string[];
}

export function applyPatchHunks(
  lines: string[],
  hunks: Array<Record<string, unknown>>,
): Record<string, unknown> {
  const file = readLines(lines, "file");
  if (!Array.isArray(hunks)) {
    throw new Error("the hunks must be a list");
  }
  const parsed: Array<{ at: number; before: string[]; after: string[] }> = [];
  for (const raw of hunks) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      throw new Error("every hunk must be a mapping");
    }
    const hunk = raw as Record<string, unknown>;
    const at = hunk.at;
    if (typeof at !== "number" || !Number.isInteger(at) || at < 1) {
      throw new Error("at must be a whole number of one or more");
    }
    parsed.push({
      at,
      before: readLines(hunk.before, "before"),
      after: readLines(hunk.after, "after"),
    });
  }
  for (let i = 1; i < parsed.length; i++) {
    if (parsed[i].at <= parsed[i - 1].at) {
      throw new Error("the ats must climb strictly");
    }
    if (parsed[i - 1].at + parsed[i - 1].before.length > parsed[i].at) {
      throw new Error("one hunk reaches into the next");
    }
  }

  const out: string[] = [];
  const conflicts: number[] = [];
  let cursor = 0;
  for (let i = 0; i < parsed.length; i++) {
    const hunk = parsed[i];
    const start = hunk.at - 1;
    const reach = start + hunk.before.length;
    let clashes = start > file.length || reach > file.length;
    if (!clashes) {
      for (let k = 0; k < hunk.before.length; k++) {
        if (file[start + k] !== hunk.before[k]) {
          clashes = true;
          break;
        }
      }
    }
    const stop = Math.min(start, file.length);
    while (cursor < stop) {
      out.push(file[cursor]);
      cursor += 1;
    }
    if (clashes) {
      conflicts.push(i);
      continue;
    }
    cursor = reach;
    for (const line of hunk.after) {
      out.push(line);
    }
  }
  while (cursor < file.length) {
    out.push(file[cursor]);
    cursor += 1;
  }
  return { lines: out, conflicts };
}
