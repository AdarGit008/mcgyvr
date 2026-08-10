import assert from "node:assert/strict";
import { tracePrintJob } from "./solution.ts";

assert.deepEqual(
  tracePrintJob([], 0),
  { state: "queued", pauses: 0, jams: 0, path: ["queued"] },
  "no events leaves the job queued",
);
assert.deepEqual(
  tracePrintJob(["start"], 0),
  { state: "printing", pauses: 0, jams: 0, path: ["queued", "printing"] },
  "start moves to printing",
);
assert.deepEqual(
  tracePrintJob(["start", "finish"], 0),
  { state: "done", pauses: 0, jams: 0, path: ["queued", "printing", "done"] },
  "a clean run finishes",
);
assert.deepEqual(
  tracePrintJob(["start", "pause"], 1),
  { state: "paused", pauses: 1, jams: 0, path: ["queued", "printing", "paused"] },
  "pause is counted",
);
assert.deepEqual(
  tracePrintJob(["start", "pause", "resume"], 1),
  {
    state: "printing",
    pauses: 1,
    jams: 0,
    path: ["queued", "printing", "paused", "printing"],
  },
  "resume returns to printing",
);
assert.deepEqual(
  tracePrintJob(["start", "jam", "clear", "finish"], 0),
  {
    state: "done",
    pauses: 0,
    jams: 1,
    path: ["queued", "printing", "blocked", "printing", "done"],
  },
  "a jam is cleared and counted",
);
assert.deepEqual(
  tracePrintJob(["cancel"], 0),
  { state: "cancelled", pauses: 0, jams: 0, path: ["queued", "cancelled"] },
  "cancel applies while queued",
);
assert.deepEqual(
  tracePrintJob(["start", "jam", "cancel"], 0),
  {
    state: "cancelled",
    pauses: 0,
    jams: 1,
    path: ["queued", "printing", "blocked", "cancelled"],
  },
  "cancel applies while blocked",
);
assert.throws(() => tracePrintJob(["eject"], 0), Error, "unknown event");
assert.throws(() => tracePrintJob(["finish"], 0), Error, "finish before start");
assert.throws(
  () => tracePrintJob(["start", "finish", "start"], 0),
  Error,
  "no event applies after done",
);
assert.throws(
  () => tracePrintJob(["start", "pause", "resume", "pause"], 1),
  Error,
  "pause past the cap",
);
assert.throws(() => tracePrintJob([42], 0), Error, "non-string event");
assert.throws(() => tracePrintJob(["start"], 1.5), Error, "fractional pause cap");
console.log("ok");
