import assert from "node:assert/strict";
import { foldParcels } from "./solution.ts";

const ev = (type, parcel) => ({ type, parcel });

assert.deepEqual(foldParcels([]), {}, "no events, empty depot");

assert.deepEqual(
  foldParcels([
    ev("accept", "p1"),
    ev("accept", "p2"),
    ev("load", "p1"),
    ev("deliver", "p1"),
    ev("load", "p2"),
  ]),
  { p1: "delivered", p2: "in_transit" },
  "independent parcels fold independently"
);

assert.deepEqual(
  foldParcels([
    ev("accept", "a"),
    ev("load", "a"),
    ev("deliver", "a"),
    ev("bounce", "a"),
  ]),
  { a: "returned" },
  "full lifecycle to returned"
);

assert.deepEqual(
  foldParcels([ev("accept", "a"), ev("lose", "a")]),
  { a: "lost" },
  "an accepted parcel can be lost"
);

assert.deepEqual(
  foldParcels([ev("accept", "a"), ev("load", "a"), ev("lose", "a")]),
  { a: "lost" },
  "a parcel in transit can be lost"
);

assert.throws(
  () => foldParcels([ev("accept", "a"), ev("accept", "a")]),
  /1/,
  "re-accepting names the event index"
);

assert.throws(
  () => foldParcels([ev("load", "ghost")]),
  /0/,
  "an event for a parcel never accepted is an error"
);

assert.throws(
  () => foldParcels([ev("accept", "a"), ev("deliver", "a")]),
  /1/,
  "deliver straight from accepted is an invalid transition"
);

assert.throws(
  () =>
    foldParcels([
      ev("accept", "a"),
      ev("load", "a"),
      ev("deliver", "a"),
      ev("bounce", "a"),
      ev("load", "a"),
    ]),
  /4/,
  "a returned parcel admits nothing further"
);

assert.throws(
  () => foldParcels([ev("accept", "a"), ev("lose", "a"), ev("load", "a")]),
  /2/,
  "a lost parcel admits nothing further"
);

assert.throws(
  () => foldParcels([ev("accept", "a"), ev("teleport", "a")]),
  /1/,
  "an unknown type is an error naming its index"
);

console.log("ok");
