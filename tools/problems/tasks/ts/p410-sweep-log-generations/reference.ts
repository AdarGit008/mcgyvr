function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function sweepLogGenerations(
  base: string,
  files: { name: string; bytes: number; days: number }[],
  rules: { rotateAt: number; keep: number; maxDays: number },
): { kept: string[]; rotated: string[][]; deleted: string[] } {
  if (typeof base !== "string" || base.length === 0) {
    throw new Error("the live name must be a non-empty string");
  }
  if (!Array.isArray(files)) {
    throw new Error("the files must be a list");
  }
  if (!isRecord(rules)) {
    throw new Error("the rules must be a record");
  }
  const rotateAt = rules.rotateAt;
  const keep = rules.keep;
  const maxDays = rules.maxDays;
  for (const setting of [rotateAt, keep, maxDays]) {
    if (!Number.isInteger(setting) || setting < 1) {
      throw new Error("each rule must be a whole number above nothing");
    }
  }
  const seen = new Set<string>();
  const copies = new Map<number, number>();
  let liveBytes = -1;
  let liveDays = -1;
  for (const file of files) {
    if (!isRecord(file)) {
      throw new Error("a file must be a record");
    }
    const name = file.name;
    if (typeof name !== "string") {
      throw new Error("a name must be a string");
    }
    if (seen.has(name)) {
      throw new Error("name " + name + " appears twice");
    }
    seen.add(name);
    const bytes = file.bytes;
    const days = file.days;
    if (!Number.isInteger(bytes) || bytes < 0) {
      throw new Error("bytes must be a whole number of nothing or more");
    }
    if (!Number.isInteger(days) || days < 0) {
      throw new Error("days must be a whole number of nothing or more");
    }
    if (name === base) {
      liveBytes = bytes;
      liveDays = days;
      continue;
    }
    if (!name.startsWith(base + ".")) {
      throw new Error("name " + name + " belongs to no generation here");
    }
    const suffix = name.slice(base.length + 1);
    if (!/^[1-9][0-9]*$/.test(suffix)) {
      throw new Error("copy number " + suffix + " is not written plainly");
    }
    copies.set(Number(suffix), days);
  }
  if (liveBytes < 0) {
    throw new Error("the live file is missing");
  }
  for (let number = 1; number <= copies.size; number++) {
    if (!copies.has(number)) {
      throw new Error("copy number " + number + " is missing");
    }
  }
  const rotated: string[][] = [];
  const placed = new Map<number, number>();
  if (liveBytes >= rotateAt) {
    placed.set(1, liveDays);
    rotated.push([base, base + ".1"]);
    for (let number = 1; number <= copies.size; number++) {
      placed.set(number + 1, copies.get(number));
      rotated.push([base + "." + number, base + "." + (number + 1)]);
    }
  } else {
    for (let number = 1; number <= copies.size; number++) {
      placed.set(number, copies.get(number));
    }
  }
  const kept = [base];
  const deleted: string[] = [];
  for (let number = 1; number <= placed.size; number++) {
    const name = base + "." + number;
    if (number > keep || placed.get(number) > maxDays) {
      deleted.push(name);
    } else {
      kept.push(name);
    }
  }
  return { kept, rotated, deleted };
}
