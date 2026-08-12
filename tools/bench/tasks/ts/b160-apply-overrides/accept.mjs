import assert from "node:assert/strict";
import { applyOverrides } from "./solution.ts";

assert.deepEqual(applyOverrides({ retries: "3" }, []), { retries: "3" }, "no overrides returns the base settings");
assert.deepEqual(applyOverrides({ host: "a", port: "80" }, ["port=8080"]), { host: "a", port: "8080" }, "an override replaces one setting");
assert.deepEqual(applyOverrides({ port: "80" }, ["port=1", "port=2"]), { port: "2" }, "a later override beats an earlier one");
assert.deepEqual(applyOverrides({ mode: "fast" }, ["mode="]), { mode: "" }, "an empty value is allowed");
assert.deepEqual(applyOverrides({ rule: "x" }, ["rule=a=b"]), { rule: "a=b" }, "only the first equals sign splits");
const base = { port: "80" };
applyOverrides(base, ["port=1"]);
assert.deepEqual(base, { port: "80" }, "base itself is left untouched");
assert.throws(() => applyOverrides({ a: "1" }, "a=2"), Error, "a non-list overrides argument is rejected");
assert.throws(() => applyOverrides({ a: "1" }, [7]), Error, "a non-string override is rejected");
assert.throws(() => applyOverrides({ port: "80" }, ["port"]), Error, "an override without an equals sign is rejected");
assert.throws(() => applyOverrides({ port: "80" }, ["=1"]), Error, "an empty override name is rejected");
assert.throws(() => applyOverrides({ port: "80" }, ["ghost=1"]), Error, "an unknown setting name is rejected");
console.log("ok");
