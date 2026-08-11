/** Prune a file listing with ordered drop and keep rules. */

function segmentFits(pattern: string, text: string): boolean {
  let p = 0;
  let t = 0;
  let star = -1;
  let mark = 0;
  while (t < text.length) {
    if (p < pattern.length && pattern[p] === "*") {
      star = p;
      mark = t;
      p += 1;
    } else if (p < pattern.length && pattern[p] === text[t]) {
      p += 1;
      t += 1;
    } else if (star >= 0) {
      p = star + 1;
      mark += 1;
      t = mark;
    } else {
      return false;
    }
  }
  while (p < pattern.length && pattern[p] === "*") {
    p += 1;
  }
  return p === pattern.length;
}

function splitStrict(text: string, what: string): string[] {
  if (typeof text !== "string" || text === "") {
    throw new Error(`${what} must be a non-empty string`);
  }
  const segments = text.split("/");
  if (segments.some((segment) => segment === "")) {
    throw new Error(`${what} has an empty segment: ${text}`);
  }
  return segments;
}

export function pruneListing(listing: string[], rules: string[]): string[] {
  const parsed: { keep: boolean; segments: string[] }[] = [];
  for (const rule of rules) {
    if (typeof rule !== "string") {
      throw new Error("every rule must be a string");
    }
    const keep = rule.startsWith("!");
    const body = keep ? rule.slice(1) : rule;
    parsed.push({ keep, segments: splitStrict(body, "rule pattern") });
  }
  const kept: string[] = [];
  for (const path of listing) {
    const steps = splitStrict(path, "path");
    let retained = true;
    for (const { keep, segments } of parsed) {
      if (segments.length > steps.length) {
        continue;
      }
      if (segments.every((segment, i) => segmentFits(segment, steps[i]))) {
        retained = keep;
      }
    }
    if (retained) {
      kept.push(path);
    }
  }
  return kept;
}
