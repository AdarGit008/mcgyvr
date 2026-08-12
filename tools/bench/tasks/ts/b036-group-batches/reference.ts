/**
 * Schedule grouped jobs into weighted batches. Jobs arrive as [name,
 * group, priority, weight] quadruples; within a group, jobs must run in
 * arrival order, so only the earliest unscheduled job of each group is
 * ever eligible. Each round fills one batch: eligible heads are ranked by
 * urgency and taken first-fit against the batch's weight capacity.
 */
export function groupBatches(
  jobs: [string, string, number, number][],
  capacity: number,
): string[][] {
  if (!Array.isArray(jobs)) {
    throw new Error("jobs must be a list");
  }
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  const seen = new Set<string>();
  for (const job of jobs) {
    if (!Array.isArray(job) || job.length !== 4) {
      throw new Error("each job is a [name, group, priority, weight] quadruple");
    }
    const [name, group, priority, weight] = job;
    if (typeof name !== "string" || name === "") {
      throw new Error("job name must be a non-empty string");
    }
    if (typeof group !== "string" || group === "") {
      throw new Error("job group must be a non-empty string");
    }
    if (typeof priority !== "number" || !Number.isInteger(priority)) {
      throw new Error("job priority must be an integer");
    }
    if (!Number.isInteger(weight) || weight < 1 || weight > capacity) {
      throw new Error("job weight must be an integer from 1 to capacity");
    }
    if (seen.has(name)) {
      throw new Error("job names must be unique");
    }
    seen.add(name);
  }
  // Per-group queues in arrival order; each holds global arrival indexes.
  const queues = new Map<string, number[]>();
  const order: string[] = [];
  jobs.forEach((job, index) => {
    const group = job[1];
    if (!queues.has(group)) {
      queues.set(group, []);
      order.push(group);
    }
    queues.get(group)!.push(index);
  });
  const batches: string[][] = [];
  let remaining = jobs.length;
  while (remaining > 0) {
    // The heads: the earliest unscheduled job of every non-empty group.
    const heads: number[] = [];
    for (const group of order) {
      const queue = queues.get(group)!;
      if (queue.length > 0) {
        heads.push(queue[0]);
      }
    }
    heads.sort((a, b) => {
      if (jobs[b][2] !== jobs[a][2]) {
        return jobs[b][2] - jobs[a][2];
      }
      return a - b;
    });
    // First-fit in urgency order: a head too heavy for what is left of
    // this batch is passed over, and later, lighter heads may still fit.
    const batch: string[] = [];
    let load = 0;
    for (const index of heads) {
      const weight = jobs[index][3];
      if (load + weight > capacity) {
        continue;
      }
      batch.push(jobs[index][0]);
      load += weight;
      queues.get(jobs[index][1])!.shift();
      remaining -= 1;
    }
    batches.push(batch);
  }
  return batches;
}
