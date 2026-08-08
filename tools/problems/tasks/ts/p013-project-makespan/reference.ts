export function projectMakespan(
  durations: Record<string, number>,
  deps: [string, string][],
): number {
  for (const name of Object.keys(durations)) {
    const minutes = durations[name];
    if (typeof minutes !== "number" || !Number.isInteger(minutes) || minutes <= 0) {
      throw new Error(`duration of ${name} must be a positive whole number`);
    }
  }
  const prereqs = new Map<string, string[]>();
  for (const [before, after] of deps) {
    if (!(before in durations) || !(after in durations)) {
      throw new Error("dependency names a task absent from the mapping");
    }
    if (before === after) {
      throw new Error("a task cannot depend on itself");
    }
    const list = prereqs.get(after) ?? [];
    list.push(before);
    prereqs.set(after, list);
  }
  const finish = new Map<string, number>();
  const onPath = new Set<string>();
  const finishTime = (name: string): number => {
    const done = finish.get(name);
    if (done !== undefined) {
      return done;
    }
    if (onPath.has(name)) {
      throw new Error("dependencies form a cycle");
    }
    onPath.add(name);
    let start = 0;
    for (const need of prereqs.get(name) ?? []) {
      start = Math.max(start, finishTime(need));
    }
    onPath.delete(name);
    const total = start + durations[name];
    finish.set(name, total);
    return total;
  };
  let makespan = 0;
  for (const name of Object.keys(durations)) {
    makespan = Math.max(makespan, finishTime(name));
  }
  return makespan;
}
