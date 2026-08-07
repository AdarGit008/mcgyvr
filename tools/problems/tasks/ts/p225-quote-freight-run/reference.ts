function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function quoteFreightRun(
  bands: Array<Record<string, unknown>>,
  kilos: number,
): Record<string, unknown> {
  if (!Array.isArray(bands) || bands.length === 0) {
    throw new Error("the bands must be a non-empty list");
  }
  const starts: number[] = [];
  const rates: number[] = [];
  for (const band of bands) {
    if (band === null || typeof band !== "object" || Array.isArray(band)) {
      throw new Error("a band must be a mapping");
    }
    const start = band.from;
    const rate = band.perKilo;
    if (!whole(start) || (start as number) < 0) {
      throw new Error("a starting weight must be a whole number of nought or more");
    }
    if (!whole(rate) || (rate as number) < 0) {
      throw new Error("a rate must be a non-negative whole number");
    }
    if (starts.length === 0) {
      if ((start as number) !== 0) {
        throw new Error("the first band must start at nought");
      }
    } else if ((start as number) <= starts[starts.length - 1]) {
      throw new Error("the starting weights must climb strictly");
    }
    starts.push(start as number);
    rates.push(rate as number);
  }
  if (!whole(kilos) || kilos < 1) {
    throw new Error("the consignment weight must be a whole number of one or more");
  }
  const split: number[] = [];
  let cents = 0;
  for (let at = 0; at < starts.length; at++) {
    const stop = at + 1 < starts.length ? starts[at + 1] : kilos;
    const covered = Math.max(0, Math.min(stop, kilos) - starts[at]);
    const charge = covered * rates[at];
    split.push(charge);
    cents += charge;
  }
  return { split, cents };
}
