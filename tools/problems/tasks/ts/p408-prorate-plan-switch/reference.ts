export function proratePlanSwitch(
  cycleDays: number,
  moveDay: number,
  paidCents: number,
  planCents: number,
): { credit: number; charge: number; due: number; carried: number } {
  if (!Number.isInteger(cycleDays) || cycleDays < 1) {
    throw new Error("the cycle must be a whole number of one day or more");
  }
  if (!Number.isInteger(moveDay) || moveDay < 1 || moveDay > cycleDays) {
    throw new Error("the day of the move must lie inside the cycle");
  }
  for (const cents of [paidCents, planCents]) {
    if (!Number.isInteger(cents) || cents < 0) {
      throw new Error("a price must be a whole number of cents, nothing or more");
    }
  }
  const unused = cycleDays - moveDay + 1;
  const credit = Math.floor((paidCents * unused) / cycleDays);
  const owedBefore = planCents * unused;
  const charge = Math.floor((owedBefore + cycleDays - 1) / cycleDays);
  const due = charge > credit ? charge - credit : 0;
  const carried = credit > charge ? credit - charge : 0;
  return { credit, charge, due, carried };
}
