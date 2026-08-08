function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function foldSessionOverruns(
  runsheet: Record<string, unknown>[],
  wall: number,
): Record<string, unknown> {
  if (!whole(wall) || wall < 1) {
    throw new Error("the wall is not whole or falls below one");
  }
  if (!Array.isArray(runsheet)) {
    throw new Error("foldSessionOverruns expects a list of entries");
  }

  const named = new Set<string>();
  for (const entry of runsheet) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("an entry is not a record");
    }
    if (Object.keys(entry).sort().join(",") !== "pause,ran,slot,speaker") {
      throw new Error("an entry's keys are not exactly the four named");
    }
    const speaker = entry["speaker"];
    if (typeof speaker !== "string" || speaker.length === 0) {
      throw new Error("a speaker is not a non-empty string");
    }
    if (named.has(speaker)) {
      throw new Error("two entries name one speaker");
    }
    named.add(speaker);
    if (!whole(entry["slot"]) || Number(entry["slot"]) < 1) {
      throw new Error("a slot is not whole or falls below one");
    }
    if (!whole(entry["ran"]) || Number(entry["ran"]) < 0) {
      throw new Error("a ran is not whole or falls below nought");
    }
    if (!whole(entry["pause"]) || Number(entry["pause"]) < 0) {
      throw new Error("a pause is not whole or falls below nought");
    }
  }

  const lines: string[] = [];
  const spill: string[] = [];
  let clock = 0;
  let finish = 0;

  for (const entry of runsheet) {
    const speaker = String(entry["speaker"]);
    const ran = Number(entry["ran"]);
    const slot = Number(entry["slot"]);
    const pause = Number(entry["pause"]);

    if (clock >= wall) {
      spill.push(speaker);
      continue;
    }
    const start = clock;
    let end = start + ran;
    let mark = "full";
    if (end > wall) {
      end = wall;
      mark = "cut";
    }
    lines.push(`${speaker} ${start} ${end} ${mark}`);
    finish = end;
    const beyond = ran > slot ? ran - slot : 0;
    clock = end + Math.max(0, pause - beyond);
  }

  return { lines, spill, finish };
}
