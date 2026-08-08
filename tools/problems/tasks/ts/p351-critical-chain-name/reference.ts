type Step = { label: string; hours: number; needs: string[] };

function readsFirst(left: string[], right: string[]): boolean {
  const shared = Math.min(left.length, right.length);
  for (let i = 0; i < shared; i += 1) {
    if (left[i] !== right[i]) {
      return left[i] < right[i];
    }
  }
  return left.length < right.length;
}

export function criticalChainName(steps: Step[]): string {
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the job must hold at least one step");
  }
  const hours = new Map<string, number>();
  const needs = new Map<string, string[]>();
  for (const step of steps) {
    if (typeof step !== "object" || step === null || Array.isArray(step)) {
      throw new Error("every step must be a mapping");
    }
    const label = step.label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a label must be a non-empty string");
    }
    if (hours.has(label)) {
      throw new Error("two steps carry the same label");
    }
    const cost = step.hours;
    if (typeof cost !== "number" || !Number.isInteger(cost) || cost <= 0) {
      throw new Error("hours must be a whole number greater than zero");
    }
    const before = step.needs;
    if (!Array.isArray(before)) {
      throw new Error("the needs list must be a list");
    }
    for (const earlier of before) {
      if (typeof earlier !== "string") {
        throw new Error("the needs list must hold strings");
      }
      if (earlier === label) {
        throw new Error("a step may not need itself");
      }
    }
    hours.set(label, cost);
    needs.set(label, [...before]);
  }
  for (const before of needs.values()) {
    for (const earlier of before) {
      if (!hours.has(earlier)) {
        throw new Error("a needs entry matches no label in the job");
      }
    }
  }

  const labels = [...hours.keys()].sort();
  const later = new Map<string, string[]>();
  for (const label of labels) {
    later.set(label, []);
  }
  const owing = new Map<string, number>();
  for (const label of labels) {
    owing.set(label, needs.get(label).length);
    for (const earlier of needs.get(label)) {
      later.get(earlier).push(label);
    }
  }
  const order: string[] = [];
  const ready = labels.filter((label) => owing.get(label) === 0);
  while (ready.length > 0) {
    const label = ready.shift();
    order.push(label);
    for (const next of later.get(label)) {
      owing.set(next, owing.get(next) - 1);
      if (owing.get(next) === 0) {
        ready.push(next);
      }
    }
  }
  if (order.length !== labels.length) {
    throw new Error("the needs relation closes into a ring");
  }

  const weight = new Map<string, number>();
  const run = new Map<string, string[]>();
  for (const label of order) {
    let bestWeight = 0;
    let bestRun: string[] = [];
    for (const earlier of needs.get(label)) {
      const there = weight.get(earlier);
      if (
        there > bestWeight ||
        (there === bestWeight && readsFirst(run.get(earlier), bestRun))
      ) {
        bestWeight = there;
        bestRun = run.get(earlier);
      }
    }
    weight.set(label, bestWeight + hours.get(label));
    run.set(label, [...bestRun, label]);
  }

  let pickedWeight = -1;
  let picked: string[] = [];
  for (const label of labels) {
    const here = weight.get(label);
    if (here > pickedWeight || (here === pickedWeight && readsFirst(run.get(label), picked))) {
      pickedWeight = here;
      picked = run.get(label);
    }
  }
  return picked.join(">");
}
