type Waiting = { who: string; rank: number; since: number };

export function agedServiceOrder(
  events: Array<Record<string, unknown>>,
  step: number
): string[] {
  if (!Number.isInteger(step) || step <= 0) {
    throw new Error("the aging step must be a positive whole number");
  }
  if (!Array.isArray(events) || events.length === 0) {
    throw new Error("the log is empty");
  }
  const room: Waiting[] = [];
  const taken: string[] = [];
  let previous = -1;
  for (const moment of events) {
    if (moment === null || typeof moment !== "object" || Array.isArray(moment)) {
      throw new Error("a moment must be a mapping");
    }
    const tick = moment.tick;
    if (!Number.isInteger(tick) || (tick as number) < 0) {
      throw new Error("a tick is a non-negative whole number");
    }
    if ((tick as number) < previous) {
      throw new Error("tick " + tick + " runs backwards");
    }
    previous = tick as number;
    const kind = moment.kind;
    if (kind === "join") {
      const who = moment.who;
      if (typeof who !== "string" || who.length === 0) {
        throw new Error("a joining caller needs a name");
      }
      const rank = moment.rank;
      if (!Number.isInteger(rank) || (rank as number) < 0) {
        throw new Error("a rank is a non-negative whole number");
      }
      if (room.some((entry) => entry.who === who)) {
        throw new Error(who + " is already in the waiting room");
      }
      room.push({ who, rank: rank as number, since: tick as number });
    } else if (kind === "call") {
      if (room.length === 0) {
        throw new Error("a call found the waiting room empty");
      }
      let chosen = 0;
      let best = -1;
      for (let i = 0; i < room.length; i++) {
        const entry = room[i];
        const standing =
          entry.rank + Math.floor(((tick as number) - entry.since) / step);
        if (best === -1) {
          best = standing;
          chosen = i;
          continue;
        }
        if (standing > best) {
          best = standing;
          chosen = i;
        } else if (standing === best) {
          const held = room[chosen];
          if (
            entry.since < held.since ||
            (entry.since === held.since && entry.who < held.who)
          ) {
            chosen = i;
          }
        }
      }
      taken.push(room[chosen].who);
      room.splice(chosen, 1);
    } else {
      throw new Error("unknown moment kind: " + String(kind));
    }
  }
  return taken;
}
