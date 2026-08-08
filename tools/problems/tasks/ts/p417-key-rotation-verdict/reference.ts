function whole(value: any, floor: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= floor;
}

function readEntry(entry: any): { digest: string; step: number } {
  if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
    throw new Error("an entry must be a record");
  }
  if (!("digest" in entry) || !("step" in entry)) {
    throw new Error("an entry needs both digest and step");
  }
  if (typeof entry.digest !== "string" || !/^[a-z0-9]+$/.test(entry.digest)) {
    throw new Error("a digest is small letters and digits only");
  }
  if (!whole(entry.step, 0)) {
    throw new Error("a step must be a whole number of zero or more");
  }
  return { digest: entry.digest, step: entry.step };
}

export function judgeKeyRotation(ledger: any[], offer: any, rules: any): any {
  if (!Array.isArray(ledger)) {
    throw new Error("the ledger must be a list");
  }
  const past = ledger.map(readEntry);
  for (let i = 1; i < past.length; i++) {
    if (past[i].step <= past[i - 1].step) {
      throw new Error("the ledger steps must rise strictly");
    }
  }
  const put = readEntry(offer);
  if (past.length > 0 && put.step <= past[past.length - 1].step) {
    throw new Error("the offer must sit above the newest ledger step");
  }
  if (rules === null || typeof rules !== "object" || Array.isArray(rules)) {
    throw new Error("rules must be a record");
  }
  for (const key of ["keep", "gap", "span", "runs", "window"]) {
    if (!(key in rules)) {
      throw new Error("rules is missing " + key);
    }
  }
  for (const key of ["keep", "gap"]) {
    if (!whole(rules[key], 0)) {
      throw new Error(key + " must be a whole number of zero or more");
    }
  }
  for (const key of ["span", "runs", "window"]) {
    if (!whole(rules[key], 1)) {
      throw new Error(key + " must be a whole number of one or more");
    }
  }
  if (rules.gap > rules.span) {
    throw new Error("gap may not be larger than span");
  }

  const broken: string[] = [];
  const recent = rules.keep === 0 ? [] : past.slice(Math.max(0, past.length - rules.keep));
  if (recent.some((entry) => entry.digest === put.digest)) {
    broken.push("reused");
  }
  if (past.length > 0) {
    const since = put.step - past[past.length - 1].step;
    if (since < rules.gap) broken.push("toosoon");
    if (since > rules.span) broken.push("stale");
  }
  const floor = put.step - rules.window;
  const busy = past.filter((entry) => entry.step > floor).length;
  if (busy >= rules.runs) {
    broken.push("churn");
  }
  return { verdict: broken.length === 0 ? "accept" : "refuse", broken };
}
