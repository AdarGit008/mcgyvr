function pair(row: unknown, what: string): [string, string] {
  if (!Array.isArray(row) || row.length !== 2) {
    throw new Error(`every ${what} is a pair of names`);
  }
  for (const name of row) {
    if (typeof name !== "string" || name === "") {
      throw new Error(`a ${what} name must be a non-empty string`);
    }
  }
  return [row[0] as string, row[1] as string];
}

export function lockCycleVictim(
  holds: string[][],
  blocked: string[][],
): { victim: string; cycle: string[] } {
  if (!Array.isArray(holds) || !Array.isArray(blocked)) {
    throw new Error("lockCycleVictim expects two lists of pairs");
  }
  const holder = new Map<string, string>();
  const held = new Map<string, number>();
  const workers = new Set<string>();
  for (const row of holds) {
    const [resource, worker] = pair(row, "granted lock");
    if (holder.has(resource)) {
      throw new Error(`${resource} is granted twice`);
    }
    holder.set(resource, worker);
    held.set(worker, (held.get(worker) ?? 0) + 1);
    workers.add(worker);
  }
  const waitingOn = new Map<string, string>();
  for (const row of blocked) {
    const [worker, resource] = pair(row, "blocked request");
    if (waitingOn.has(worker)) {
      throw new Error(`${worker} is blocked on two resources`);
    }
    if (holder.get(resource) === worker) {
      throw new Error(`${worker} is blocked on a lock it holds`);
    }
    waitingOn.set(worker, resource);
    workers.add(worker);
  }

  const step = (worker: string): string | undefined => {
    const resource = waitingOn.get(worker);
    if (resource === undefined) {
      return undefined;
    }
    return holder.get(resource);
  };

  const done = new Set<string>();
  const onRing = new Set<string>();
  for (const start of workers) {
    if (done.has(start)) {
      continue;
    }
    const path: string[] = [];
    const seenAt = new Map<string, number>();
    let current: string | undefined = start;
    while (current !== undefined && !done.has(current) && !seenAt.has(current)) {
      seenAt.set(current, path.length);
      path.push(current);
      current = step(current);
    }
    if (current !== undefined && seenAt.has(current)) {
      for (let i = seenAt.get(current) as number; i < path.length; i++) {
        onRing.add(path[i]);
      }
    }
    for (const worker of path) {
      done.add(worker);
    }
  }

  let victim = "";
  for (const worker of onRing) {
    if (victim === "") {
      victim = worker;
      continue;
    }
    const mine = held.get(worker) ?? 0;
    const best = held.get(victim) ?? 0;
    if (mine < best || (mine === best && worker < victim)) {
      victim = worker;
    }
  }
  if (victim === "") {
    return { victim: "", cycle: [] };
  }
  const cycle: string[] = [victim];
  let current = step(victim) as string;
  while (current !== victim) {
    cycle.push(current);
    current = step(current) as string;
  }
  return { victim, cycle };
}
