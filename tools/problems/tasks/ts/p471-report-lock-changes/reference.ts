const SHAPE = /^(0|[1-9]\d*)(\.(0|[1-9]\d*))*(\+[0-9a-z]+(\.[0-9a-z]+)*)?$/;

type Entry = {
  version: string;
  groups: number[];
  source: string;
  needs: string[];
};

function mapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function read(record: unknown): Map<string, Entry> {
  if (!Array.isArray(record)) {
    throw new Error("a lock record is not a list");
  }
  const held = new Map<string, Entry>();
  for (const row of record) {
    if (!mapping(row)) {
      throw new Error("an entry is not a mapping");
    }
    if (Object.keys(row).sort().join(",") !== "name,needs,source,version") {
      throw new Error("an entry carries exactly name, version, source and needs");
    }
    const name = row["name"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("an entry's name is not a non-empty string");
    }
    if (held.has(name)) {
      throw new Error("two entries of one record share a name");
    }
    const version = row["version"];
    if (typeof version !== "string" || !SHAPE.test(version)) {
      throw new Error("a version is not written in the stated shape");
    }
    const source = row["source"];
    if (typeof source !== "string" || source.length === 0) {
      throw new Error("an entry's source is not a non-empty string");
    }
    const needs = row["needs"];
    if (!Array.isArray(needs)) {
      throw new Error("an entry's needs are not a list");
    }
    const wants: string[] = [];
    for (const want of needs) {
      if (typeof want !== "string" || want.length === 0) {
        throw new Error("a need is not a non-empty string");
      }
      if (wants.includes(want)) {
        throw new Error("an entry names one need twice");
      }
      wants.push(want);
    }
    const digits = version.split("+")[0];
    held.set(name, {
      version,
      groups: digits.split(".").map((part) => Number(part)),
      source,
      needs: wants,
    });
  }
  return held;
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

export function reportLockChanges(
  before: Record<string, unknown>[],
  after: Record<string, unknown>[],
): Record<string, Record<string, unknown>[]> {
  const was = read(before);
  const now = read(after);
  const added: Record<string, unknown>[] = [];
  const dropped: Record<string, unknown>[] = [];
  const lifted: Record<string, unknown>[] = [];
  const lowered: Record<string, unknown>[] = [];
  const rebuilt: Record<string, unknown>[] = [];
  const moved: Record<string, unknown>[] = [];
  const rewired: Record<string, unknown>[] = [];

  for (const name of [...new Set([...was.keys(), ...now.keys()])].sort()) {
    const old = was.get(name);
    const fresh = now.get(name);
    if (old === undefined && fresh !== undefined) {
      added.push({ name, version: fresh.version });
      continue;
    }
    if (fresh === undefined && old !== undefined) {
      dropped.push({ name, version: old.version });
      continue;
    }
    if (old === undefined || fresh === undefined) {
      continue;
    }
    const verdict = rank(old.groups, fresh.groups);
    if (verdict < 0) {
      lifted.push({ name, from: old.version, to: fresh.version });
      continue;
    }
    if (verdict > 0) {
      lowered.push({ name, from: old.version, to: fresh.version });
      continue;
    }
    if (old.version !== fresh.version) {
      rebuilt.push({ name, from: old.version, to: fresh.version });
    }
    if (old.source !== fresh.source) {
      moved.push({ name, from: old.source, to: fresh.source });
    }
    const gained = fresh.needs.filter((want) => !old.needs.includes(want)).sort();
    const lost = old.needs.filter((want) => !fresh.needs.includes(want)).sort();
    if (gained.length > 0 || lost.length > 0) {
      rewired.push({ name, gained, lost });
    }
  }
  return { added, dropped, lifted, lowered, rebuilt, moved, rewired };
}
