export function sealOf(note: string, prev: number): number {
  let value = prev;
  for (const ch of note) {
    value = (value * 31 + ch.charCodeAt(0)) % 9973;
  }
  return value;
}

export function auditChain(
  records: { seq: number; note: string; seal: number }[],
): number[] {
  if (!Array.isArray(records)) {
    throw new Error("auditChain expects a list of records");
  }
  const bad: number[] = [];
  let prev = 0;
  for (let i = 0; i < records.length; i++) {
    const record = records[i];
    if (typeof record !== "object" || record === null || Array.isArray(record)) {
      throw new Error("each record is a mapping");
    }
    const { seq, note, seal } = record;
    if (seq === undefined || note === undefined || seal === undefined) {
      throw new Error("a record carries seq, note and seal");
    }
    if (typeof note !== "string") {
      throw new Error("note must be a string");
    }
    if (!Number.isInteger(seal)) {
      throw new Error("seal must be an integer");
    }
    if (seq !== i + 1) {
      throw new Error("seq must count upward from 1");
    }
    if (sealOf(note, prev) !== seal) {
      bad.push(seq);
    }
    prev = seal;
  }
  return bad;
}
