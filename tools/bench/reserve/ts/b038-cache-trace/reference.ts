/**
 * Replay a request trace against a bounded key cache with
 * least-recently-used eviction, recording hits, misses, removals and
 * evictions along with the final residency, most recently used first,
 * the hottest key and the peak residency.
 */
export function traceCache(
  capacity: number,
  requests: [string, string][],
): {
  hits: number;
  misses: number;
  dropped: number;
  evictions: string[];
  contents: string[];
  hotKey: string | null;
  peak: number;
} {
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  if (!Array.isArray(requests)) {
    throw new Error("requests must be a list");
  }
  const contents: string[] = []; // most recently used first
  const evictions: string[] = [];
  const hitCounts = new Map<string, number>();
  let hits = 0;
  let misses = 0;
  let dropped = 0;
  let peak = 0;
  for (const request of requests) {
    if (!Array.isArray(request) || request.length !== 2) {
      throw new Error("each trace entry is an [operation, key] pair");
    }
    const [op, key] = request;
    if (op !== "get" && op !== "put" && op !== "del") {
      throw new Error("operation must be get, put or del");
    }
    if (typeof key !== "string" || key === "") {
      throw new Error("key must be a non-empty string");
    }
    const at = contents.indexOf(key);
    if (op === "get") {
      if (at === -1) {
        misses += 1;
      } else {
        hits += 1;
        hitCounts.set(key, (hitCounts.get(key) ?? 0) + 1);
        contents.splice(at, 1);
        contents.unshift(key);
      }
    } else if (op === "put") {
      if (at !== -1) {
        contents.splice(at, 1);
      }
      contents.unshift(key);
      if (contents.length > capacity) {
        const evicted = contents.pop() as string;
        evictions.push(evicted);
      }
    } else if (at !== -1) {
      // del: a resident key is removed; an absent one is a quiet no-op.
      contents.splice(at, 1);
      dropped += 1;
    }
    if (contents.length > peak) {
      peak = contents.length;
    }
  }
  let hotKey: string | null = null;
  let best = 0;
  for (const [key, count] of hitCounts) {
    if (hotKey === null || count > best || (count === best && key < hotKey)) {
      hotKey = key;
      best = count;
    }
  }
  return { hits, misses, dropped, evictions, contents, hotKey, peak };
}
