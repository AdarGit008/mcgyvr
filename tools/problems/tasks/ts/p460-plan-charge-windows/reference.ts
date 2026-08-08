type Band = {
  label: string;
  opens: number;
  shuts: number;
  price: number;
  rate: number;
  blocked: boolean;
};

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planChargeWindows(
  windows: any[],
  target: number,
): { plan: (string | number)[][]; cost: number; short: number } {
  if (!Array.isArray(windows)) {
    throw new Error("windows must be a list");
  }
  if (!whole(target) || target < 0) {
    throw new Error("target must be a whole number of nought or more");
  }

  const labels = new Set<string>();
  const bands: Band[] = [];
  for (const band of windows) {
    if (band === null || typeof band !== "object" || Array.isArray(band)) {
      throw new Error("a window must be a record");
    }
    if (typeof band.label !== "string" || band.label.length === 0) {
      throw new Error("a label must be a non-empty string");
    }
    if (labels.has(band.label)) {
      throw new Error(`two windows carry the label ${band.label}`);
    }
    labels.add(band.label);
    if (!whole(band.opens) || band.opens < 0) {
      throw new Error("opens must be a whole number of nought or more");
    }
    if (!whole(band.shuts) || band.shuts <= band.opens) {
      throw new Error("shuts must be a whole number later than opens");
    }
    if (!whole(band.price) || band.price < 0) {
      throw new Error("price must be a whole number of nought or more");
    }
    if (!whole(band.rate) || band.rate < 1) {
      throw new Error("rate must be a whole number above nought");
    }
    if (typeof band.blocked !== "boolean") {
      throw new Error("blocked must be either true or false");
    }
    bands.push({
      label: band.label,
      opens: band.opens,
      shuts: band.shuts,
      price: band.price,
      rate: band.rate,
      blocked: band.blocked,
    });
  }

  const byClock = [...bands].sort((a, b) => a.opens - b.opens);
  for (let i = 1; i < byClock.length; i++) {
    if (byClock[i - 1].shuts > byClock[i].opens) {
      throw new Error(`the windows ${byClock[i - 1].label} and ${byClock[i].label} overlap`);
    }
  }

  const byPrice = [...bands].sort((a, b) => (a.price !== b.price ? a.price - b.price : a.opens - b.opens));
  const taken = new Map<string, number>();
  let owed = target;
  let cost = 0;
  for (const band of byPrice) {
    if (owed === 0) break;
    if (band.blocked) continue;
    const room = (band.shuts - band.opens) * band.rate;
    const units = room < owed ? room : owed;
    if (units === 0) continue;
    taken.set(band.label, units);
    cost += units * band.price;
    owed -= units;
  }

  const plan: (string | number)[][] = [];
  for (const band of byClock) {
    if (taken.has(band.label)) {
      plan.push([band.label, taken.get(band.label) as number]);
    }
  }
  return { plan, cost, short: owed };
}
