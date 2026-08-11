/** Clock-time helpers and the leg-by-leg arrival tracker built on them. */

export function parseClock(text: string): number {
  if (typeof text !== "string" || !/^\d\d:\d\d$/.test(text)) {
    throw new Error("a clock reads HH:MM");
  }
  const hours = Number(text.slice(0, 2));
  const minutes = Number(text.slice(3));
  if (hours > 23 || minutes > 59) {
    throw new Error("no such clock time");
  }
  return hours * 60 + minutes;
}

export function formatClock(minutes: number): string {
  if (!Number.isInteger(minutes) || minutes < 0 || minutes > 1439) {
    throw new Error("minutes must lie in 0..1439");
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function legArrivals(
  departure: string,
  legs: number[][],
): [string, number][] {
  const start = parseClock(departure);
  const arrivals: [string, number][] = [];
  let elapsed = 0;
  for (const leg of legs) {
    if (!Array.isArray(leg) || leg.length !== 2) {
      throw new Error("a leg is [travel, layover]");
    }
    const [travel, layover] = leg;
    if (!Number.isInteger(travel) || !Number.isInteger(layover)) {
      throw new Error("leg minutes must be integers");
    }
    if (travel <= 0) {
      throw new Error("travel minutes must be a positive integer");
    }
    if (layover < 0) {
      throw new Error("layover minutes must be a non-negative integer");
    }
    elapsed += travel;
    const absolute = start + elapsed;
    arrivals.push([formatClock(absolute % 1440), Math.floor(absolute / 1440)]);
    elapsed += layover;
  }
  return arrivals;
}
