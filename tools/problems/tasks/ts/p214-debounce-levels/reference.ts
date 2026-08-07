export function debounceLevels(samples: unknown, hold: unknown): number[] {
  if (!Array.isArray(samples) || samples.length === 0) {
    throw new Error("the sample list must be a non-empty list");
  }
  for (const sample of samples) {
    if (sample !== 0 && sample !== 1) {
      throw new Error("a sample must be 0 or 1");
    }
  }
  if (typeof hold !== "number" || !Number.isInteger(hold) || hold < 1) {
    throw new Error("hold must be a positive whole number");
  }
  let settled = samples[0] as number;
  let tally = 0;
  const report: number[] = [settled];
  for (let index = 1; index < samples.length; index++) {
    const sample = samples[index] as number;
    if (sample === settled) {
      tally = 0;
    } else {
      tally += 1;
      if (tally >= hold) {
        settled = sample;
        tally = 0;
      }
    }
    report.push(settled);
  }
  return report;
}
