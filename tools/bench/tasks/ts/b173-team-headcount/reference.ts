export function teamHeadcount(chart: Record<string, string[]>, name: string): number {
  if (chart === null || typeof chart !== "object" || Array.isArray(chart)) throw new Error("chart must be a mapping");
  if (!(name in chart)) throw new Error("the chart holds no such name");
  const reports = chart[name];
  if (!Array.isArray(reports)) throw new Error("the reports of a worker must be a list");
  let covered = 1;
  for (const worker of reports) {
    if (typeof worker !== "string") throw new Error("a report must be a name");
    covered += teamHeadcount(chart, worker);
  }
  return covered;
}
