import assert from "node:assert/strict";
import { pinPackageSet } from "./solution.ts";

const want = (name, from, under) => ({ name, from, under });
const plan = (shelf, needs, root) => ({ shelf, needs, root });
const pin = (name, version) => ({ name, version });

assert.deepEqual(
  pinPackageSet(plan({ g: ["1.0.0"] }, {}, [])),
  { picked: [], stuck: [] },
  "an application that asks for nothing settles nothing"
);
assert.deepEqual(
  pinPackageSet(
    plan({ a: ["1.0.0", "1.2.0", "2.0.0"] }, {}, [want("a", "1.0.0", "3.0.0")])
  ),
  { picked: [pin("a", "1.2.0")], stuck: [] },
  "the oldest generation still allowed, at its freshest build"
);
assert.deepEqual(
  pinPackageSet(
    plan({ h: ["1.2.0", "1.2.7", "1.2.3"] }, {}, [want("h", "1.0.0", "2.0.0")])
  ),
  { picked: [pin("h", "1.2.7")], stuck: [] },
  "the third group breaks a tie on the first two"
);
assert.deepEqual(
  pinPackageSet(
    plan({ a: ["1.0.0"], b: ["2.0.0", "2.1.0"] }, { a: [want("b", "2.0.0", "3.0.0")] }, [
      want("a", "1.0.0", "2.0.0"),
    ])
  ),
  { picked: [pin("a", "1.0.0"), pin("b", "2.1.0")], stuck: [] },
  "a settled package drags its own wants in"
);
assert.deepEqual(
  pinPackageSet(
    plan(
      { a: ["1.0.0"], b: ["1.0.0", "1.5.0", "2.0.0"] },
      { a: [want("b", "1.5.0", "3.0.0")] },
      [want("a", "1.0.0", "2.0.0"), want("b", "1.0.0", "2.0.0")]
    )
  ),
  { picked: [pin("a", "1.0.0"), pin("b", "1.5.0")], stuck: [] },
  "two windows on one package must both hold"
);
assert.deepEqual(
  pinPackageSet(
    plan({ g: ["1.0.0", "2.0.0", "2.3.0"] }, {}, [
      want("g", "1.0.0", "3.0.0"),
      want("g", "2.0.0", "3.0.0"),
    ])
  ),
  { picked: [pin("g", "2.3.0")], stuck: [] },
  "a floor from one want lifts the whole choice"
);
assert.deepEqual(
  pinPackageSet(plan({ c: ["1.0.0"] }, {}, [want("c", "2.0.0", "3.0.0")])),
  { picked: [], stuck: ["c"] },
  "a window nothing on the shelf satisfies is stuck"
);
assert.deepEqual(
  pinPackageSet(
    plan({ d: ["1.0.0"], e: ["1.0.0"] }, { d: [want("e", "1.0.0", "2.0.0")] }, [
      want("d", "5.0.0", "6.0.0"),
    ])
  ),
  { picked: [pin("e", "1.0.0")], stuck: ["d"] },
  "a stuck package still drags its wants in"
);
assert.deepEqual(
  pinPackageSet(
    plan(
      { a: ["1.0.0"], b: ["1.0.0"] },
      { a: [want("b", "1.0.0", "2.0.0")], b: [want("a", "1.0.0", "2.0.0")] },
      [want("a", "1.0.0", "2.0.0")]
    )
  ),
  { picked: [pin("a", "1.0.0"), pin("b", "1.0.0")], stuck: [] },
  "wants that point at each other still finish"
);
assert.deepEqual(
  pinPackageSet(
    plan({ k: ["9.0.0", "10.1.0"] }, {}, [want("k", "1.0.0", "11.0.0")])
  ),
  { picked: [pin("k", "9.0.0")], stuck: [] },
  "groups compare as numbers, not as text"
);

assert.throws(() => pinPackageSet([1, 2]), Error, "a plan that is not a mapping is rejected");
assert.throws(
  () => pinPackageSet({ shelf: [], needs: {}, root: [] }),
  Error,
  "a shelf that is not a mapping is rejected"
);
assert.throws(
  () => pinPackageSet({ shelf: { a: ["1.0.0"] }, needs: [], root: [] }),
  Error,
  "needs that is not a mapping is rejected"
);
assert.throws(
  () => pinPackageSet({ shelf: { a: ["1.0.0"] }, needs: {}, root: {} }),
  Error,
  "a root that is not a list is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: [] }, {}, [])),
  Error,
  "an empty shelf entry is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.2"] }, {}, [])),
  Error,
  "a version of two groups is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["01.2.0"] }, {}, [])),
  Error,
  "a leading zero is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0", "1.0.0"] }, {}, [])),
  Error,
  "a repeated version is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0"] }, { z: [] }, [])),
  Error,
  "needs keyed by an unstocked package is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0"] }, {}, ["a"])),
  Error,
  "a want that is not a mapping is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0"] }, {}, [want("zz", "1.0.0", "2.0.0")])),
  Error,
  "a want on an unstocked package is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0"] }, {}, [want("a", "2.0.0", "1.0.0")])),
  Error,
  "a window that runs backwards is rejected"
);
assert.throws(
  () => pinPackageSet(plan({ a: ["1.0.0"] }, {}, [want("a", "1.0.0", "1.0.0")])),
  Error,
  "an empty window is rejected"
);

console.log("ok");
