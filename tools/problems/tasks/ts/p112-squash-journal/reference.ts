export function squashJournal(
  ops: (string | number)[][]
): (string | number)[][] {
  const value = new Map<string, number>();
  const born = new Map<string, number>();

  const asKey = (raw: string | number): string => {
    if (typeof raw !== "string" || raw.length === 0) {
      throw new Error("key must be a non-empty string");
    }
    return raw;
  };

  ops.forEach((op, index) => {
    const kind = op[0];
    if (kind === "put") {
      const key = asKey(op[1]);
      const val = op[2];
      if (typeof val !== "number" || !Number.isInteger(val) || val <= 0) {
        throw new Error("value must be a positive integer");
      }
      value.set(key, val);
      born.set(key, index);
    } else if (kind === "del") {
      const key = asKey(op[1]);
      if (!value.has(key)) {
        throw new Error("cannot delete an absent key");
      }
      value.delete(key);
      born.delete(key);
    } else if (kind === "ren") {
      const src = asKey(op[1]);
      const dst = asKey(op[2]);
      const held = value.get(src);
      if (held === undefined) {
        throw new Error("cannot rename an absent key");
      }
      if (value.has(dst)) {
        throw new Error("cannot rename onto an existing key");
      }
      value.set(dst, held);
      born.set(dst, born.get(src) ?? 0);
      value.delete(src);
      born.delete(src);
    } else {
      throw new Error("unknown operation");
    }
  });

  return [...value.keys()]
    .sort((a, b) => (born.get(a) ?? 0) - (born.get(b) ?? 0))
    .map((key) => ["put", key, value.get(key) ?? 0]);
}
