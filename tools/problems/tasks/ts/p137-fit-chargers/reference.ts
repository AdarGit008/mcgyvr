export function fitChargers(
  chargers: Array<{ plug: string; low: number; high: number }>,
  devices: Array<{ plug: string; draw: number }>,
): number[] {
  const taken = chargers.map(() => false);
  const handed: number[] = [];
  for (const device of devices) {
    let pick = -1;
    for (let i = 0; i < chargers.length; i++) {
      const charger = chargers[i];
      if (
        !taken[i] &&
        charger.plug === device.plug &&
        charger.low <= device.draw &&
        device.draw <= charger.high
      ) {
        pick = i;
        break;
      }
    }
    if (pick !== -1) {
      taken[pick] = true;
    }
    handed.push(pick);
  }
  return handed;
}
