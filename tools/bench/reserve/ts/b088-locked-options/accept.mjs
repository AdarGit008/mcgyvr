import assert from "node:assert/strict";
import { settleOptions } from "./solution.ts";

assert.deepEqual(settleOptions({ mode: "dev" }, {}, {}, []), { mode: "dev" }, "defaults pass through");
assert.deepEqual(
  settleOptions({ retries: "1" }, { retries: "4" }, {}, []),
  { retries: "4" },
  "the file beats defaults",
);
assert.deepEqual(
  settleOptions({ level: "a" }, { level: "b" }, { level: "c" }, []),
  { level: "c" },
  "a flag beats the file",
);
assert.deepEqual(
  settleOptions({ a: "1" }, { b: "2" }, { c: "3" }, []),
  { a: "1", b: "2", c: "3" },
  "disjoint keys all survive",
);
assert.deepEqual(
  settleOptions({ port: "80" }, { port: "8080" }, {}, ["port"]),
  { port: "8080" },
  "the file may still set a locked key",
);
assert.deepEqual(
  settleOptions({ port: "80" }, {}, { host: "far" }, ["port"]),
  { port: "80", host: "far" },
  "a lock only guards its own key",
);
assert.deepEqual(settleOptions({}, {}, {}, []), {}, "nothing in, nothing out");
assert.throws(() => settleOptions({}, {}, { port: "1" }, ["port"]), Error, "flag on a locked key is rejected");
assert.throws(() => settleOptions(null, {}, {}, []), Error, "a missing source is rejected");
assert.throws(() => settleOptions({}, ["x"], {}, []), Error, "a list source is rejected");
assert.throws(() => settleOptions({ a: 5 }, {}, {}, []), Error, "a numeric value is rejected");
assert.throws(() => settleOptions({}, {}, {}, [7]), Error, "a non-string lock is rejected");
console.log("ok");
