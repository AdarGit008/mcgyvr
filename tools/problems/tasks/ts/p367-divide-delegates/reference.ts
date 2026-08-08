/** Delegates handed to each slate by quota, leftover and roster. */
type Slate = { name: string; votes: number; roster: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

export function divideDelegates(
  slates: Array<Record<string, unknown>>,
  delegates: number,
): Record<string, number> {
  if (!Array.isArray(slates) || slates.length === 0) {
    throw new Error("there must be at least one slate");
  }
  if (!whole(delegates)) {
    throw new Error("the delegate count must be a whole number above zero");
  }
  const rows: Slate[] = [];
  const names = new Set<string>();
  for (const raw of slates) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a slate must be a mapping");
    }
    const name = raw.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a slate needs a non-empty name");
    }
    if (names.has(name)) {
      throw new Error("two slates carry the same name");
    }
    names.add(name);
    if (!whole(raw.votes) || !whole(raw.roster)) {
      throw new Error("votes and roster must be whole numbers above zero");
    }
    rows.push({
      name,
      votes: raw.votes as number,
      roster: raw.roster as number,
    });
  }
  const seats = rows.reduce((sum, row) => sum + row.roster, 0);
  if (seats < delegates) {
    throw new Error("the rosters cannot hold that many delegates");
  }

  const held = new Map<string, number>();
  let standing = [...rows];
  let left = delegates;
  while (standing.length > 0) {
    const total = standing.reduce((sum, row) => sum + row.votes, 0);
    const share = standing.map((row, at) => {
      const exact = row.votes * left;
      const base = Math.floor(exact / total);
      return { row, at, base, rest: exact - base * total };
    });
    let spare = left - share.reduce((sum, item) => sum + item.base, 0);
    const queue = [...share].sort(
      (a, b) =>
        b.rest - a.rest || b.row.votes - a.row.votes || a.at - b.at,
    );
    for (const item of queue) {
      if (spare === 0) {
        break;
      }
      item.base += 1;
      spare -= 1;
    }
    const over = share.filter((item) => item.base > item.row.roster);
    if (over.length === 0) {
      for (const item of share) {
        held.set(item.row.name, item.base);
      }
      break;
    }
    const pinned = new Set<string>();
    for (const item of over) {
      held.set(item.row.name, item.row.roster);
      left -= item.row.roster;
      pinned.add(item.row.name);
    }
    standing = standing.filter((row) => !pinned.has(row.name));
  }

  const answer: Record<string, number> = {};
  for (const row of rows) {
    answer[row.name] = held.get(row.name) as number;
  }
  return answer;
}
