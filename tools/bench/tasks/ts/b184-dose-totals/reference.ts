/** Exact per-reagent totals of a pour log, counted in thousandths. */
export function doseTotals(log: [string, string][]): Record<string, string> {
  const thousandths: Record<string, number> = {};
  const places: Record<string, number> = {};
  for (const [reagent, amount] of log) {
    const written = /^-?\d+(?:\.(\d{1,3}))?$/.exec(amount);
    if (written === null) {
      throw new Error("amount is not a decimal of at most three places: " + amount);
    }
    const digits = written[1] ?? "";
    const sign = amount.startsWith("-") ? -1 : 1;
    const bare = amount.replace("-", "").replace(".", "");
    thousandths[reagent] = (thousandths[reagent] ?? 0) + sign * Number(bare) * Math.pow(10, 3 - digits.length);
    places[reagent] = Math.max(places[reagent] ?? 0, digits.length);
  }
  const totals: Record<string, string> = {};
  for (const reagent of Object.keys(thousandths)) {
    const kept = places[reagent];
    const units = thousandths[reagent] / Math.pow(10, 3 - kept);
    const whole = Math.trunc(Math.abs(units) / Math.pow(10, kept));
    const rest = Math.abs(units) % Math.pow(10, kept);
    const body = kept === 0 ? String(whole) : whole + "." + String(rest).padStart(kept, "0");
    totals[reagent] = (units < 0 ? "-" : "") + body;
  }
  return totals;
}
