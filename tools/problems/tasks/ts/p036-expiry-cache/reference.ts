export function expiryCache(capacity: number, ops: (string | number)[][]): number[] {
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  const store = new Map<string, { value: number; expiry: number }>();
  const results: number[] = [];
  let lastTime: number | null = null;

  const clock = (time: number): number => {
    if (lastTime !== null && time < lastTime) {
      throw new Error("time goes backwards");
    }
    lastTime = time;
    return time;
  };

  for (const op of ops) {
    const kind = op[0];
    if (kind === "set") {
      const time = clock(op[1] as number);
      const key = op[2] as string;
      const value = op[3] as number;
      const ttl = op[4] as number;
      if (!Number.isInteger(ttl) || ttl < 1) {
        throw new Error("ttl must be a positive integer");
      }
      const held = store.get(key);
      if (held !== undefined && held.expiry > time) {
        store.set(key, { value, expiry: time + ttl });
        continue;
      }
      for (const [k, entry] of [...store]) {
        if (entry.expiry <= time) {
          store.delete(k);
        }
      }
      if (store.size >= capacity) {
        let victim: string | null = null;
        for (const [k, entry] of store) {
          if (victim === null) {
            victim = k;
            continue;
          }
          const best = store.get(victim)!;
          if (entry.expiry < best.expiry || (entry.expiry === best.expiry && k < victim)) {
            victim = k;
          }
        }
        if (victim !== null) {
          store.delete(victim);
        }
      }
      store.set(key, { value, expiry: time + ttl });
    } else if (kind === "get") {
      const time = clock(op[1] as number);
      const key = op[2] as string;
      const held = store.get(key);
      results.push(held !== undefined && held.expiry > time ? held.value : -1);
    } else {
      throw new Error(`unknown operation ${String(kind)}`);
    }
  }
  return results;
}
