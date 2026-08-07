const MOVES: Record<string, Record<string, string>> = {
  load: { accepted: "in_transit" },
  deliver: { in_transit: "delivered" },
  bounce: { delivered: "returned" },
  lose: { accepted: "lost", in_transit: "lost" },
};

export function foldParcels(
  events: Array<{ type: string; parcel: string }>
): Record<string, string> {
  const states: Record<string, string> = {};
  for (let i = 0; i < events.length; i++) {
    const { type, parcel } = events[i];
    if (type === "accept") {
      if (parcel in states) {
        throw new Error(`event ${i}: parcel already accepted`);
      }
      states[parcel] = "accepted";
      continue;
    }
    const moves = MOVES[type];
    if (moves === undefined) {
      throw new Error(`event ${i}: unknown type ${type}`);
    }
    if (!(parcel in states)) {
      throw new Error(`event ${i}: unknown parcel ${parcel}`);
    }
    const next = moves[states[parcel]];
    if (next === undefined) {
      throw new Error(
        `event ${i}: invalid transition ${type} from ${states[parcel]}`
      );
    }
    states[parcel] = next;
  }
  return states;
}
