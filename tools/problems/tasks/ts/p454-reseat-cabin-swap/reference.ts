const SEAT = /^([1-9][0-9]*)([A-Z])$/;
const WANTS = ["window", "aisle", "any"];

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function capitals(value: unknown): boolean {
  return typeof value === "string" && /^[A-Z]+$/.test(value);
}

export function reseatCabin(holders: any[], cabin: any): { seated: string[]; bumped: string[] } {
  if (!Array.isArray(holders)) {
    throw new Error("holders must be a list");
  }
  if (cabin === null || typeof cabin !== "object" || Array.isArray(cabin)) {
    throw new Error("cabin must be a record");
  }
  if (!whole(cabin.rows) || cabin.rows < 1) {
    throw new Error("rows must be a whole number above nought");
  }
  if (!capitals(cabin.left) || !capitals(cabin.right)) {
    throw new Error("left and right must be non-empty runs of capital letters");
  }
  const order: string = cabin.left + cabin.right;
  if (new Set(order).size !== order.length) {
    throw new Error("a seat letter is used twice in one row");
  }
  if (!Array.isArray(cabin.blocked)) {
    throw new Error("blocked must be a list");
  }

  const rank = (row: number, letter: string): number => (row - 1) * order.length + order.indexOf(letter);
  const windows = new Set([cabin.left[0], cabin.right[cabin.right.length - 1]]);
  const aisles = new Set([cabin.left[cabin.left.length - 1], cabin.right[0]]);

  const free = new Map<number, string>();
  for (let row = 1; row <= cabin.rows; row++) {
    for (const letter of order) {
      free.set(rank(row, letter), `${row}${letter}`);
    }
  }
  for (const label of cabin.blocked) {
    const parsed = typeof label === "string" ? SEAT.exec(label) : null;
    if (parsed === null) {
      throw new Error("a blocked seat must be a row number then one capital letter");
    }
    const row = Number(parsed[1]);
    if (row > cabin.rows || !order.includes(parsed[2])) {
      throw new Error(`the cabin has no seat ${label}`);
    }
    free.delete(rank(row, parsed[2]));
  }

  const names = new Set<string>();
  const oldSeats = new Set<string>();
  const queue: { name: string; row: number; letter: string; want: string }[] = [];
  for (const holder of holders) {
    if (holder === null || typeof holder !== "object" || Array.isArray(holder)) {
      throw new Error("a holder must be a record");
    }
    if (typeof holder.name !== "string" || holder.name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (names.has(holder.name)) {
      throw new Error(`two holders answer to the name ${holder.name}`);
    }
    names.add(holder.name);
    const parsed = typeof holder.seat === "string" ? SEAT.exec(holder.seat) : null;
    if (parsed === null) {
      throw new Error("a seat must be a row number then one capital letter");
    }
    if (oldSeats.has(holder.seat)) {
      throw new Error(`two holders claim the old seat ${holder.seat}`);
    }
    oldSeats.add(holder.seat);
    if (!WANTS.includes(holder.want)) {
      throw new Error("want must be window, aisle or any");
    }
    queue.push({ name: holder.name, row: Number(parsed[1]), letter: parsed[2], want: holder.want });
  }

  queue.sort((a, b) => (a.row !== b.row ? a.row - b.row : a.letter < b.letter ? -1 : 1));

  const suits = (want: string, letter: string): boolean => {
    if (want === "any") return true;
    if (want === "window") return windows.has(letter);
    return aisles.has(letter);
  };

  const seated: string[] = [];
  const bumped: string[] = [];
  for (const rider of queue) {
    const keys = [...free.keys()].sort((a, b) => a - b);
    const held = rider.row <= cabin.rows && order.includes(rider.letter) ? rank(rider.row, rider.letter) : -1;
    if (held >= 0 && free.has(held)) {
      seated.push(`${rider.name} ${free.get(held)} kept`);
      free.delete(held);
      continue;
    }
    let chosen = -1;
    for (const key of keys) {
      const label = free.get(key) as string;
      if (suits(rider.want, label[label.length - 1])) {
        chosen = key;
        break;
      }
    }
    if (chosen >= 0) {
      seated.push(`${rider.name} ${free.get(chosen)} moved`);
      free.delete(chosen);
      continue;
    }
    if (keys.length > 0) {
      seated.push(`${rider.name} ${free.get(keys[0])} shifted`);
      free.delete(keys[0]);
      continue;
    }
    bumped.push(rider.name);
  }
  return { seated, bumped };
}
