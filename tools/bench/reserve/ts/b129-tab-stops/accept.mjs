import assert from "node:assert/strict";
import { renderTabbed } from "./solution.ts";

assert.equal(renderTabbed("total", [[8, "left"]]), "total", "no tabs, no change");
assert.equal(renderTabbed("id\tname", [[6, "left"]]), "id    name", "a left stop pads to its column");
assert.equal(
  renderTabbed("a\tbb\tccc", [[4, "left"], [10, "left"]]),
  "a   bb    ccc",
  "successive pieces take successive stops",
);
assert.equal(renderTabbed("item\t42", [[9, "right"]]), "item   42", "a right stop ends the piece at its column");
assert.equal(
  renderTabbed("lineup\t88", [[4, "left"], [12, "right"]]),
  "lineup    88",
  "a stop already passed is skipped over",
);
assert.equal(
  renderTabbed("ledger\t123456", [[8, "right"]]),
  "ledger 123456",
  "a right piece too wide falls back to one space",
);
assert.equal(renderTabbed("totals\tdue", [[4, "left"]]), "totals due", "no stop left falls back to one space");
assert.equal(renderTabbed("a\t\tb", [[3, "left"], [6, "left"]]), "a     b", "an empty piece still advances");
assert.equal(renderTabbed("\ttitle", [[5, "left"]]), "     title", "a leading tab indents the first piece");
assert.equal(renderTabbed("", []), "", "an empty line stays empty");
assert.throws(() => renderTabbed(42, []), Error, "a non-string line is rejected");
assert.throws(() => renderTabbed("a\nb", []), Error, "a newline in the line is rejected");
assert.throws(() => renderTabbed("a", "nope"), Error, "non-list stops are rejected");
assert.throws(() => renderTabbed("a", [[4]]), Error, "a one-item stop is rejected");
assert.throws(() => renderTabbed("a", [[0, "left"]]), Error, "a zero column is rejected");
assert.throws(() => renderTabbed("a", [[4, "center"]]), Error, "an unknown kind is rejected");
assert.throws(
  () => renderTabbed("a", [[6, "left"], [4, "right"]]),
  Error,
  "non-increasing columns are rejected",
);
console.log("ok");
