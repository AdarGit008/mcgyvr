const KINDS = ["full", "diff", "incr"];

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isRecord(value: any): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function planRestoreChain(runs: any[], target: number): any {
  if (!Array.isArray(runs) || runs.length === 0) {
    throw new Error("runs must be a non-empty list");
  }
  const table = new Map<number, any>();
  const labels = new Set<string>();
  for (const run of runs) {
    if (!isRecord(run)) {
      throw new Error("each run is a record");
    }
    for (const key of ["label", "kind", "step", "sound"]) {
      if (!(key in run)) {
        throw new Error("a run is missing " + key);
      }
    }
    if (typeof run.label !== "string" || run.label === "") {
      throw new Error("label must be a non-empty string");
    }
    if (labels.has(run.label)) {
      throw new Error("two runs share a label");
    }
    labels.add(run.label);
    if (!KINDS.includes(run.kind)) {
      throw new Error("kind must be full, diff or incr");
    }
    if (!whole(run.step)) {
      throw new Error("step must be a whole number of zero or more");
    }
    if (table.has(run.step)) {
      throw new Error("two runs share a step");
    }
    if (typeof run.sound !== "boolean") {
      throw new Error("sound must be a boolean");
    }
    table.set(run.step, run);
  }
  if (!whole(target)) {
    throw new Error("target must be a whole number of zero or more");
  }
  if (!table.has(target)) {
    throw new Error("no run carries the target step");
  }
  const order = [...table.keys()].sort((a, b) => a - b);
  const chain: string[] = [];
  let step = target;
  for (;;) {
    const run = table.get(step);
    if (!run.sound) {
      return { ok: "no", chain: [], reason: "damaged" };
    }
    chain.push(run.label);
    if (run.kind === "full") {
      chain.reverse();
      return { ok: "yes", chain, reason: "" };
    }
    const earlier = order.filter((s) => s < step);
    if (earlier.length === 0) {
      return { ok: "no", chain: [], reason: "nofull" };
    }
    if (run.kind === "incr") {
      step = earlier[earlier.length - 1];
      continue;
    }
    const fulls = earlier.filter((s) => {
      const older = table.get(s);
      return older.kind === "full" && older.sound;
    });
    if (fulls.length === 0) {
      return { ok: "no", chain: [], reason: "nofull" };
    }
    step = fulls[fulls.length - 1];
  }
}
