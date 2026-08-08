function marked(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function handled(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

export function foldVisitTrail(pings: any, idle: any): (string | number[])[][] {
  if (!Array.isArray(pings)) {
    throw new Error("the pings must be a list");
  }
  if (!marked(idle) || idle < 1) {
    throw new Error("idle must be a whole number of one or more");
  }
  const trails = new Map<string, number[]>();
  for (const ping of pings) {
    if (!Array.isArray(ping) || ping.length !== 2) {
      throw new Error("a ping must be a list of exactly two items");
    }
    const [handle, stamp] = ping;
    if (!handled(handle)) {
      throw new Error("a handle must be a non-empty string");
    }
    if (!marked(stamp)) {
      throw new Error("a stamp must be a whole number");
    }
    if (!trails.has(handle)) {
      trails.set(handle, []);
    }
    const stamps = trails.get(handle) as number[];
    if (stamps.includes(stamp)) {
      throw new Error("a handle carries one stamp twice");
    }
    stamps.push(stamp);
  }
  const folded: (string | number[])[][] = [];
  for (const handle of [...trails.keys()].sort()) {
    const stamps = (trails.get(handle) as number[])
      .slice()
      .sort((left, right) => left - right);
    const runs: number[] = [];
    for (let i = 0; i < stamps.length; i++) {
      if (i === 0 || stamps[i] - stamps[i - 1] >= idle) {
        runs.push(1);
      } else {
        runs[runs.length - 1] += 1;
      }
    }
    folded.push([handle, runs]);
  }
  return folded;
}
