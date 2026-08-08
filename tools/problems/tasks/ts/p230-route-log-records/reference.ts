const LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"];

function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function routeLogRecords(
  rules: Array<Record<string, unknown>>,
  records: Array<Record<string, unknown>>,
  spare: string,
): Array<Record<string, unknown>> {
  if (!Array.isArray(rules)) throw new Error("the rules must be a list");
  if (!Array.isArray(records)) throw new Error("the records must be a list");
  if (typeof spare !== "string" || spare.length === 0) {
    throw new Error("the spare name must be a non-empty string");
  }
  const sinks: string[] = [];
  const floors: number[] = [];
  const tags: string[] = [];
  const halts: boolean[] = [];
  for (const rule of rules) {
    if (!isMapping(rule)) throw new Error("a rule must be a mapping");
    const sink = (rule as Record<string, unknown>).sink;
    const least = (rule as Record<string, unknown>).least;
    const tag = (rule as Record<string, unknown>).tag;
    const stop = (rule as Record<string, unknown>).stop;
    if (typeof sink !== "string" || sink.length === 0) {
      throw new Error("a sink must be a non-empty string");
    }
    if (typeof least !== "string" || !LEVELS.includes(least)) {
      throw new Error("a level must be one of the six names");
    }
    if (typeof tag !== "string") throw new Error("a tag must be a string");
    if (typeof stop !== "boolean") throw new Error("stop is either true or false");
    sinks.push(sink);
    floors.push(LEVELS.indexOf(least));
    tags.push(tag);
    halts.push(stop);
  }
  const routed: Array<Record<string, unknown>> = [];
  for (let at = 0; at < records.length; at++) {
    const record = records[at];
    if (!isMapping(record)) throw new Error("a record must be a mapping");
    const level = (record as Record<string, unknown>).level;
    const tag = (record as Record<string, unknown>).tag;
    if (typeof level !== "string" || !LEVELS.includes(level)) {
      throw new Error("a level must be one of the six names");
    }
    if (typeof tag !== "string") throw new Error("a tag must be a string");
    const rank = LEVELS.indexOf(level);
    const taken: string[] = [];
    const held = new Set<string>();
    for (let which = 0; which < sinks.length; which++) {
      if (rank < floors[which]) continue;
      if (tags[which] !== "" && tags[which] !== tag) continue;
      if (!held.has(sinks[which])) {
        held.add(sinks[which]);
        taken.push(sinks[which]);
      }
      if (halts[which]) break;
    }
    routed.push({ at, sinks: taken.length === 0 ? [spare] : taken });
  }
  return routed;
}
