/** Tick simulation: most-remaining first, then lexicographically smallest. */
export function schedule(tasks: string[], cooldown: number): string[] {
  const remaining: Map<string, number> = new Map();
  for (const label of tasks) {
    remaining.set(label, (remaining.get(label) ?? 0) + 1);
  }
  const nextReady: Map<string, number> = new Map();
  const out: string[] = [];
  let left = tasks.length;
  for (let tick = 0; left > 0; tick++) {
    let pick = "";
    let pickCount = 0;
    for (const [label, count] of remaining) {
      if (count === 0) continue;
      if ((nextReady.get(label) ?? 0) > tick) continue;
      if (pick === "" || count > pickCount || (count === pickCount && label < pick)) {
        pick = label;
        pickCount = count;
      }
    }
    if (pick === "") {
      out.push("idle");
      continue;
    }
    out.push(pick);
    remaining.set(pick, pickCount - 1);
    nextReady.set(pick, tick + cooldown + 1);
    left -= 1;
  }
  return out;
}
