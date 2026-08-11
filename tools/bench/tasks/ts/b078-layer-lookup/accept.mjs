import assert from "node:assert/strict";
import { configValue } from "./solution.ts";

assert.equal(configValue(["port=8080"], "port"), "8080", "a single layer supplies the value");
assert.equal(configValue(["port=8080\nhost=web", "port=9090"], "port"), "9090", "the later layer wins");
assert.equal(configValue(["mode=fast", "!mode"], "mode"), null, "a later unset hides the value");
assert.equal(configValue(["# port=off\n  host =  local  "], "host"), "local", "comments are skipped and whitespace is trimmed");
assert.equal(configValue(["flag="], "flag"), "", "an empty value is a value, not an unset");
assert.throws(() => configValue(["port=8080"], 7), Error, "non-string name is rejected");
assert.throws(() => configValue(["port=8080"], ""), Error, "empty name is rejected");
assert.throws(() => configValue([42], "port"), Error, "non-string layer is rejected");
assert.throws(() => configValue(["just a word"], "port"), Error, "a line with no equals sign is rejected");
console.log("ok");
