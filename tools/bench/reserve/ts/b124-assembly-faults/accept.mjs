import assert from "node:assert/strict";
import { runAssembly } from "./solution.ts";

assert.deepEqual(
  runAssembly({ bolt: 6, panel: 2, gear: 1 }, [
    ["frame", { bolt: 2, panel: 1 }, false],
    ["door", { panel: 1, bolt: 1 }, false],
  ]),
  {
    built: ["frame", "door"],
    faults: [],
    halted: null,
    leftover: [["bolt", 3], ["gear", 1], ["panel", 0]],
  },
  "a clean run builds every step",
);
assert.deepEqual(
  runAssembly({ bolt: 3, panel: 1 }, [
    ["frame", { bolt: 2, panel: 2 }, false],
    ["lid", { bolt: 3 }, false],
  ]),
  {
    built: ["lid"],
    faults: [["frame", "panel"]],
    halted: null,
    leftover: [["bolt", 0], ["panel", 1]],
  },
  "a faulted step consumes nothing, so later steps still draw stock",
);
assert.deepEqual(
  runAssembly({ cell: 2 }, [
    ["pack", { cell: 3 }, true],
    ["trim", {}, false],
  ]),
  {
    built: [],
    faults: [["pack", "cell"]],
    halted: "pack",
    leftover: [["cell", 2]],
  },
  "a critical fault halts before later steps run",
);
assert.deepEqual(
  runAssembly({ axle: 1, bolt: 0, arm: 0 }, [
    ["cart", { bolt: 2, arm: 1, axle: 1 }, false],
  ]),
  {
    built: [],
    faults: [["cart", "arm"]],
    halted: null,
    leftover: [["arm", 0], ["axle", 1], ["bolt", 0]],
  },
  "the fault names the alphabetically first short part",
);
assert.deepEqual(
  runAssembly({}, [["poll", {}, false]]),
  { built: ["poll"], faults: [], halted: null, leftover: [] },
  "a step needing nothing always builds",
);
assert.deepEqual(
  runAssembly({ nut: 4 }, []),
  { built: [], faults: [], halted: null, leftover: [["nut", 4]] },
  "an empty plan leaves the bins alone",
);
assert.deepEqual(
  runAssembly({ rod: 4 }, [
    ["a1", { rod: 2 }, false],
    ["a2", { rod: 2 }, false],
    ["a3", { rod: 1 }, false],
  ]),
  {
    built: ["a1", "a2"],
    faults: [["a3", "rod"]],
    halted: null,
    leftover: [["rod", 0]],
  },
  "stock drains to exactly zero, then the next draw faults",
);
assert.deepEqual(
  runAssembly({ pin: 2 }, [
    ["core", { pin: 1 }, true],
    ["rim", { pin: 1 }, false],
  ]),
  { built: ["core", "rim"], faults: [], halted: null, leftover: [["pin", 0]] },
  "a critical step that succeeds does not halt",
);
assert.deepEqual(
  runAssembly({ cap: 1 }, [
    ["c1", { cap: 2 }, false],
    ["c2", { cap: 3 }, false],
  ]),
  {
    built: [],
    faults: [["c1", "cap"], ["c2", "cap"]],
    halted: null,
    leftover: [["cap", 1]],
  },
  "non-critical faults accumulate in order",
);
assert.throws(() => runAssembly({ bolt: -1 }, []), Error, "negative stock");
assert.throws(() => runAssembly({ "": 2 }, []), Error, "empty bin name");
assert.throws(() => runAssembly({ bolt: 1 }, [["s", { bolt: 1 }]]), Error, "two-item step");
assert.throws(() => runAssembly({ bolt: 1 }, [["", { bolt: 1 }, false]]), Error, "empty step name");
assert.throws(() => runAssembly({ bolt: 1 }, [["s", { screw: 1 }, false]]), Error, "unknown part");
assert.throws(() => runAssembly({ bolt: 1 }, [["s", { bolt: 0 }, false]]), Error, "zero needed count");
assert.throws(() => runAssembly({ bolt: 1 }, [["s", { bolt: 1 }, "yes"]]), Error, "non-boolean critical flag");
console.log("ok");
