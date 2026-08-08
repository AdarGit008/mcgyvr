type Candidate = { key: string; size: number; hits: number };

function whole(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

export function preloadPicks(entries: unknown, room: unknown): string[] {
  if (!Array.isArray(entries)) {
    throw new Error("the candidate list must be a list");
  }
  if (!whole(room) || room < 0) {
    throw new Error("the room must be a non-negative whole number");
  }
  const keys = new Set<string>();
  const candidates: Candidate[] = [];
  for (const raw of entries) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a candidate must be a mapping");
    }
    const entry = raw as Record<string, unknown>;
    const key = entry.key;
    if (typeof key !== "string" || key.length === 0) {
      throw new Error("a key must be a non-empty string");
    }
    if (keys.has(key)) {
      throw new Error("two candidates share a key");
    }
    keys.add(key);
    const size = entry.size;
    const hits = entry.hits;
    if (!whole(size) || size < 1) {
      throw new Error("a size must be a positive whole number");
    }
    if (!whole(hits) || hits < 0) {
      throw new Error("hits must be a non-negative whole number");
    }
    candidates.push({ key, size, hits });
  }
  candidates.sort((left, right) => {
    if (left.hits !== right.hits) {
      return right.hits - left.hits;
    }
    if (left.size !== right.size) {
      return left.size - right.size;
    }
    return left.key < right.key ? -1 : left.key > right.key ? 1 : 0;
  });
  let free = room;
  const taken: string[] = [];
  for (const candidate of candidates) {
    if (candidate.size <= free) {
      free -= candidate.size;
      taken.push(candidate.key);
    }
  }
  return taken;
}
