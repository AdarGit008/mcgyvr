const SHAPE = /^(0|[1-9]\d*)(\.(0|[1-9]\d*))*$/;

function groups(name: string, raw: unknown): number[] {
  if (typeof raw !== "string" || !SHAPE.test(raw)) {
    throw new Error("a release is not written in the stated shape: " + name);
  }
  return raw.split(".").map((part) => Number(part));
}

function rank(left: number[], right: number[]): number {
  const reach = Math.max(left.length, right.length);
  for (let at = 0; at < reach; at++) {
    const here = at < left.length ? left[at] : 0;
    const there = at < right.length ? right[at] : 0;
    if (here !== there) {
      return here < there ? -1 : 1;
    }
  }
  return 0;
}

function read(book: unknown): Map<string, number[]> {
  if (typeof book !== "object" || book === null || Array.isArray(book)) {
    throw new Error("a lock record is not a mapping");
  }
  const held = new Map<string, number[]>();
  for (const [name, raw] of Object.entries(book)) {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a package name is not a non-empty string");
    }
    held.set(name, groups(name, raw));
  }
  return held;
}

export function summariseLockDiff(
  before: Record<string, string>,
  after: Record<string, string>,
): Record<string, string[]> {
  const was = read(before);
  const now = read(after);
  const added: string[] = [];
  const dropped: string[] = [];
  const lifted: string[] = [];
  const lowered: string[] = [];

  const every = [...new Set([...was.keys(), ...now.keys()])].sort();
  for (const name of every) {
    const old = was.get(name);
    const fresh = now.get(name);
    if (old === undefined) {
      added.push(name);
      continue;
    }
    if (fresh === undefined) {
      dropped.push(name);
      continue;
    }
    const verdict = rank(old, fresh);
    if (verdict < 0) {
      lifted.push(name);
    } else if (verdict > 0) {
      lowered.push(name);
    }
  }
  return { added, dropped, lifted, lowered };
}
