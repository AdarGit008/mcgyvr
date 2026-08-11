export function runThermostat(
  start: number,
  low: number,
  high: number,
  power: number,
  drifts: number[],
): { temp: number; heated: number; switches: number; coldest: number } {
  for (const bound of [start, low, high]) {
    if (!Number.isInteger(bound)) {
      throw new Error("temperatures must be integers");
    }
  }
  if (low >= high) {
    throw new Error("low must lie strictly below high");
  }
  if (!Number.isInteger(power) || power <= 0) {
    throw new Error("power must be a positive integer");
  }
  if (!Array.isArray(drifts)) {
    throw new Error("drifts must be a list");
  }
  let temp = start;
  let heating = false;
  let heated = 0;
  let switches = 0;
  let coldest = start;
  for (const drift of drifts) {
    if (!Number.isInteger(drift)) {
      throw new Error("drifts must be integers");
    }
    if (temp < low && !heating) {
      heating = true;
      switches += 1;
    } else if (temp >= high && heating) {
      heating = false;
      switches += 1;
    }
    if (heating) {
      heated += 1;
      temp += power;
    }
    temp += drift;
    if (temp < coldest) {
      coldest = temp;
    }
  }
  return { temp, heated, switches, coldest };
}
