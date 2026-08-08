function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function backoffSchedule(
  base: number,
  factor: number,
  cap: number,
  attempts: number,
): number[] {
  if (!whole(base) || base < 1) {
    throw new Error("base must be a whole number of one or more");
  }
  if (!whole(factor) || factor < 1) {
    throw new Error("factor must be a whole number of one or more");
  }
  if (!whole(cap) || cap < base) {
    throw new Error("cap must be a whole number no smaller than base");
  }
  if (!whole(attempts) || attempts < 1) {
    throw new Error("attempts must be a whole number of one or more");
  }
  const moments: number[] = [0];
  let idle = base;
  let clock = 0;
  for (let dial = 1; dial < attempts; dial++) {
    const waited = idle > cap ? cap : idle;
    clock += waited;
    moments.push(clock);
    idle = waited >= cap ? cap : idle * factor;
  }
  return moments;
}
