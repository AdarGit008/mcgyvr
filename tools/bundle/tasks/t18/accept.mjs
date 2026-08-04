import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { EventLog } from "./solution.ts";

const log = new EventLog();
assert.deepEqual(log.since(0), [], "a fresh log is empty");
log.record({ name: "start", timestamp: 10 });
log.record({ name: "tick", timestamp: 20 });
log.record({ name: "stop", timestamp: 30 });

assert.deepEqual(
  log.since(20).map((event) => event.name),
  ["tick", "stop"],
  "at or after the timestamp, in insertion order",
);
assert.equal(log.since(31).length, 0, "nothing after the last event");
assert.equal(log.since(0).length, 3, "everything from the beginning");
assert.deepEqual(log.since(10)[0], { name: "start", timestamp: 10 }, "the bound is inclusive");

const source = readFileSync(new URL("./solution.ts", import.meta.url), "utf8");
assert.ok(/export\s+(interface|type)\s+Event\b/.test(source), "Event must be exported");
assert.ok(/timestamp\s*:\s*number/.test(source), "timestamp must be typed number");
assert.ok(/name\s*:\s*string/.test(source), "name must be typed string");
assert.ok(/:\s*Event\[\]/.test(source), "the field or return must be annotated `Event[]`");
assert.ok(!/Array<\s*Event\s*>/.test(source), "use `Event[]`, not `Array<Event>`");
assert.ok(/record\s*\(\s*event\s*:\s*Event\s*\)/.test(source), "record must type its parameter");
