/** A least-recently-used cache built on Map's insertion-order guarantee. */
export function createLruCache(capacity: number): {
  get: (key: string) => number | undefined;
  put: (key: string, value: number) => void;
  size: () => number;
} {
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  const entries = new Map<string, number>();
  return {
    get(key: string): number | undefined {
      if (!entries.has(key)) {
        return undefined;
      }
      const value = entries.get(key) as number;
      entries.delete(key);
      entries.set(key, value);
      return value;
    },
    put(key: string, value: number): void {
      if (entries.has(key)) {
        entries.delete(key);
      } else if (entries.size === capacity) {
        const oldest = entries.keys().next().value as string;
        entries.delete(oldest);
      }
      entries.set(key, value);
    },
    size(): number {
      return entries.size;
    },
  };
}
