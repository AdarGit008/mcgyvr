export function runPress(
  jobs: [string, number][], budget: number,
): { printed: string[]; waiting: string[]; pages: number } {
  if (!Array.isArray(jobs)) throw new Error("jobs must be a list");
  if (!Number.isInteger(budget) || budget < 0) throw new Error("budget must be a non-negative whole number");
  const printed: string[] = [], waiting: string[] = [];
  let pages = 0;
  for (const job of jobs) {
    if (!Array.isArray(job) || job.length !== 2 || typeof job[0] !== "string" || job[0] === "" || !Number.isInteger(job[1]) || job[1] < 1) throw new Error("malformed job");
    if (waiting.length === 0 && pages + job[1] <= budget) {
      printed.push(job[0]);
      pages += job[1];
    } else {
      waiting.push(job[0]);
    }
  }
  return { printed, waiting, pages };
}
