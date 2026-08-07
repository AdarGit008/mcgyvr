export function stalledLoopMembers(waits: Record<string, string>): string[] {
  if (waits === null || typeof waits !== "object" || Array.isArray(waits)) {
    throw new Error("stalledLoopMembers expects a stall table");
  }
  for (const [job, target] of Object.entries(waits)) {
    if (job === "") {
      throw new Error("a stalled job cannot have an empty name");
    }
    if (typeof target !== "string" || target === "") {
      throw new Error(`${job} waits on something that is not a job name`);
    }
    if (job === target) {
      throw new Error(`${job} waits on itself`);
    }
  }

  const size = Object.keys(waits).length;
  const closes = (job: string): boolean => {
    let current = job;
    for (let step = 0; step <= size; step++) {
      if (!(current in waits)) {
        return false;
      }
      current = waits[current];
      if (current === job) {
        return true;
      }
    }
    return false;
  };

  const looped = Object.keys(waits).filter(closes);
  if (looped.length === 0) {
    return [];
  }
  const start = looped.slice().sort()[0];
  const members = [start];
  let current = waits[start];
  while (current !== start) {
    members.push(current);
    current = waits[current];
  }
  return members.sort();
}
