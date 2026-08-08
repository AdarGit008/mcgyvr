type Room = { room: string; hop: number; dwell: number; merit: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function auditTourCard(
  rooms: Record<string, unknown>[],
  card: string[],
  allowance: number,
): { minutes: number; merit: number; spare: number; ok: boolean } {
  if (!Array.isArray(rooms)) {
    throw new Error("auditTourCard expects a list of rooms");
  }
  if (!Array.isArray(card)) {
    throw new Error("the card is not a list");
  }
  if (!whole(allowance) || allowance < 0) {
    throw new Error("the allowance is not whole or falls below nought");
  }

  const floor: Room[] = [];
  const where = new Map<string, number>();
  for (const entry of rooms) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("a room is not a mapping");
    }
    if (Object.keys(entry).sort().join(",") !== "dwell,hop,merit,room") {
      throw new Error("a room's keys are not exactly the four named");
    }
    const name = entry["room"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a room name is not a non-empty string");
    }
    if (where.has(name)) {
      throw new Error("a room name is repeated on the floor");
    }
    const hop = entry["hop"];
    if (!whole(hop) || (hop as number) < 0) {
      throw new Error("a hop is not whole or falls below nought");
    }
    const dwell = entry["dwell"];
    if (!whole(dwell) || (dwell as number) < 1) {
      throw new Error("a dwell is not whole or falls below one");
    }
    const merit = entry["merit"];
    if (!whole(merit) || (merit as number) < 0) {
      throw new Error("a merit is not whole or falls below nought");
    }
    where.set(name, floor.length);
    floor.push({
      room: name,
      hop: hop as number,
      dwell: dwell as number,
      merit: merit as number,
    });
  }

  let last = -1;
  let dwelt = 0;
  let merit = 0;
  for (const name of card) {
    if (typeof name !== "string") {
      throw new Error("a card entry is not a string");
    }
    const seat = where.get(name);
    if (seat === undefined) {
      throw new Error("a card entry names no room on the floor");
    }
    if (seat <= last) {
      throw new Error("a card repeats a name or falls out of floor-plan order");
    }
    last = seat;
    dwelt += floor[seat].dwell;
    merit += floor[seat].merit;
  }

  let walked = 0;
  for (let index = 0; index <= last; index++) {
    walked += floor[index].hop;
  }

  const minutes = walked + dwelt;
  return { minutes, merit, spare: allowance - minutes, ok: minutes <= allowance };
}
