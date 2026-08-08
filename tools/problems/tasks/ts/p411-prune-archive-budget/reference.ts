type Archived = { label: string; size: number; age: number };

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function pruneArchiveBudget(
  files: { label: string; size: number; age: number }[],
  budget: number,
  limit: number,
  least: number,
): { removed: string[]; held: number; over: number; stale: number } {
  if (!Array.isArray(files)) {
    throw new Error("the archive must be a list of files");
  }
  if (!Number.isInteger(budget) || budget < 0) {
    throw new Error("the budget must be a whole number of nothing or more");
  }
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("the age limit must be a whole number above nothing");
  }
  if (!Number.isInteger(least) || least < 0) {
    throw new Error("the least number must be a whole number of nothing or more");
  }
  const seen = new Set<string>();
  let standing: Archived[] = [];
  for (const file of files) {
    if (!isRecord(file)) {
      throw new Error("a file must be a record");
    }
    const label = file.label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a label must be a non-empty string");
    }
    if (seen.has(label)) {
      throw new Error("label " + label + " appears twice");
    }
    seen.add(label);
    const size = file.size;
    const age = file.age;
    if (!Number.isInteger(size) || size < 0) {
      throw new Error("a size must be a whole number of nothing or more");
    }
    if (!Number.isInteger(age) || age < 0) {
      throw new Error("an age must be a whole number of nothing or more");
    }
    standing.push({ label, size, age });
  }
  const removed: string[] = [];
  for (;;) {
    if (standing.length <= least) {
      break;
    }
    let weight = 0;
    let stale = 0;
    for (const file of standing) {
      weight += file.size;
      if (file.age > limit) {
        stale += 1;
      }
    }
    if (stale === 0 && weight <= budget) {
      break;
    }
    let doomed = standing[0];
    for (const file of standing) {
      if (
        file.age > doomed.age ||
        (file.age === doomed.age && file.size > doomed.size) ||
        (file.age === doomed.age && file.size === doomed.size && file.label < doomed.label)
      ) {
        doomed = file;
      }
    }
    removed.push(doomed.label);
    standing = standing.filter((file) => file.label !== doomed.label);
  }
  let held = 0;
  let stale = 0;
  for (const file of standing) {
    held += file.size;
    if (file.age > limit) {
      stale += 1;
    }
  }
  return { removed, held, over: held > budget ? held - budget : 0, stale };
}
