function counting(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function traceBreakerStates(outcomes: any[], settings: any): string[] {
  if (!Array.isArray(outcomes)) {
    throw new Error("outcomes must be a list");
  }
  for (const outcome of outcomes) {
    if (outcome !== "pass" && outcome !== "fail") {
      throw new Error("an outcome is either pass or fail");
    }
  }
  if (
    settings === null ||
    typeof settings !== "object" ||
    Array.isArray(settings)
  ) {
    throw new Error("settings must be a record");
  }
  for (const key of ["trip", "cool", "proof"]) {
    if (!(key in settings)) {
      throw new Error("settings is missing " + key);
    }
    if (!counting(settings[key])) {
      throw new Error(key + " must be a whole number of one or more");
    }
  }
  const { trip, cool, proof } = settings;
  let posture = "closed";
  let losing = 0;
  let winning = 0;
  let countdown = 0;
  const trace: string[] = [];
  for (const outcome of outcomes) {
    if (posture === "closed") {
      losing = outcome === "fail" ? losing + 1 : 0;
      if (losing === trip) {
        posture = "open";
        countdown = cool;
      }
    } else if (posture === "open") {
      countdown -= 1;
      if (countdown === 0) {
        posture = "half";
        winning = 0;
      }
    } else {
      if (outcome === "pass") {
        winning += 1;
        if (winning === proof) {
          posture = "closed";
          losing = 0;
        }
      } else {
        posture = "open";
        countdown = cool;
      }
    }
    trace.push(posture);
  }
  return trace;
}
