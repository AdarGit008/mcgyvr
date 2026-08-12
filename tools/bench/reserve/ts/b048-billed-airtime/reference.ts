/** Billable airtime for a metered call, in whole seconds. */

export function billedAirtime(duration: number, initial: number, step: number): number {
  if (!Number.isInteger(duration) || duration < 0) {
    throw new Error("duration must be a non-negative integer");
  }
  if (!Number.isInteger(initial) || initial <= 0) {
    throw new Error("initial block must be a positive integer");
  }
  if (!Number.isInteger(step) || step <= 0) {
    throw new Error("billing step must be a positive integer");
  }
  if (duration === 0) {
    return 0;
  }
  if (duration <= initial) {
    return initial;
  }
  const beyond = duration - initial;
  const steps = Math.floor((beyond + step - 1) / step);
  return initial + steps * step;
}
