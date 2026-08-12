type JobReport = { state: string; pauses: number; jams: number; path: string[] };

const TRANSITIONS: Record<string, Record<string, string>> = {
  queued: { start: "printing", cancel: "cancelled" },
  printing: {
    pause: "paused",
    jam: "blocked",
    finish: "done",
    cancel: "cancelled",
  },
  paused: { resume: "printing", cancel: "cancelled" },
  blocked: { clear: "printing", cancel: "cancelled" },
  done: {},
  cancelled: {},
};

const EVENT_NAMES = new Set([
  "start",
  "pause",
  "resume",
  "jam",
  "clear",
  "finish",
  "cancel",
]);

export function tracePrintJob(events: string[], pauseLimit: number): JobReport {
  if (!Number.isInteger(pauseLimit) || pauseLimit < 0) {
    throw new Error("pause cap must be a non-negative integer");
  }
  let state = "queued";
  let pauses = 0;
  let jams = 0;
  const path: string[] = ["queued"];
  for (const event of events) {
    if (typeof event !== "string" || !EVENT_NAMES.has(event)) {
      throw new Error("unknown event: " + String(event));
    }
    const next = TRANSITIONS[state][event];
    if (next === undefined) {
      throw new Error("event " + event + " does not apply in state " + state);
    }
    if (event === "pause") {
      if (pauses === pauseLimit) {
        throw new Error("pause cap exhausted");
      }
      pauses += 1;
    }
    if (event === "jam") {
      jams += 1;
    }
    state = next;
    path.push(state);
  }
  return { state, pauses, jams, path };
}
