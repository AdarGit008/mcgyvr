type CacheEntry = { value: string; stored: number; ttl: number };

export function freshValue(entry: CacheEntry, now: number): string {
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    throw new Error("entry must be a cache record");
  }
  const { value, stored, ttl } = entry;
  if (typeof value !== "string") throw new Error("value must be a string");
  if (!Number.isInteger(stored) || stored < 0) throw new Error("stored must be a non-negative integer");
  if (!Number.isInteger(ttl) || ttl < 1) throw new Error("ttl must be a positive integer");
  if (!Number.isInteger(now) || now < stored) throw new Error("now must be an integer no earlier than stored");
  if (now >= stored + ttl) throw new Error("record is no longer usable at now");
  return value;
}
