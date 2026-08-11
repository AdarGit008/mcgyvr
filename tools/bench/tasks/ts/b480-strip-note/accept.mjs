import assert from "node:assert/strict";
import { stripNote } from "./solution.ts";

assert.equal(stripNote("Report (draft)"), "Report", "a closing note is removed");
assert.equal(stripNote("Report (draft) final"), "Report (draft) final", "a note that does not close at the end stays");
assert.equal(stripNote("Plain title"), "Plain title", "a title with no bracket");
assert.equal(stripNote("Notes (a) (b)"), "Notes (a)", "only the closing note goes");
assert.equal(stripNote("Song (live)"), "Song", "spaces left trailing are removed");
assert.equal(stripNote(""), "", "a title holding nothing");
console.log("ok");
