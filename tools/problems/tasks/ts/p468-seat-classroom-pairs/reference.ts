function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function seatClassroom(
  room: Record<string, unknown>,
): { seated: boolean; grid: string[][] } {
  if (typeof room !== "object" || room === null || Array.isArray(room)) {
    throw new Error("seatClassroom expects a mapping");
  }
  if (Object.keys(room).sort().join(",") !== "apart,cols,pupils,rows,together") {
    throw new Error("the room carries exactly rows, cols, pupils, together and apart");
  }
  const rows = room["rows"];
  const cols = room["cols"];
  if (!whole(rows) || Number(rows) < 1) {
    throw new Error("rows is not whole or falls below one");
  }
  if (!whole(cols) || Number(cols) < 1) {
    throw new Error("cols is not whole or falls below one");
  }
  const down = Number(rows);
  const across = Number(cols);
  const roster = room["pupils"];
  if (!Array.isArray(roster)) {
    throw new Error("the pupils are not a list");
  }
  const names: string[] = [];
  for (const pupil of roster) {
    if (typeof pupil !== "string" || pupil.length === 0) {
      throw new Error("a pupil is not a non-empty string");
    }
    if (names.includes(pupil)) {
      throw new Error("two pupils share a name");
    }
    names.push(pupil);
  }
  const desks = down * across;
  if (names.length > desks) {
    throw new Error("there are more pupils than desks");
  }
  names.sort();
  const rank = new Map<string, number>();
  names.forEach((name, at) => rank.set(name, at));
  const count = names.length;

  function readPairs(field: string): Set<number> {
    const raw = room[field];
    if (!Array.isArray(raw)) {
      throw new Error("a pairing list is not a list");
    }
    const found = new Set<number>();
    for (const pair of raw) {
      if (!Array.isArray(pair) || pair.length !== 2) {
        throw new Error("a pairing is not a list of two names");
      }
      const first = rank.get(String(pair[0]));
      const second = rank.get(String(pair[1]));
      if (
        typeof pair[0] !== "string" ||
        typeof pair[1] !== "string" ||
        first === undefined ||
        second === undefined
      ) {
        throw new Error("a pairing names somebody the roster does not hold");
      }
      if (first === second) {
        throw new Error("a pairing names one pupil twice");
      }
      const key = Math.min(first, second) * count + Math.max(first, second);
      if (found.has(key)) {
        throw new Error("a pairing is listed twice in one list");
      }
      found.add(key);
    }
    return found;
  }

  const glued = readPairs("together");
  const split = readPairs("apart");
  for (const key of glued) {
    if (split.has(key)) {
      throw new Error("a pairing appears in both lists");
    }
  }

  const partners: number[][] = names.map(() => []);
  for (const key of glued) {
    const lo = Math.floor(key / count);
    const hi = key % count;
    partners[lo].push(hi);
    partners[hi].push(lo);
  }

  const pairKey = (a: number, b: number) =>
    Math.min(a, b) * count + Math.max(a, b);
  const adjacent = (a: number, b: number) => {
    const ra = Math.floor(a / across);
    const ca = a % across;
    const rb = Math.floor(b / across);
    const cb = b % across;
    return (
      (ra === rb && Math.abs(ca - cb) === 1) ||
      (ca === cb && Math.abs(ra - rb) === 1)
    );
  };

  const seatOf: number[] = new Array(desks).fill(-1);
  const deskOf: number[] = new Array(count).fill(-1);

  function solve(at: number, left: number): boolean {
    if (at === desks) {
      return left === 0;
    }
    if (desks - at < left) {
      return false;
    }
    const column = at % across;
    const row = Math.floor(at / across);
    for (let pupil = 0; pupil < count; pupil++) {
      if (deskOf[pupil] !== -1) {
        continue;
      }
      let fine = true;
      if (column > 0 && seatOf[at - 1] !== -1) {
        fine = !split.has(pairKey(pupil, seatOf[at - 1]));
      }
      if (fine && row > 0 && seatOf[at - across] !== -1) {
        fine = !split.has(pairKey(pupil, seatOf[at - across]));
      }
      if (fine) {
        for (const mate of partners[pupil]) {
          if (deskOf[mate] !== -1 && !adjacent(at, deskOf[mate])) {
            fine = false;
            break;
          }
        }
      }
      if (!fine) {
        continue;
      }
      seatOf[at] = pupil;
      deskOf[pupil] = at;
      if (solve(at + 1, left - 1)) {
        return true;
      }
      seatOf[at] = -1;
      deskOf[pupil] = -1;
    }
    return solve(at + 1, left);
  }

  if (!solve(0, count)) {
    return { seated: false, grid: [] };
  }
  const grid: string[][] = [];
  for (let row = 0; row < down; row++) {
    const line: string[] = [];
    for (let column = 0; column < across; column++) {
      const who = seatOf[row * across + column];
      line.push(who === -1 ? "" : names[who]);
    }
    grid.push(line);
  }
  return { seated: true, grid };
}
