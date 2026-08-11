/** A deterministic assembly run: steps consume bins, shortages become faults. */

type RunReport = {
  built: string[];
  faults: [string, string][];
  halted: string | null;
  leftover: [string, number][];
};

export function runAssembly(
  bins: Record<string, number>,
  steps: [string, Record<string, number>, boolean][],
): RunReport {
  for (const part of Object.keys(bins)) {
    if (part === "") {
      throw new Error("bin name must be a non-empty string");
    }
    if (!Number.isInteger(bins[part]) || bins[part] < 0) {
      throw new Error("stock must be a non-negative integer");
    }
  }
  for (const step of steps) {
    if (!Array.isArray(step) || step.length !== 3) {
      throw new Error("a step must be a [name, needs, critical] triple");
    }
    const [name, needs, critical] = step;
    if (typeof name !== "string" || name === "") {
      throw new Error("step name must be a non-empty string");
    }
    if (typeof critical !== "boolean") {
      throw new Error("critical flag must be a boolean");
    }
    for (const part of Object.keys(needs)) {
      if (!(part in bins)) {
        throw new Error(`unknown part: ${part}`);
      }
      if (!Number.isInteger(needs[part]) || needs[part] < 1) {
        throw new Error("needed count must be a positive integer");
      }
    }
  }
  const stock: Record<string, number> = { ...bins };
  const built: string[] = [];
  const faults: [string, string][] = [];
  let halted: string | null = null;
  for (const [name, needs, critical] of steps) {
    const short = Object.keys(needs)
      .filter((part) => stock[part] < needs[part])
      .sort();
    if (short.length === 0) {
      for (const part of Object.keys(needs)) {
        stock[part] -= needs[part];
      }
      built.push(name);
      continue;
    }
    faults.push([name, short[0]]);
    if (critical) {
      halted = name;
      break;
    }
  }
  const leftover = Object.keys(stock)
    .sort()
    .map((part): [string, number] => [part, stock[part]]);
  return { built, faults, halted, leftover };
}
