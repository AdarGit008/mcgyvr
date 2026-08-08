type Row = { step: string; count: number; lost: number; share: number };

function named(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function stepDropReport(tallies: any, order: any): Row[] {
  if (!Array.isArray(order) || order.length === 0) {
    throw new Error("the order must be a non-empty list");
  }
  const wanted: string[] = [];
  const seen = new Set<string>();
  for (const step of order) {
    if (!named(step)) {
      throw new Error("an ordered step must be a non-empty string");
    }
    if (seen.has(step)) {
      throw new Error("the order names " + step + " twice");
    }
    seen.add(step);
    wanted.push(step);
  }
  if (!Array.isArray(tallies)) {
    throw new Error("the tallies must be a list");
  }
  const counted = new Map<string, number>();
  for (const tally of tallies) {
    if (!Array.isArray(tally) || tally.length !== 2) {
      throw new Error("a tally must be a list of exactly two items");
    }
    const [step, count] = tally;
    if (!named(step)) {
      throw new Error("a step name must be a non-empty string");
    }
    if (!whole(count) || count < 0) {
      throw new Error("a count must be a whole number of zero or more");
    }
    if (!seen.has(step)) {
      throw new Error("the order does not name " + step);
    }
    if (counted.has(step)) {
      throw new Error(step + " is tallied more than once");
    }
    counted.set(step, count);
  }
  for (const step of wanted) {
    if (!counted.has(step)) {
      throw new Error(step + " has no tally");
    }
  }

  const top = counted.get(wanted[0]) as number;
  const report: Row[] = [];
  for (let index = 0; index < wanted.length; index++) {
    const count = counted.get(wanted[index]) as number;
    if (index > 0) {
      const above = counted.get(wanted[index - 1]) as number;
      if (count > above) {
        throw new Error(wanted[index] + " stands above the step over it");
      }
      report.push({
        step: wanted[index],
        count,
        lost: above - count,
        share: top === 0 ? 0 : Math.floor((count * 100) / top),
      });
    } else {
      report.push({
        step: wanted[index],
        count,
        lost: 0,
        share: top === 0 ? 0 : 100,
      });
    }
  }
  return report;
}
