export function flagProbeReadings(
  readings: unknown,
  rules: unknown,
): string[][] {
  if (!Array.isArray(readings) || readings.length === 0) {
    throw new Error("readings must be a non-empty list");
  }
  for (const reading of readings) {
    if (!Number.isInteger(reading)) {
      throw new Error("every reading must be a whole number");
    }
  }
  if (rules === null || typeof rules !== "object" || Array.isArray(rules)) {
    throw new Error("rules must be a mapping");
  }
  const spec = rules as Record<string, any>;
  for (const key of ["low", "high", "jump", "stuck"]) {
    if (!Number.isInteger(spec[key])) {
      throw new Error(`${key} must be a whole number`);
    }
  }
  const low: number = spec.low;
  const high: number = spec.high;
  const jump: number = spec.jump;
  const stuck: number = spec.stuck;
  if (low > high) {
    throw new Error("low must not sit above high");
  }
  if (jump < 0) {
    throw new Error("jump must not be beneath zero");
  }
  if (stuck < 2) {
    throw new Error("stuck must not be beneath two");
  }

  const report: string[][] = [];
  let reference: number | null = null;
  let runValue: number = readings[0];
  let runLength = 0;
  for (const reading of readings as number[]) {
    if (reading === runValue) {
      runLength += 1;
    } else {
      runValue = reading;
      runLength = 1;
    }
    const flags: string[] = [];
    const implausible = reading < low || reading > high;
    if (implausible) {
      flags.push("range");
    } else if (reference !== null && Math.abs(reading - reference) > jump) {
      flags.push("jump");
    }
    if (runLength >= stuck) {
      flags.push("stuck");
    }
    if (!implausible) {
      reference = reading;
    }
    report.push(flags);
  }
  return report;
}
