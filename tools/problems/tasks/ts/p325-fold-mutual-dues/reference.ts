type Slip = { who: string; whom: string; cents: number };

function tallied(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function held(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

export function foldMutualDues(slips: any): Slip[] {
  if (!Array.isArray(slips)) {
    throw new Error("the slips must be a list");
  }
  const running = new Map<string, Map<string, number>>();
  const people = new Set<string>();
  for (const slip of slips) {
    if (slip === null || typeof slip !== "object" || Array.isArray(slip)) {
      throw new Error("a slip must be a record");
    }
    for (const name of ["who", "whom", "cents"]) {
      if (!Object.prototype.hasOwnProperty.call(slip, name)) {
        throw new Error("a slip is missing " + name);
      }
    }
    if (!held(slip.who) || !held(slip.whom)) {
      throw new Error("a name must be a non-empty string");
    }
    if (slip.who === slip.whom) {
      throw new Error("a slip must not name one person twice");
    }
    if (!tallied(slip.cents) || slip.cents < 1) {
      throw new Error("cents must be a whole number of one or more");
    }
    if (!running.has(slip.who)) {
      running.set(slip.who, new Map<string, number>());
    }
    const row = running.get(slip.who) as Map<string, number>;
    row.set(slip.whom, (row.get(slip.whom) ?? 0) + slip.cents);
    people.add(slip.who);
    people.add(slip.whom);
  }

  const owed = (from: string, to: string): number =>
    running.get(from)?.get(to) ?? 0;

  const names = [...people].sort();
  const folded: Slip[] = [];
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const left = names[i];
      const right = names[j];
      const net = owed(left, right) - owed(right, left);
      if (net > 0) {
        folded.push({ who: left, whom: right, cents: net });
      } else if (net < 0) {
        folded.push({ who: right, whom: left, cents: -net });
      }
    }
  }
  folded.sort((a, b) => (a.who === b.who ? (a.whom < b.whom ? -1 : 1) : a.who < b.who ? -1 : 1));
  return folded;
}
