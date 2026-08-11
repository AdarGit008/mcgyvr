import assert from "node:assert/strict";
import { chartDepths } from "./solution.ts";

assert.deepEqual(chartDepths({ vera: "" }), { vera: 0 }, "the chief sits on rung zero");
assert.deepEqual(chartDepths({ vera: "", omar: "vera" }), { vera: 0, omar: 1 }, "a direct report sits one above");
assert.deepEqual(chartDepths({ ines: "omar", omar: "vera", vera: "" }), { ines: 2, omar: 1, vera: 0 }, "a chain listed upside down still measures");
assert.deepEqual(
  chartDepths({ vera: "", omar: "vera", ines: "vera", kip: "ines", lena: "kip" }),
  { vera: 0, omar: 1, ines: 1, kip: 2, lena: 3 },
  "separate branches keep their own rungs",
);
assert.deepEqual(chartDepths({}), {}, "an empty chart has no rungs");
assert.throws(() => chartDepths({ omar: "ghost" }), Error, "answering to an unlisted member is rejected");
assert.throws(() => chartDepths({ omar: "ines", ines: "omar" }), Error, "a chart that circles back is rejected");
console.log("ok");
