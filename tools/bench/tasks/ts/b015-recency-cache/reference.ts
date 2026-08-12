type CacheState = { limit: number; keys: string[]; store: Record<string, number> };

function checkKey(key: string): void {
  if (typeof key !== "string" || key.length === 0) {
    throw new Error("key must be a non-empty string");
  }
}

function touch(cache: CacheState, key: string): void {
  const at = cache.keys.indexOf(key);
  if (at !== -1) {
    cache.keys.splice(at, 1);
  }
  cache.keys.push(key);
}

export function newCache(limit: number): CacheState {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("limit must be a positive integer");
  }
  return { limit, keys: [], store: {} };
}

export function cacheWrite(
  cache: CacheState,
  key: string,
  value: number,
): string[] {
  checkKey(key);
  if (key in cache.store) {
    cache.store[key] = value;
    touch(cache, key);
    return [];
  }
  const spilled: string[] = [];
  if (cache.keys.length === cache.limit) {
    const oldest = cache.keys[0];
    cache.keys.shift();
    delete cache.store[oldest];
    spilled.push(oldest);
  }
  cache.store[key] = value;
  cache.keys.push(key);
  return spilled;
}

export function cacheRead(cache: CacheState, key: string): number {
  checkKey(key);
  if (!(key in cache.store)) {
    throw new Error("key not held: " + key);
  }
  touch(cache, key);
  return cache.store[key];
}
