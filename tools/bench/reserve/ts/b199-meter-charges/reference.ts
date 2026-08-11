/** Meter a period of charges against each caller's granted units. */
export function meterCharges(allowance: Record<string, number>, charges: [string, number][]): Record<string, { used: number; left: number; refused: number }> {
  const report: Record<string, { used: number; left: number; refused: number }> = {};
  for (const caller of Object.keys(allowance)) {
    report[caller] = { used: 0, left: allowance[caller], refused: 0 };
  }
  for (const [caller, cost] of charges) {
    const meter = report[caller];
    if (meter === undefined) {
      throw new Error(`no allowance granted to ${caller}`);
    }
    if (cost < 0) {
      const returned = Math.min(-cost, meter.used);
      meter.used -= returned;
      meter.left += returned;
    } else if (cost <= meter.left) {
      meter.used += cost;
      meter.left -= cost;
    } else {
      meter.refused += 1;
    }
  }
  return report;
}
