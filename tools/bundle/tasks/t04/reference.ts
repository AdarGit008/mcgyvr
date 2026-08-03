/** A fixed-capacity cache that evicts its least recently used entry. */
export class LruCache<K, V> {
  readonly #capacity: number;
  readonly #entries = new Map<K, V>();

  constructor(capacity: number) {
    if (!Number.isInteger(capacity) || capacity < 1) {
      throw new Error(`capacity must be a positive integer, got ${capacity}`);
    }
    this.#capacity = capacity;
  }

  /** The value for key, or undefined; a hit becomes the most recent use. */
  get(key: K): V | undefined {
    if (!this.#entries.has(key)) {
      return undefined;
    }
    const value = this.#entries.get(key) as V;
    this.#entries.delete(key);
    this.#entries.set(key, value);
    return value;
  }

  /** Insert or update key, evicting the least recently used entry if full. */
  set(key: K, value: V): void {
    this.#entries.delete(key);
    this.#entries.set(key, value);
    if (this.#entries.size > this.#capacity) {
      const oldest = this.#entries.keys().next().value as K;
      this.#entries.delete(oldest);
    }
  }

  /** How many entries the cache currently holds. */
  get size(): number {
    return this.#entries.size;
  }
}
