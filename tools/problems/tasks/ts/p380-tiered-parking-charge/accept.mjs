import assert from "node:assert/strict";
import { tieredParkingCharge } from "./solution.ts";

const stepped = {
  tiers: [{ upTo: 60, rate: 5 }, { upTo: 180, rate: 3 }, { upTo: null, rate: 1 }],
  cap: 1000,
  dayStart: 0,
  grace: 15,
};
const freeHalfHour = {
  tiers: [{ upTo: 30, rate: 0 }, { upTo: null, rate: 2 }],
  cap: null,
  dayStart: 0,
  grace: 0,
};
const noonTurn = {
  tiers: [{ upTo: null, rate: 1 }],
  cap: 100,
  dayStart: 720,
  grace: 0,
};
const dawnTurn = {
  tiers: [{ upTo: 60, rate: 5 }, { upTo: 180, rate: 3 }, { upTo: null, rate: 1 }],
  cap: 1000,
  dayStart: 360,
  grace: 0,
};

assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 10 }),
  { days: [], capped: [], cents: 0 },
  "a stay inside the grace costs nothing",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 15 }),
  { days: [], capped: [], cents: 0 },
  "a stay exactly the grace still costs nothing",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 16 }),
  { days: [80], capped: [], cents: 80 },
  "one minute past the grace and every minute is paid for",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 60 }),
  { days: [300], capped: [], cents: 300 },
  "the first tier filled exactly",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 61 }),
  { days: [303], capped: [], cents: 303 },
  "the next minute is charged at the second tier",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 200 }),
  { days: [680], capped: [], cents: 680 },
  "the open tier takes what is left",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 1440 }),
  { days: [1000], capped: [0], cents: 1000 },
  "a whole day runs into the cap",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 1380, stay: 120 }),
  { days: [300, 300], capped: [], cents: 600 },
  "a stay across the turnover numbers each side afresh from one",
);
assert.deepEqual(
  tieredParkingCharge(stepped, { entry: 0, stay: 3000 }),
  { days: [1000, 1000, 480], capped: [0, 1], cents: 2480 },
  "three charging days, the two full ones trimmed",
);
assert.deepEqual(
  tieredParkingCharge(freeHalfHour, { entry: 0, stay: 30 }),
  { days: [0], capped: [], cents: 0 },
  "a tier priced at nothing charges nothing",
);
assert.deepEqual(
  tieredParkingCharge(freeHalfHour, { entry: 0, stay: 100 }),
  { days: [140], capped: [], cents: 140 },
  "only the minutes past that tier are paid for",
);
assert.deepEqual(
  tieredParkingCharge(noonTurn, { entry: 700, stay: 60 }),
  { days: [20, 40], capped: [], cents: 60 },
  "a turnover at noon splits a stay that straddles it",
);
assert.deepEqual(
  tieredParkingCharge(noonTurn, { entry: 0, stay: 1440 }),
  { days: [100, 100], capped: [0, 1], cents: 200 },
  "a full midnight-to-midnight stay touches two charging days here",
);
assert.deepEqual(
  tieredParkingCharge(dawnTurn, { entry: 300, stay: 120 }),
  { days: [300, 300], capped: [], cents: 600 },
  "arriving before the turnover puts the earlier half in the day behind",
);

const rejects = (tariff, ticket) => {
  try {
    tieredParkingCharge(tariff, ticket);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects({ ...stepped, tiers: [] }, { entry: 0, stay: 60 }), "an empty tier list is refused");
assert.ok(
  rejects({ ...stepped, tiers: [{ upTo: 60, rate: 5 }] }, { entry: 0, stay: 60 }),
  "a tier list with no open tier is refused",
);
assert.ok(
  rejects({ ...stepped, tiers: [{ upTo: null, rate: 1 }, { upTo: 60, rate: 5 }] }, { entry: 0, stay: 60 }),
  "an open tier that is not last is refused",
);
assert.ok(
  rejects({ ...stepped, tiers: [{ upTo: 60, rate: 5 }, { upTo: 60, rate: 3 }, { upTo: null, rate: 1 }] }, { entry: 0, stay: 60 }),
  "stated minutes that do not climb are refused",
);
assert.ok(
  rejects({ ...stepped, tiers: [{ upTo: 60, rate: -1 }, { upTo: null, rate: 1 }] }, { entry: 0, stay: 60 }),
  "a rate below nothing is refused",
);
assert.ok(rejects({ ...stepped, cap: -5 }, { entry: 0, stay: 60 }), "a cap below nothing is refused");
assert.ok(rejects({ ...stepped, dayStart: 1440 }, { entry: 0, stay: 60 }), "a dayStart of 1440 is refused");
assert.ok(rejects({ ...stepped, grace: -1 }, { entry: 0, stay: 60 }), "a grace below nothing is refused");
assert.ok(rejects(stepped, { entry: -1, stay: 60 }), "an entry below nothing is refused");
assert.ok(rejects(stepped, { entry: 0, stay: 0 }), "a stay of no minutes is refused");
assert.ok(rejects(stepped, { entry: 0, stay: 20161 }), "a stay past the ceiling is refused");
assert.ok(rejects(stepped, { entry: 0, stay: 60.5 }), "a fractional stay is refused");
assert.ok(rejects("tariff", { entry: 0, stay: 60 }), "a tariff that is not a mapping is refused");
console.log("ok");
