/** Total each item in base units and report it in the largest exact unit. */
export function tallyByUnit(entries: [string, number, string][], units: Record<string, number>): Record<string, [number, string]> {
  const totals = new Map<string, number>();
  for (const entry of entries) {
    const item = entry[0];
    const base = entry[1] * units[entry[2]];
    const running = totals.get(item);
    totals.set(item, running === undefined ? base : running + base);
  }

  const ladder = Object.entries(units).sort((one, two) => two[1] - one[1]);
  const report: Record<string, [number, string]> = {};
  for (const [item, total] of totals) {
    for (const [name, worth] of ladder) {
      if (total % worth === 0) {
        report[item] = [total / worth, name];
        break;
      }
    }
  }
  return report;
}
