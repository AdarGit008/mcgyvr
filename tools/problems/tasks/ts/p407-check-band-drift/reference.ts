const NEARNESS: Record<string, number> = { A: 0, B: 1, C: 2 };

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function checkBandDrift(
  entries: { code: string; hits: number; was: string }[],
  marks: number[],
): { up: string[]; down: string[]; steady: number } {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("the audit needs at least one entry");
  }
  const seen = new Set<string>();
  const held: { code: string; hits: number; was: string }[] = [];
  for (const entry of entries) {
    if (!isRecord(entry)) {
      throw new Error("an entry must be a record");
    }
    const code = entry.code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (seen.has(code)) {
      throw new Error("code " + code + " appears twice");
    }
    seen.add(code);
    const hits = entry.hits;
    if (!Number.isInteger(hits) || hits < 0) {
      throw new Error("hits must be a whole number of nothing or more");
    }
    const was = entry.was;
    if (was !== "A" && was !== "B" && was !== "C") {
      throw new Error("the former class must be A, B or C");
    }
    held.push({ code, hits, was });
  }
  if (!Array.isArray(marks) || marks.length !== 2) {
    throw new Error("the marks must be two whole permille values");
  }
  const first = marks[0];
  const second = marks[1];
  for (const mark of [first, second]) {
    if (!Number.isInteger(mark) || mark < 1 || mark > 999) {
      throw new Error("a mark must be a whole number from 1 to 999");
    }
  }
  if (first >= second) {
    throw new Error("the first mark must fall under the second");
  }
  let grand = 0;
  for (const entry of held) {
    grand += entry.hits;
  }
  if (grand === 0) {
    throw new Error("the season recorded no hits at all");
  }
  const sweep = held.slice().sort((a, b) => {
    if (b.hits !== a.hits) {
      return b.hits - a.hits;
    }
    return a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
  });
  const up: string[] = [];
  const down: string[] = [];
  let steady = 0;
  let piled = 0;
  for (const entry of sweep) {
    piled += entry.hits;
    const weighed = piled * 1000;
    let now = "C";
    if (weighed <= first * grand) {
      now = "A";
    } else if (weighed <= second * grand) {
      now = "B";
    }
    if (NEARNESS[now] < NEARNESS[entry.was]) {
      up.push(entry.code);
    } else if (NEARNESS[now] > NEARNESS[entry.was]) {
      down.push(entry.code);
    } else {
      steady += 1;
    }
  }
  return { up, down, steady };
}
