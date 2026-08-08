import assert from "node:assert/strict";
import { connectServices } from "./solution.ts";

const base = [
  { code: "S1", from: "A", to: "B", depart: 500, arrive: 530 },
  { code: "S2", from: "B", to: "C", depart: 545, arrive: 600 },
  { code: "S3", from: "A", to: "C", depart: 505, arrive: 650 },
  { code: "S4", from: "B", to: "C", depart: 535, arrive: 555 },
  { code: "S5", from: "C", to: "D", depart: 610, arrive: 640 },
];

assert.deepEqual(
  connectServices(base, "A", "C", 0, 10),
  { arrive: 600, legs: ["S1", "S2"] },
  "the tight change at 535 is unreachable with a ten minute minimum",
);
assert.deepEqual(
  connectServices(base, "A", "C", 0, 0),
  { arrive: 555, legs: ["S1", "S4"] },
  "with no minimum the tight change wins",
);
assert.deepEqual(
  connectServices(base, "A", "C", 502, 10),
  { arrive: 650, legs: ["S3"] },
  "readyAt rules out the 500 departure",
);
assert.deepEqual(
  connectServices(base, "A", "D", 0, 10),
  { arrive: 640, legs: ["S1", "S2", "S5"] },
  "a three service journey",
);
assert.deepEqual(
  connectServices(base, "A", "D", 0, 0),
  { arrive: 640, legs: ["S1", "S2", "S5"] },
  "equal arrivals and equal leg counts fall to the codes",
);
assert.deepEqual(
  connectServices(base, "D", "A", 0, 10),
  { arrive: -1, legs: [] },
  "nothing runs back from D",
);
assert.deepEqual(
  connectServices(base, "A", "C", 700, 10),
  { arrive: -1, legs: [] },
  "arriving after the last departure strands the traveller",
);
assert.deepEqual(
  connectServices([], "A", "C", 0, 0),
  { arrive: -1, legs: [] },
  "an empty timetable connects nothing",
);

const tied = [
  { code: "S1", from: "A", to: "B", depart: 500, arrive: 530 },
  { code: "S2", from: "B", to: "C", depart: 545, arrive: 600 },
  { code: "M9", from: "B", to: "C", depart: 545, arrive: 600 },
];
assert.deepEqual(
  connectServices(tied, "A", "C", 0, 10),
  { arrive: 600, legs: ["S1", "M9"] },
  "identical second legs are decided by the code",
);

const short = [
  { code: "D1", from: "X", to: "Y", depart: 100, arrive: 200 },
  { code: "E1", from: "X", to: "Z", depart: 100, arrive: 140 },
  { code: "E2", from: "Z", to: "Y", depart: 150, arrive: 200 },
];
assert.deepEqual(
  connectServices(short, "X", "Y", 0, 5),
  { arrive: 200, legs: ["D1"] },
  "a shared arrival prefers the journey with fewer services",
);

const looped = [
  { code: "L1", from: "P", to: "Q", depart: 10, arrive: 20 },
  { code: "L2", from: "Q", to: "P", depart: 30, arrive: 40 },
  { code: "L3", from: "P", to: "R", depart: 50, arrive: 60 },
];
assert.deepEqual(
  connectServices(looped, "P", "R", 0, 0),
  { arrive: 60, legs: ["L3"] },
  "a timetable that loops back does not trap the search",
);

assert.throws(
  () => connectServices("timetable", "A", "C", 0, 0),
  Error,
  "the timetable must be a list",
);
assert.throws(
  () => connectServices([{ code: "Z", from: "A", to: "B", depart: 1 }], "A", "B", 0, 0),
  Error,
  "a service missing arrive is rejected",
);
assert.throws(
  () =>
    connectServices(
      [
        { code: "Z", from: "A", to: "B", depart: 1, arrive: 2 },
        { code: "Z", from: "B", to: "C", depart: 3, arrive: 4 },
      ],
      "A",
      "C",
      0,
      0,
    ),
  Error,
  "two services sharing a code are rejected",
);
assert.throws(
  () => connectServices([{ code: "Z", from: "A", to: "B", depart: 9, arrive: 9 }], "A", "B", 0, 0),
  Error,
  "an arrival not later than the departure is rejected",
);
assert.throws(
  () => connectServices([{ code: "Z", from: "A", to: "A", depart: 1, arrive: 2 }], "A", "B", 0, 0),
  Error,
  "a service that sets down where it picked up is rejected",
);
assert.throws(
  () => connectServices(base, "A", "C", 0, -1),
  Error,
  "a negative minTransfer is rejected",
);
assert.throws(
  () => connectServices(base, "A", "C", 1.5, 0),
  Error,
  "a fractional readyAt is rejected",
);
assert.throws(
  () => connectServices(base, "A", "A", 0, 0),
  Error,
  "origin equal to destination is rejected",
);
assert.throws(
  () => connectServices(base, 42, "C", 0, 0),
  Error,
  "a non-string origin is rejected",
);
assert.throws(
  () => connectServices(base, "A", "", 0, 0),
  Error,
  "an empty destination is rejected",
);
console.log("ok");
