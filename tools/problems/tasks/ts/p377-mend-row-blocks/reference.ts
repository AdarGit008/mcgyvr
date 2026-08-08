function readRows(value: unknown, what: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error("the " + what + " must be a list of strings");
  }
  for (const row of value) {
    if (typeof row !== "string") {
      throw new Error("the " + what + " must be a list of strings");
    }
  }
  return value as string[];
}

export function mendRowBlocks(
  rows: string[],
  blocks: Array<Record<string, unknown>>,
): Record<string, unknown> {
  const sheet = readRows(rows, "sheet");
  if (!Array.isArray(blocks)) {
    throw new Error("the blocks must be a list");
  }
  const parsed: Array<{ start: number; drop: number; insert: string[]; guard: string | null }> = [];
  for (const raw of blocks) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      throw new Error("every block must be a mapping");
    }
    const block = raw as Record<string, unknown>;
    const start = block.start;
    if (typeof start !== "number" || !Number.isInteger(start) || start < 1) {
      throw new Error("start must be a whole number of one or more");
    }
    const drop = block.drop;
    if (typeof drop !== "number" || !Number.isInteger(drop) || drop < 0) {
      throw new Error("drop must be a whole number of none or more");
    }
    const held = block.guard;
    if (held !== null && held !== undefined && typeof held !== "string") {
      throw new Error("guard must be a string or null");
    }
    parsed.push({
      start,
      drop,
      insert: readRows(block.insert, "insert"),
      guard: typeof held === "string" ? held : null,
    });
  }
  for (let i = 1; i < parsed.length; i++) {
    if (parsed[i].start <= parsed[i - 1].start) {
      throw new Error("the starts must climb strictly");
    }
    if (parsed[i - 1].start + parsed[i - 1].drop > parsed[i].start) {
      throw new Error("one block reaches into the next");
    }
  }

  const out = sheet.slice();
  const rejected: number[] = [];
  let shift = 0;
  for (let i = 0; i < parsed.length; i++) {
    const block = parsed[i];
    const at = block.start - 1;
    let refused = at > sheet.length || at + block.drop > sheet.length;
    if (!refused && block.guard !== null) {
      refused = sheet[at] !== block.guard;
    }
    if (refused) {
      rejected.push(i);
      continue;
    }
    out.splice(at + shift, block.drop, ...block.insert);
    shift += block.insert.length - block.drop;
  }
  return { rows: out, rejected };
}
