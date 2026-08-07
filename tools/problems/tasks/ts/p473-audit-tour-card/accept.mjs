import assert from "node:assert/strict";
import { auditTourCard } from "./solution.ts";

const floor = [
  { room: "Atlas", hop: 3, dwell: 9, merit: 4 },
  { room: "Bronze", hop: 2, dwell: 6, merit: 5 },
  { room: "Cameos", hop: 5, dwell: 4, merit: 2 },
  { room: "Drums", hop: 1, dwell: 7, merit: 6 },
];

assert.deepEqual(
  auditTourCard(floor, ["Atlas", "Bronze"], 30),
  { minutes: 20, merit: 9, spare: 10, ok: true },
  "a card that stops early never pays for the far end of the floor",
);

assert.deepEqual(
  auditTourCard(floor, [], 5),
  { minutes: 0, merit: 0, spare: 5, ok: true },
  "a blank card costs nothing at all",
);

assert.deepEqual(
  auditTourCard(floor, ["Drums"], 18),
  { minutes: 18, merit: 6, spare: 0, ok: true },
  "spending the allowance to the minute still sits within it",
);

assert.deepEqual(
  auditTourCard(floor, ["Atlas", "Bronze", "Cameos", "Drums"], 20),
  { minutes: 37, merit: 17, spare: -17, ok: false },
  "a card past the allowance reports how far past",
);

assert.deepEqual(
  auditTourCard(floor, ["Cameos"], 100),
  { minutes: 14, merit: 2, spare: 86, ok: true },
  "reaching one room deep pays for the doorways walked through",
);

assert.deepEqual(
  auditTourCard(floor, ["Atlas", "Drums"], 27),
  { minutes: 27, merit: 10, spare: 0, ok: true },
  "rooms skipped in the middle are still walked past",
);

assert.deepEqual(
  auditTourCard([{ room: "Solo", hop: 0, dwell: 1, merit: 0 }], [], 0),
  { minutes: 0, merit: 0, spare: 0, ok: true },
  "a blank card against no allowance is still within it",
);

assert.throws(
  () => auditTourCard("Atlas", [], 10),
  Error,
  "a rooms argument that is not a list is rejected",
);
assert.throws(
  () => auditTourCard(floor, "Atlas", 10),
  Error,
  "a card that is not a list is rejected",
);
assert.throws(
  () => auditTourCard(floor, ["Enamel"], 10),
  Error,
  "a card naming no room is rejected",
);
assert.throws(
  () => auditTourCard(floor, ["Atlas", "Atlas"], 10),
  Error,
  "a card repeating a name is rejected",
);
assert.throws(
  () => auditTourCard(floor, ["Bronze", "Atlas"], 10),
  Error,
  "a card out of floor-plan order is rejected",
);
assert.throws(
  () => auditTourCard(floor, [7], 10),
  Error,
  "a card entry that is not a string is rejected",
);
assert.throws(
  () => auditTourCard([{ room: "Atlas", hop: 1, dwell: 2 }], [], 10),
  Error,
  "a room missing a key is rejected",
);
assert.throws(
  () => auditTourCard([{ room: "Atlas", hop: -1, dwell: 2, merit: 0 }], [], 10),
  Error,
  "a hop below nought is rejected",
);
assert.throws(
  () => auditTourCard([{ room: "Atlas", hop: 1, dwell: 0, merit: 0 }], [], 10),
  Error,
  "a dwell below one is rejected",
);
assert.throws(
  () => auditTourCard([{ room: "Atlas", hop: 1, dwell: 2, merit: -1 }], [], 10),
  Error,
  "a merit below nought is rejected",
);
assert.throws(
  () =>
    auditTourCard(
      [
        { room: "Atlas", hop: 1, dwell: 2, merit: 0 },
        { room: "Atlas", hop: 1, dwell: 2, merit: 0 },
      ],
      [],
      10,
    ),
  Error,
  "a floor repeating a room name is rejected",
);
assert.throws(
  () => auditTourCard(floor, [], -4),
  Error,
  "an allowance below nought is rejected",
);
console.log("ok");
