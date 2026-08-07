function whole(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

export function steadyReadings(
  readings: unknown,
  spec: unknown
): Record<string, unknown> {
  if (!Array.isArray(readings) || readings.length === 0) {
    throw new Error("the reading list must be a non-empty list");
  }
  for (const reading of readings) {
    if (!whole(reading)) {
      throw new Error("a reading must be a whole number");
    }
  }
  if (spec === null || typeof spec !== "object" || Array.isArray(spec)) {
    throw new Error("the second argument must be a mapping");
  }
  const settings = spec as Record<string, unknown>;
  const band = settings.band;
  const hold = settings.hold;
  if (!whole(band) || band < 0) {
    throw new Error("band must be a non-negative whole number");
  }
  if (!whole(hold) || hold < 1) {
    throw new Error("hold must be a positive whole number");
  }

  let steady = readings[0] as number;
  let opener = 0;
  let run = 0;
  const settled: number[] = [steady];
  const moved: number[] = [];
  for (let index = 1; index < readings.length; index++) {
    const reading = readings[index] as number;
    if (Math.abs(reading - steady) <= band) {
      run = 0;
    } else {
      if (run > 0 && Math.abs(reading - opener) <= band) {
        run += 1;
      } else {
        opener = reading;
        run = 1;
      }
      if (run >= hold) {
        steady = opener;
        run = 0;
        moved.push(index);
      }
    }
    settled.push(steady);
  }
  return { settled, moved };
}
