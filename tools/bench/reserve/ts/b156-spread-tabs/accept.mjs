import assert from "node:assert/strict";
import { spreadTabs } from "./solution.ts";

assert.equal(spreadTabs("plain text", 4), "plain text", "text without tabs is unchanged");
assert.equal(spreadTabs("", 4), "", "empty text is unchanged");
assert.equal(spreadTabs("\tx", 4), "    x", "a leading tab reaches the first stop");
assert.equal(spreadTabs("a\tb", 4), "a   b", "a tab pads to the next stop");
assert.equal(spreadTabs("abcd\tz", 4), "abcd    z", "a tab on a stop jumps a full width");
assert.equal(spreadTabs("\t\tx", 2), "    x", "consecutive tabs each reach their own stop");
assert.equal(spreadTabs("ab\n\tz", 4), "ab\n    z", "a newline returns the column to zero");
assert.equal(spreadTabs("a\tb", 1), "a b", "width one pads a single space");
assert.throws(() => spreadTabs(42, 4), Error, "non-string text is rejected");
assert.throws(() => spreadTabs("a\tb", 0), Error, "zero width is rejected");
assert.throws(() => spreadTabs("a\tb", 2.5), Error, "fractional width is rejected");
assert.throws(() => spreadTabs("a\tb", "4"), Error, "non-number width is rejected");
console.log("ok");
