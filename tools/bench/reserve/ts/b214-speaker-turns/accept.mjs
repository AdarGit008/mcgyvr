import assert from "node:assert/strict";
import { foldTranscript } from "./solution.ts";

assert.deepEqual(foldTranscript([]), [], "an empty transcript gathers nothing");
assert.deepEqual(foldTranscript(["  ada :   the pump is dry  "]), [{ speaker: "ada", text: "the pump is dry" }], "one line is trimmed on both sides of the colon");
assert.deepEqual(foldTranscript(["ada: the pump is dry", "ada: I shut the valve"]), [{ speaker: "ada", text: "the pump is dry I shut the valve" }], "neighbouring lines from one speaker join");
assert.deepEqual(foldTranscript(["ada: dry", "bo: noted", "ada: refilled"]), [{ speaker: "ada", text: "dry" }, { speaker: "bo", text: "noted" }, { speaker: "ada", text: "refilled" }], "a speaker coming back opens a fresh block");
assert.deepEqual(foldTranscript(["ada: dry", "ada:    ", "ada: refilled"]), [{ speaker: "ada", text: "dry refilled" }], "an empty line interrupts nothing");
assert.deepEqual(foldTranscript(["bo: warning: seal at 4:15"]), [{ speaker: "bo", text: "warning: seal at 4:15" }], "only the first colon parts the line");
assert.throws(() => foldTranscript(["no colon anywhere"]), Error, "a line carrying no colon is rejected");
console.log("ok");
