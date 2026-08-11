/** Spread courses over numbered study terms, prerequisites strictly earlier. */

export function planTerms(
  courses: string[],
  prereqs: string[][],
  perTerm: number,
): string[][] {
  if (!Array.isArray(courses)) {
    throw new Error("courses must be a list");
  }
  const known = new Set<string>();
  for (const course of courses) {
    if (typeof course !== "string" || course.length === 0) {
      throw new Error("each course must be a non-empty string");
    }
    if (known.has(course)) {
      throw new Error(`course listed twice: ${course}`);
    }
    known.add(course);
  }
  if (!Number.isInteger(perTerm) || perTerm < 1) {
    throw new Error("perTerm must be a whole number of at least one");
  }
  if (!Array.isArray(prereqs)) {
    throw new Error("prereqs must be a list");
  }
  const needs = new Map<string, string[]>();
  for (const course of courses) {
    needs.set(course, []);
  }
  for (const pair of prereqs) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("each prereq must be a [course, needed] pair");
    }
    const [course, needed] = pair;
    if (!known.has(course) || !known.has(needed)) {
      throw new Error("prereq names a course absent from the list");
    }
    needs.get(course)!.push(needed);
  }
  const planned = new Set<string>();
  const terms: string[][] = [];
  while (planned.size < known.size) {
    const ready: string[] = [];
    for (const course of courses) {
      if (planned.has(course)) {
        continue;
      }
      if (needs.get(course)!.every((need) => planned.has(need))) {
        ready.push(course);
      }
    }
    if (ready.length === 0) {
      throw new Error("prerequisites loop back on themselves");
    }
    ready.sort();
    const term = ready.slice(0, perTerm);
    terms.push(term);
    for (const course of term) {
      planned.add(course);
    }
  }
  return terms;
}
