export function firstDeadlineMiss(jobs: Array<Record<string, unknown>>): string {
  const seen = new Set<string>();
  for (const job of jobs) {
    if (typeof job.name !== "string" || job.name === "") {
      throw new Error("name must be a non-empty string");
    }
    if (seen.has(job.name)) {
      throw new Error(`name repeated: ${job.name}`);
    }
    seen.add(job.name);
    if (!Number.isInteger(job.work) || (job.work as number) <= 0) {
      throw new Error("work must be a positive integer");
    }
    if (!Number.isInteger(job.due) || (job.due as number) <= 0) {
      throw new Error("due must be a positive integer");
    }
  }
  const order = jobs
    .map((job, position) => ({ job, position }))
    .sort(
      (a, b) =>
        (a.job.due as number) - (b.job.due as number) || a.position - b.position,
    );
  let clock = 0;
  for (const { job } of order) {
    clock += job.work as number;
    if (clock > (job.due as number)) {
      return job.name as string;
    }
  }
  return "";
}
