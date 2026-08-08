const KINDS = ["HELLO", "OFFER", "CHOOSE", "ACCEPT", "DATA", "BYE"];

function step(state: number, side: string, kind: string): number {
  if (state === 0 && side === "client" && kind === "HELLO") return 1;
  if (state === 1 && side === "server" && kind === "OFFER") return 2;
  if (state === 2 && side === "client" && kind === "CHOOSE") return 3;
  if (state === 3 && side === "server" && kind === "ACCEPT") return 4;
  if (state === 4 && side === "client" && kind === "DATA") return 5;
  if (state === 4 && side === "client" && kind === "BYE") return 6;
  if (state === 5 && side === "server" && kind === "DATA") return 4;
  if (state === 6 && side === "server" && kind === "BYE") return 7;
  return -1;
}

export function firstBadMessage(exchange: unknown): number {
  if (!Array.isArray(exchange) || exchange.length === 0) {
    throw new Error("the exchange must be a non-empty list");
  }
  let state = 0;
  for (let index = 0; index < exchange.length; index++) {
    const raw = exchange[index];
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a message must be a mapping");
    }
    const message = raw as Record<string, unknown>;
    const side = message.from;
    const kind = message.kind;
    if (side !== "client" && side !== "server") {
      throw new Error("a message must come from the client or the server");
    }
    if (typeof kind !== "string" || !KINDS.includes(kind)) {
      throw new Error("a message kind must be one of the six names");
    }
    const moved = step(state, side, kind);
    if (moved === -1) {
      return index;
    }
    state = moved;
  }
  return state === 7 ? -1 : exchange.length;
}
