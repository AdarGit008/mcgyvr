const FARES: Record<string, number> = { flex: 0, saver: 1, award: 2 };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function buildBumpList(
  travellers: any[],
  seats: number,
  volunteers: string[],
): { boarding: string[]; bumped: string[] } {
  if (!Array.isArray(travellers)) {
    throw new Error("travellers must be a list");
  }
  if (!whole(seats) || seats < 0) {
    throw new Error("seats must be a whole number of nought or more");
  }
  if (!Array.isArray(volunteers)) {
    throw new Error("volunteers must be a list");
  }

  const codes = new Set<string>();
  const stamps = new Set<number>();
  const roll: { code: string; fare: number; miles: number; checked: number }[] = [];
  for (const traveller of travellers) {
    if (traveller === null || typeof traveller !== "object" || Array.isArray(traveller)) {
      throw new Error("a traveller must be a record");
    }
    if (typeof traveller.code !== "string" || traveller.code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (codes.has(traveller.code)) {
      throw new Error(`two travellers carry the code ${traveller.code}`);
    }
    codes.add(traveller.code);
    if (!(traveller.fare in FARES) || typeof traveller.fare !== "string") {
      throw new Error("fare must be flex, saver or award");
    }
    if (!whole(traveller.miles) || traveller.miles < 0) {
      throw new Error("miles must be a whole number of nought or more");
    }
    if (!whole(traveller.checked) || traveller.checked < 1) {
      throw new Error("checked must be a whole number above nought");
    }
    if (stamps.has(traveller.checked)) {
      throw new Error(`two travellers checked in at ${traveller.checked}`);
    }
    stamps.add(traveller.checked);
    roll.push({
      code: traveller.code,
      fare: FARES[traveller.fare],
      miles: traveller.miles,
      checked: traveller.checked,
    });
  }

  const offered = new Set<string>();
  for (const code of volunteers) {
    if (typeof code !== "string" || !codes.has(code)) {
      throw new Error("a volunteer must name a traveller on the roll");
    }
    if (offered.has(code)) {
      throw new Error(`the volunteer ${code} is named twice`);
    }
    offered.add(code);
  }

  roll.sort((a, b) => {
    if (a.fare !== b.fare) return a.fare - b.fare;
    if (a.miles !== b.miles) return b.miles - a.miles;
    return a.checked - b.checked;
  });

  let owed = roll.length - seats;
  if (owed < 0) {
    owed = 0;
  }
  const bumped: string[] = [];
  const gone = new Set<string>();
  for (const code of volunteers) {
    if (bumped.length >= owed) break;
    bumped.push(code);
    gone.add(code);
  }
  for (let i = roll.length - 1; i >= 0 && bumped.length < owed; i--) {
    if (gone.has(roll[i].code)) continue;
    bumped.push(roll[i].code);
    gone.add(roll[i].code);
  }

  const boarding = roll.filter((rider) => !gone.has(rider.code)).map((rider) => rider.code);
  return { boarding, bumped };
}
