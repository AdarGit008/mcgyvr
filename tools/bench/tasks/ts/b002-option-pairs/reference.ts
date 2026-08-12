export function parseOption(segment: string): string[] {
  const eq = segment.indexOf("=");
  const key = segment.slice(0, eq);
  if (eq === -1 || !/^[A-Za-z][A-Za-z0-9_]*$/.test(key)) {
    throw new Error("malformed option segment: " + segment);
  }
  let raw = segment.slice(eq + 1);
  if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
    raw = raw.slice(1, -1);
  }
  return [key, raw];
}

export function scanPairs(input: string): string[][] {
  if (typeof input !== "string" || input.length === 0) {
    throw new Error("scanPairs expects a non-empty string");
  }
  const segments: string[] = [];
  let current = "";
  let quoted = false;
  for (const ch of input) {
    if (ch === '"') quoted = !quoted;
    if (ch === ";" && !quoted) {
      segments.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  if (quoted) throw new Error("unterminated quoted value");
  segments.push(current);
  const seen = new Set<string>();
  const pairs: string[][] = [];
  for (const segment of segments) {
    const [key, value] = parseOption(segment);
    if (seen.has(key)) {
      throw new Error("repeated key: " + key);
    }
    seen.add(key);
    pairs.push([key, value]);
  }
  return pairs;
}
