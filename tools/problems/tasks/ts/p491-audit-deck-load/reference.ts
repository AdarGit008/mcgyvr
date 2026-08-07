/** Which rule an already loaded deck breaks first. */
function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isWhole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function auditDeckLoad(rows: any[], deck: any): any {
  if (!isRecord(deck)) {
    throw new Error("deck must be a record");
  }
  if (!Array.isArray(deck.bays) || deck.bays.length === 0) {
    throw new Error("bays must be a list holding at least one bay");
  }
  const holds = new Map<string, number>();
  const levers = new Map<string, number>();
  const pulls = new Map<string, number>();
  const order: string[] = [];
  for (const bay of deck.bays) {
    if (!isRecord(bay)) {
      throw new Error("each bay must be a record");
    }
    if (typeof bay.bay !== "string" || bay.bay.length === 0) {
      throw new Error("a bay name must be a non-empty string");
    }
    if (holds.has(bay.bay)) {
      throw new Error(`two bays answer to the name ${bay.bay}`);
    }
    if (!isWhole(bay.hold) || bay.hold < 1) {
      throw new Error("hold must be a whole number above nought");
    }
    if (!isWhole(bay.pull) || bay.pull < 1) {
      throw new Error("pull must be a whole number above nought");
    }
    if (!isWhole(bay.lever)) {
      throw new Error("lever must be a whole number");
    }
    holds.set(bay.bay, bay.hold);
    levers.set(bay.bay, bay.lever);
    pulls.set(bay.bay, bay.pull);
    order.push(bay.bay);
  }
  if (!isWhole(deck.total) || deck.total < 1) {
    throw new Error("total must be a whole number above nought");
  }

  if (!Array.isArray(rows)) {
    throw new Error("rows must be a list");
  }
  const seen = new Set<string>();
  const weights = new Map<string, number>();
  for (const name of order) {
    weights.set(name, 0);
  }
  let weight = 0;
  for (const row of rows) {
    if (!isRecord(row)) {
      throw new Error("each row must be a record");
    }
    if (typeof row.crate !== "string" || row.crate.length === 0) {
      throw new Error("crate must be a non-empty string");
    }
    if (seen.has(row.crate)) {
      throw new Error(`two rows answer to the crate ${row.crate}`);
    }
    seen.add(row.crate);
    if (typeof row.bay !== "string" || row.bay.length === 0) {
      throw new Error("a row's bay must be a non-empty string");
    }
    if (!weights.has(row.bay)) {
      throw new Error(`the deck lists no bay called ${row.bay}`);
    }
    if (!isWhole(row.weight) || row.weight < 1) {
      throw new Error("weight must be a whole number above nought");
    }
    weights.set(row.bay, weights.get(row.bay) + row.weight);
    weight += row.weight;
  }

  let swing = 0;
  for (const name of order) {
    swing += weights.get(name) * levers.get(name);
  }
  for (const name of order) {
    if (weights.get(name) > holds.get(name)) {
      return { verdict: "broken", bay: name, limit: "hold", weight, swing };
    }
    if (Math.abs(weights.get(name) * levers.get(name)) > pulls.get(name)) {
      return { verdict: "broken", bay: name, limit: "pull", weight, swing };
    }
  }
  if (weight > deck.total) {
    return { verdict: "broken", bay: "", limit: "total", weight, swing };
  }
  return { verdict: "clear", bay: "", limit: "", weight, swing };
}
