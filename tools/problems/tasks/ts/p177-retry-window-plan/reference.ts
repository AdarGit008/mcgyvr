const NAMES = ["won", "lost", "held"];

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planRetryWindow(
  policy: {
    base: number;
    factor: number;
    ceiling: number;
    tries: number;
    deadline: number;
  },
  outcomes: string[],
): { times: number[]; verdict: string } {
  if (typeof policy !== "object" || policy === null || Array.isArray(policy)) {
    throw new Error("the policy must be a record");
  }
  for (const field of ["base", "factor", "ceiling", "tries", "deadline"]) {
    if (!(field in policy)) {
      throw new Error("the policy is missing " + field);
    }
  }
  const base = policy.base;
  const factor = policy.factor;
  const ceiling = policy.ceiling;
  const tries = policy.tries;
  const deadline = policy.deadline;
  for (const value of [base, factor, tries, deadline]) {
    if (!whole(value) || value < 1) {
      throw new Error("base, factor, tries and deadline must be one or more");
    }
  }
  if (!whole(ceiling) || ceiling < base) {
    throw new Error("ceiling must be a whole number of at least base");
  }
  if (!Array.isArray(outcomes)) {
    throw new Error("the outcomes must be a list");
  }
  for (const outcome of outcomes) {
    if (typeof outcome !== "string" || !NAMES.includes(outcome)) {
      throw new Error("an outcome must be won, lost or held");
    }
  }
  const times: number[] = [0];
  let made = 1;
  let streak = 0;
  for (;;) {
    if (made > outcomes.length) {
      throw new Error("the outcome list ends while the plan is still going");
    }
    const outcome = outcomes[made - 1];
    if (outcome === "won") {
      return { times, verdict: "succeeded" };
    }
    if (made === tries) {
      return { times, verdict: "exhausted" };
    }
    let gap: number;
    if (outcome === "lost") {
      streak += 1;
      gap = base;
      for (let grown = 1; grown < streak; grown++) {
        gap = gap * factor;
        if (gap > ceiling) {
          gap = ceiling;
        }
      }
      if (gap > ceiling) {
        gap = ceiling;
      }
    } else {
      streak = 0;
      gap = ceiling;
    }
    const next = times[times.length - 1] + gap;
    if (next >= deadline) {
      return { times, verdict: "expired" };
    }
    times.push(next);
    made += 1;
  }
}
