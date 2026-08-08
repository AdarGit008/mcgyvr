export function settleClaimRun(claims: unknown, plan: unknown): number[][] {
  if (!Array.isArray(claims)) {
    throw new Error("claims must be a list");
  }
  for (const claim of claims) {
    if (!Number.isInteger(claim) || claim < 0) {
      throw new Error("every claim must be a whole number of cents, not below zero");
    }
  }
  if (plan === null || typeof plan !== "object" || Array.isArray(plan)) {
    throw new Error("plan must be a mapping");
  }
  const spec = plan as Record<string, any>;
  for (const key of ["deductible", "coinsurance", "cap"]) {
    if (!Number.isInteger(spec[key])) {
      throw new Error(`${key} must be a whole number`);
    }
  }
  const deductible: number = spec.deductible;
  const coinsurance: number = spec.coinsurance;
  const cap: number = spec.cap;
  if (deductible < 0 || cap < 0) {
    throw new Error("deductible and cap must not fall below zero");
  }
  if (coinsurance < 0 || coinsurance > 100) {
    throw new Error("coinsurance must be a whole percent from 0 through 100");
  }
  if (cap < deductible) {
    throw new Error("cap must not lie below deductible");
  }

  const rows: number[][] = [];
  let unmet = deductible;
  let running = 0;
  for (const claim of claims as number[]) {
    const swallowed = claim < unmet ? claim : unmet;
    const shared = claim - swallowed;
    const share = Math.floor((shared * coinsurance + 50) / 100);
    const owed = swallowed + share;
    const room = cap - running;
    const member = owed < room ? owed : room;
    unmet -= swallowed;
    running += member;
    rows.push([member, claim - member, unmet, running]);
  }
  return rows;
}
