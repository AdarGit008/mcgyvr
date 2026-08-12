/** Replay metered calls through a sliding-window throttle. */
export function throttleCalls(
  span: number,
  cap: number,
  budget: number,
  calls: number[][],
): { verdicts: string[]; remaining: number } {
  if (!Number.isInteger(span) || span <= 0) {
    throw new Error("span must be a positive integer of seconds");
  }
  if (!Number.isInteger(cap) || cap <= 0) {
    throw new Error("cap must be a positive integer of units");
  }
  if (!Number.isInteger(budget) || budget < 0) {
    throw new Error("budget must be a non-negative integer of units");
  }
  const passed: number[][] = [];
  const verdicts: string[] = [];
  let remaining = budget;
  let previous = 0;
  for (const call of calls) {
    if (!Array.isArray(call) || call.length !== 2) {
      throw new Error("a call is a [time, units] pair");
    }
    const [time, units] = call;
    if (!Number.isInteger(time) || time < 0) {
      throw new Error("a call time must be a non-negative integer");
    }
    if (!Number.isInteger(units) || units <= 0) {
      throw new Error("call units must be a positive integer");
    }
    if (time < previous) {
      throw new Error("call times must not decrease");
    }
    previous = time;
    while (passed.length > 0 && passed[0][0] <= time - span) {
      passed.shift();
    }
    let load = units;
    for (const [, spent] of passed) {
      load += spent;
    }
    if (load <= cap && units <= remaining) {
      passed.push([time, units]);
      remaining -= units;
      verdicts.push("pass");
    } else {
      verdicts.push("drop");
    }
  }
  return { verdicts, remaining };
}
