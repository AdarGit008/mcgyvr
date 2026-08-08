/** The first record of a link setup that departs from the drill. */
const VERBS = ["PROBE", "READY", "KEY", "SEAL", "PING", "PONG", "CLOSE"];

export function auditLinkSetup(exchange: Record<string, unknown>[]): string {
  if (!Array.isArray(exchange) || exchange.length === 0) {
    throw new Error("the list must be a non-empty list");
  }
  let stage = 0;
  let carried = 0;
  for (let index = 0; index < exchange.length; index++) {
    const raw = exchange[index];
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a record must be a mapping");
    }
    const record = raw as Record<string, unknown>;
    const side = record.side;
    const verb = record.verb;
    const seq = record.seq;
    if (side !== "caller" && side !== "listener") {
      throw new Error("a record must come from the caller or the listener");
    }
    if (typeof verb !== "string" || !VERBS.includes(verb)) {
      throw new Error("a verb must be one of the seven");
    }
    if (typeof seq !== "number" || !Number.isInteger(seq)) {
      throw new Error("a seq must be a whole number");
    }
    const fault = verb + "@" + (index + 1);
    if (stage === 0) {
      if (side !== "caller" || verb !== "PROBE" || seq !== 1) return fault;
      carried = seq;
      stage = 1;
    } else if (stage === 1) {
      if (side !== "listener" || verb !== "READY" || seq !== carried) return fault;
      stage = 2;
    } else if (stage === 2) {
      if (side !== "caller" || verb !== "KEY" || seq !== carried + 1) return fault;
      carried = seq;
      stage = 3;
    } else if (stage === 3) {
      if (side !== "listener" || verb !== "SEAL" || seq !== carried) return fault;
      stage = 4;
    } else if (stage === 4) {
      if (side !== "caller" || seq !== carried + 1) return fault;
      if (verb === "PING") {
        carried = seq;
        stage = 5;
      } else if (verb === "CLOSE") {
        carried = seq;
        stage = 6;
      } else {
        return fault;
      }
    } else if (stage === 5) {
      if (side !== "listener" || verb !== "PONG" || seq !== carried) return fault;
      stage = 4;
    } else if (stage === 6) {
      if (side !== "listener" || verb !== "CLOSE" || seq !== carried) return fault;
      stage = 7;
    } else {
      return fault;
    }
  }
  return stage === 7 ? "" : "short";
}
