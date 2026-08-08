import assert from "node:assert/strict";
import { assignBerths } from "./solution.ts";

const dock = (boat, owner, size) => ({ op: "dock", boat, owner, size });
const leave = (boat) => ({ op: "leave", boat });

const twoBerths = [
  { id: "B1", size: 10 },
  { id: "B2", size: 4 },
];

assert.deepEqual(
  assignBerths(twoBerths, {}, [dock("Swan", "ann", 3)]),
  ["B1"],
  "first fit takes the first big-enough berth, not the snuggest"
);

assert.deepEqual(
  assignBerths(twoBerths, {}, [
    dock("Swan", "ann", 8),
    dock("Gull", "ann", 3),
    dock("Tern", "ann", 5),
  ]),
  ["B1", "B2", "rejected:no_berth"],
  "an occupied berth is skipped and an oversize boat is refused"
);

assert.deepEqual(
  assignBerths(twoBerths, { ann: 1 }, [
    dock("Swan", "ann", 3),
    dock("Gull", "ann", 3),
    leave("Swan"),
    dock("Gull", "ann", 3),
  ]),
  ["B1", "rejected:over_quota", "left", "B1"],
  "leaving releases both the berth and the owner's quota"
);

assert.deepEqual(
  assignBerths(twoBerths, { ann: 1 }, [
    dock("Swan", "ann", 3),
    dock("Swan", "ann", 3),
  ]),
  ["B1", "rejected:already_docked"],
  "already_docked outranks over_quota"
);

assert.deepEqual(
  assignBerths(twoBerths, {}, [leave("Ghost")]),
  ["rejected:not_docked"],
  "leaving while not docked is refused"
);

assert.deepEqual(
  assignBerths(twoBerths, { bob: 0 }, [dock("Skua", "bob", 1)]),
  ["rejected:over_quota"],
  "a zero quota holds nothing"
);

assert.throws(
  () => assignBerths(twoBerths, {}, [{ op: "paint", boat: "Swan" }]),
  Error,
  "an unknown op is an error"
);

assert.throws(
  () =>
    assignBerths(
      [
        { id: "B1", size: 5 },
        { id: "B1", size: 6 },
      ],
      {},
      []
    ),
  Error,
  "duplicate berth ids are an error"
);

console.log("ok");
