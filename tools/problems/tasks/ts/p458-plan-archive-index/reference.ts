type Slot = { name: string; offset: number; length: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planArchiveIndex(
  entries: any[],
  total: number,
): { fault: string; blame: string[]; order: string[]; gaps: number[][]; slack: number; used: number } {
  if (!Array.isArray(entries)) {
    throw new Error("entries must be a list");
  }
  if (!whole(total) || total < 0) {
    throw new Error("total must be a whole number of nought or more");
  }
  const named = new Set<string>();
  const slots: Slot[] = [];
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 3) {
      throw new Error("an entry is a [name, offset, length] triple");
    }
    const [name, offset, length] = entry;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (named.has(name)) {
      throw new Error(`two entries carry the name ${name}`);
    }
    named.add(name);
    if (!whole(offset) || offset < 0) {
      throw new Error("an offset must be a whole number of nought or more");
    }
    if (!whole(length) || length < 0) {
      throw new Error("a length must be a whole number of nought or more");
    }
    slots.push({ name, offset, length });
  }

  slots.sort((a, b) => {
    if (a.offset !== b.offset) return a.offset - b.offset;
    if (a.length !== b.length) return a.length - b.length;
    return a.name < b.name ? -1 : 1;
  });
  const order = slots.map((slot) => slot.name);

  for (const slot of slots) {
    if (slot.offset + slot.length > total) {
      return { fault: "truncated", blame: [slot.name], order, gaps: [], slack: 0, used: 0 };
    }
  }

  const held = slots.filter((slot) => slot.length > 0);
  for (let i = 1; i < held.length; i++) {
    if (held[i - 1].offset + held[i - 1].length > held[i].offset) {
      return {
        fault: "overlap",
        blame: [held[i - 1].name, held[i].name],
        order,
        gaps: [],
        slack: 0,
        used: 0,
      };
    }
  }

  const gaps: number[][] = [];
  let cursor = 0;
  let used = 0;
  for (const slot of held) {
    if (slot.offset > cursor) {
      gaps.push([cursor, slot.offset - cursor]);
    }
    cursor = slot.offset + slot.length;
    used += slot.length;
  }
  return { fault: "", blame: [], order, gaps, slack: total - cursor, used };
}
