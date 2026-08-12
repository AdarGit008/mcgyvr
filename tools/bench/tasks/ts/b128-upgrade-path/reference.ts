/** Vet a device's proposed firmware upgrade path and report the final tag. */

function parseTag(value: unknown): [number, number] {
  if (typeof value !== "string") {
    throw new Error("a tag must be a string");
  }
  const parts = value.split(".");
  if (parts.length !== 2) {
    throw new Error(`a tag is line.point: ${value}`);
  }
  for (const part of parts) {
    if (part === "") {
      throw new Error(`empty tag part: ${value}`);
    }
    if (!/^\d+$/.test(part)) {
      throw new Error(`a tag part must be plain digits: ${value}`);
    }
    if (part.length > 1 && part.startsWith("0")) {
      throw new Error(`leading zero in a tag part: ${value}`);
    }
  }
  return [Number(parts[0]), Number(parts[1])];
}

function older(a: [number, number], b: [number, number]): boolean {
  if (a[0] !== b[0]) {
    return a[0] < b[0];
  }
  return a[1] < b[1];
}

export function vetUpgradePath(installed: string, steps: unknown): string {
  let carriedTag = installed;
  let carried = parseTag(installed);
  if (!Array.isArray(steps)) {
    throw new Error("steps must be a list");
  }
  for (const step of steps) {
    if (typeof step !== "object" || step === null || Array.isArray(step)) {
      throw new Error("a step must be an object with tag and requires");
    }
    const record = step as { tag?: unknown; requires?: unknown };
    const next = parseTag(record.tag);
    const floor = parseTag(record.requires);
    if (older(carried, floor)) {
      throw new Error(
        `step ${String(record.tag)} requires at least ${String(record.requires)}`,
      );
    }
    if (next[0] === carried[0] && next[1] === carried[1]) {
      throw new Error(`step ${String(record.tag)} repeats the carried tag`);
    }
    if (older(next, carried)) {
      throw new Error(
        `step ${String(record.tag)} is a downgrade from ${carriedTag}`,
      );
    }
    carriedTag = record.tag as string;
    carried = next;
  }
  return carriedTag;
}
