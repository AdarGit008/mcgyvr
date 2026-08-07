type Mark = { step: string; at: number };

function named(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function funnelRungReach(
  marks: any,
  ladder: any,
  window: any,
): (string | number)[][] {
  if (!Array.isArray(ladder) || ladder.length === 0) {
    throw new Error("the ladder must be a non-empty list");
  }
  const rungs: string[] = [];
  const known = new Set<string>();
  for (const step of ladder) {
    if (!named(step)) {
      throw new Error("a ladder step must be a non-empty string");
    }
    if (known.has(step)) {
      throw new Error("the ladder names " + step + " twice");
    }
    known.add(step);
    rungs.push(step);
  }
  if (!whole(window) || window < 0) {
    throw new Error("window must be a whole number of zero or more");
  }
  if (!Array.isArray(marks)) {
    throw new Error("the marks must be a list");
  }

  const byActor = new Map<string, Mark[]>();
  for (const mark of marks) {
    if (!Array.isArray(mark) || mark.length !== 3) {
      throw new Error("a mark must be a list of exactly three items");
    }
    const [actor, step, at] = mark;
    if (!named(actor) || !named(step)) {
      throw new Error("an actor and a step must be non-empty strings");
    }
    if (!whole(at)) {
      throw new Error("an at must be a whole number");
    }
    if (!known.has(step)) {
      continue;
    }
    if (!byActor.has(actor)) {
      byActor.set(actor, []);
    }
    (byActor.get(actor) as Mark[]).push({ step, at });
  }

  const counts = new Array(rungs.length).fill(0);
  for (const own of byActor.values()) {
    const list = own.slice().sort((left, right) => left.at - right.at);
    let reached = -1;
    for (let start = 0; start < list.length; start++) {
      if (list[start].step !== rungs[0]) {
        continue;
      }
      let held = list[start].at;
      let depth = 0;
      for (let rung = 1; rung < rungs.length; rung++) {
        let found = -1;
        for (let j = 0; j < list.length; j++) {
          if (list[j].at > held && list[j].step === rungs[rung]) {
            found = j;
            break;
          }
        }
        if (found === -1) break;
        if (list[found].at - list[start].at > window) break;
        held = list[found].at;
        depth = rung;
      }
      if (depth > reached) reached = depth;
    }
    for (let rung = 0; rung <= reached; rung++) {
      counts[rung] += 1;
    }
  }
  return rungs.map((step, index) => [step, counts[index]]);
}
