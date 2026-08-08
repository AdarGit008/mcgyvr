type Slot = { size: number; links: number[]; cleanup: string | null };
type Sweep = { blocks: number[][]; reclaimed: number; cleanups: string[] };

export function sweepArenaBlocks(slots: Slot[], anchors: number[]): Sweep {
  if (!Array.isArray(slots)) {
    throw new Error("sweepArenaBlocks expects an arena list");
  }
  if (!Array.isArray(anchors)) {
    throw new Error("sweepArenaBlocks expects an anchors list");
  }
  const inArena = (value: unknown): boolean =>
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0 &&
    value < slots.length;
  for (const slot of slots) {
    if (slot === null || typeof slot !== "object") {
      throw new Error("every arena entry must be a slot");
    }
    if (!Number.isInteger(slot.size) || slot.size <= 0) {
      throw new Error("a slot size is a whole number above zero");
    }
    if (!Array.isArray(slot.links)) {
      throw new Error("a slot needs a links list");
    }
    if (slot.cleanup !== null && typeof slot.cleanup !== "string") {
      throw new Error("a cleanup is a name or null");
    }
    for (const link of slot.links) {
      if (!inArena(link)) {
        throw new Error("link names no slot of this arena: " + String(link));
      }
    }
  }
  const marked = new Set<number>();
  const queue: number[] = [];
  for (const anchor of anchors) {
    if (!inArena(anchor)) {
      throw new Error("anchor names no slot of this arena: " + String(anchor));
    }
    if (!marked.has(anchor)) {
      marked.add(anchor);
      queue.push(anchor);
    }
  }
  while (queue.length > 0) {
    const here = queue.shift();
    for (const link of slots[here].links) {
      if (!marked.has(link)) {
        marked.add(link);
        queue.push(link);
      }
    }
  }
  const blocks: number[][] = [];
  const cleanups: string[] = [];
  let reclaimed = 0;
  let open = -1;
  let bytes = 0;
  for (let at = 0; at < slots.length; at++) {
    if (marked.has(at)) {
      if (open >= 0) {
        blocks.push([open, bytes]);
        open = -1;
        bytes = 0;
      }
      continue;
    }
    if (open < 0) {
      open = at;
      bytes = 0;
    }
    bytes += slots[at].size;
    reclaimed += slots[at].size;
    if (slots[at].cleanup !== null) {
      cleanups.push(slots[at].cleanup);
    }
  }
  if (open >= 0) {
    blocks.push([open, bytes]);
  }
  return { blocks, reclaimed, cleanups };
}
