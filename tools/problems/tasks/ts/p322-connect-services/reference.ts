type Leg = {
  code: string;
  from: string;
  to: string;
  depart: number;
  arrive: number;
};

type Journey = { arrive: number; legs: string[] };

const NAMES = ["code", "from", "to", "depart", "arrive"];

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function label(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function preferred(candidate: Journey, held: Journey): boolean {
  if (candidate.arrive !== held.arrive) {
    return candidate.arrive < held.arrive;
  }
  if (candidate.legs.length !== held.legs.length) {
    return candidate.legs.length < held.legs.length;
  }
  for (let i = 0; i < candidate.legs.length; i++) {
    if (candidate.legs[i] !== held.legs[i]) {
      return candidate.legs[i] < held.legs[i];
    }
  }
  return false;
}

export function connectServices(
  services: any,
  origin: any,
  destination: any,
  readyAt: any,
  minTransfer: any,
): Journey {
  if (!Array.isArray(services)) {
    throw new Error("the timetable must be a list");
  }
  if (!label(origin) || !label(destination)) {
    throw new Error("origin and destination must be non-empty strings");
  }
  if (origin === destination) {
    throw new Error("origin and destination must differ");
  }
  if (!whole(readyAt) || readyAt < 0) {
    throw new Error("readyAt must be a whole number of zero or more");
  }
  if (!whole(minTransfer) || minTransfer < 0) {
    throw new Error("minTransfer must be a whole number of zero or more");
  }

  const table: Leg[] = [];
  const codes = new Set<string>();
  for (const raw of services) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a service must be a record");
    }
    for (const name of NAMES) {
      if (!Object.prototype.hasOwnProperty.call(raw, name)) {
        throw new Error("a service is missing " + name);
      }
    }
    if (!label(raw.code)) {
      throw new Error("a code must be a non-empty string");
    }
    if (!label(raw.from) || !label(raw.to)) {
      throw new Error("a place must be a non-empty string");
    }
    if (raw.from === raw.to) {
      throw new Error("a service must not set down where it picked up");
    }
    if (!whole(raw.depart) || !whole(raw.arrive)) {
      throw new Error("depart and arrive must be whole numbers");
    }
    if (raw.arrive <= raw.depart) {
      throw new Error("arrive must be later than depart");
    }
    if (codes.has(raw.code)) {
      throw new Error("two services share the code " + raw.code);
    }
    codes.add(raw.code);
    table.push({
      code: raw.code,
      from: raw.from,
      to: raw.to,
      depart: raw.depart,
      arrive: raw.arrive,
    });
  }

  let best: Journey | null = null;
  const called = new Set<string>([origin]);
  const ridden: string[] = [];

  const ride = (here: string, arrivedAt: number, earliest: number): void => {
    if (here === destination) {
      const found: Journey = { arrive: arrivedAt, legs: ridden.slice() };
      if (best === null || preferred(found, best)) {
        best = found;
      }
      return;
    }
    for (const service of table) {
      if (service.from !== here) continue;
      if (service.depart < earliest) continue;
      if (called.has(service.to)) continue;
      called.add(service.to);
      ridden.push(service.code);
      ride(service.to, service.arrive, service.arrive + minTransfer);
      ridden.pop();
      called.delete(service.to);
    }
  };

  ride(origin, readyAt, readyAt);
  return best === null ? { arrive: -1, legs: [] } : best;
}
