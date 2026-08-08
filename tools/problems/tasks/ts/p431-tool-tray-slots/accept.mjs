import assert from "node:assert/strict";
import { foldToolTray } from "./solution.ts";

const touch = (name) => ["touch", name];
const pin = (name) => ["pin", name];
const drop = (name) => ["drop", name];

assert.deepEqual(foldToolTray(2, []), [], "no actions leaves the tray empty");
assert.deepEqual(foldToolTray(2, [touch("a"), touch("b")]), ["b", "a"], "the tray reads newest touch first");
assert.deepEqual(
  foldToolTray(2, [touch("a"), touch("b"), touch("a")]),
  ["a", "b"],
  "touching a held entry only refreshes it",
);
assert.deepEqual(
  foldToolTray(2, [touch("a"), touch("b"), touch("c")]),
  ["c", "b"],
  "a full tray turns out its oldest touch",
);
assert.deepEqual(
  foldToolTray(2, [touch("a"), pin("a"), touch("b"), touch("c")]),
  ["c", "*a"],
  "a pinned entry is passed over when room is made",
);
assert.deepEqual(
  foldToolTray(1, [touch("a"), pin("a"), touch("b")]),
  ["*a"],
  "a tray of nothing but pins refuses the touch",
);
assert.deepEqual(
  foldToolTray(3, [touch("a"), touch("b"), touch("a"), touch("c"), touch("d")]),
  ["d", "c", "a"],
  "a refreshed entry outlives one touched earlier",
);
assert.deepEqual(
  foldToolTray(2, [touch("a"), pin("a"), pin("a"), touch("b")]),
  ["b", "*a"],
  "pinning twice changes nothing",
);
assert.deepEqual(
  foldToolTray(2, [touch("a"), pin("a"), drop("a"), touch("b"), touch("c")]),
  ["c", "b"],
  "a drop turns out a pinned entry too",
);
assert.deepEqual(foldToolTray(2, [pin("z"), touch("a")]), ["a"], "pinning a name the tray lacks changes nothing");
assert.deepEqual(foldToolTray(2, [touch("a"), drop("z")]), ["a"], "dropping a name the tray lacks changes nothing");
assert.deepEqual(
  foldToolTray(3, [touch("a"), touch("b"), pin("b"), touch("c"), touch("d"), touch("e")]),
  ["e", "d", "*b"],
  "a longer replay keeps the pin through two turnings out",
);
assert.deepEqual(
  foldToolTray(2, [touch("a"), pin("a"), touch("b"), pin("b"), drop("a"), touch("c")]),
  ["c", "*b"],
  "dropping a pin frees the slot the refused touch wanted",
);

assert.throws(() => foldToolTray(0, []), Error, "a slots figure under 1 is refused");
assert.throws(() => foldToolTray(2.5, []), Error, "a fractional slots figure is refused");
assert.throws(() => foldToolTray("2", []), Error, "a slots figure that is not a number is refused");
assert.throws(() => foldToolTray(2, [["touch"]]), Error, "an action that is not a pair is refused");
assert.throws(() => foldToolTray(2, [["poke", "a"]]), Error, "an unknown verb is refused");
assert.throws(() => foldToolTray(2, [["touch", ""]]), Error, "an empty name is refused");
assert.throws(() => foldToolTray(2, [["touch", "*a"]]), Error, "a name carrying an asterisk is refused");
assert.throws(() => foldToolTray(2, [["touch", 5]]), Error, "a name that is not a string is refused");
console.log("ok");
