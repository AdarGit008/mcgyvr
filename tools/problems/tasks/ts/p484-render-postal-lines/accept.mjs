import assert from "node:assert/strict";
import { renderPostalLines } from "./solution.ts";

const full = {
  who: "Ilva Renn",
  house: "12b",
  street: "Marl  Row",
  ward: "Upper Fen",
  town: "hesketh",
  code: "vk-4471",
};

assert.deepEqual(
  renderPostalLines(full, "vela"),
  ["Ilva Renn", "12b Marl Row", "vk-4471 HESKETH"],
  "vela writes three lines and shouts the town alone",
);
assert.deepEqual(
  renderPostalLines(full, "korrin"),
  ["ILVA RENN", "Marl Row 12b", "hesketh", "VK-4471"],
  "korrin puts the street before the house and shouts who and code",
);
assert.deepEqual(
  renderPostalLines(full, "mebis"),
  ["ILVA RENN", "UPPER FEN", "MARL ROW 12B", "HESKETH VK-4471"],
  "mebis writes the ward and shouts everything",
);

assert.deepEqual(
  renderPostalLines(
    { who: "  Orin  Kade ", house: " 4 ", street: "Low Gate", town: "  arden", code: "q7" },
    "vela",
  ),
  ["Orin Kade", "4 Low Gate", "q7 ARDEN"],
  "values are trimmed and inner blanks squeezed",
);

assert.deepEqual(
  renderPostalLines({ ...full, ward: "  ", note: "kept back" }, "korrin"),
  ["ILVA RENN", "Marl Row 12b", "hesketh", "VK-4471"],
  "a value korrin never writes is ignored even when blank, and so are strangers",
);

assert.deepEqual(
  renderPostalLines({ who: "a", house: "b", street: "c", ward: "d", town: "e", code: "f" }, "mebis"),
  ["A", "D", "C B", "E F"],
  "single letters shout the same way",
);

assert.throws(() => renderPostalLines("not a record", "vela"), Error, "entry must be a record");
assert.throws(() => renderPostalLines([full], "vela"), Error, "a list is not a record");
assert.throws(() => renderPostalLines(full, "nowhere"), Error, "an unknown region is rejected");
assert.throws(() => renderPostalLines(full, ""), Error, "an empty region is rejected");
assert.throws(
  () => renderPostalLines({ ...full, ward: "   " }, "mebis"),
  Error,
  "mebis needs the ward",
);
assert.throws(
  () => renderPostalLines({ who: "a", house: "b", street: "c", town: "e" }, "vela"),
  Error,
  "vela needs the code",
);
assert.throws(
  () => renderPostalLines({ ...full, house: 12 }, "vela"),
  Error,
  "a value that is not a string is missing",
);
assert.throws(
  () => renderPostalLines({ ...full, town: "" }, "korrin"),
  Error,
  "an empty town is missing",
);
console.log("ok");
