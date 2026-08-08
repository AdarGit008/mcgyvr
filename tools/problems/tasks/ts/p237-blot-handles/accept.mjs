import assert from "node:assert/strict";
import { blotHandles } from "./solution.ts";

assert.equal(blotHandles(""), "", "an empty message stays empty");
assert.equal(
  blotHandles("hi @alice_1 there"),
  "hi @a...... there",
  "the at sign and the first character survive the blot",
);
assert.equal(
  blotHandles("ping @zed!"),
  "ping @z..!",
  "three characters is the shortest handle there is",
);
assert.equal(
  blotHandles("@ab and @abcdefghijklm"),
  "@ab and @abcdefghijklm",
  "two characters and thirteen are both no handle",
);
assert.equal(
  blotHandles("mail me@home now"),
  "mail me@home now",
  "an at sign glued to a word is an address, not a handle",
);
assert.equal(
  blotHandles("@abc@def"),
  "@a..@def",
  "the second at sign follows a handle character, so it opens nothing",
);
assert.equal(
  blotHandles("@aaa @bbb"),
  "@a.. @b..",
  "each handle in a plain part is blotted",
);
assert.equal(
  blotHandles("run `@bob` but @carol here"),
  "run `@bob` but @c.... here",
  "a fenced handle is copied through with its backticks",
);
assert.equal(
  blotHandles("@dave ` @erin"),
  "@d... ` @erin",
  "a backtick with no partner fences the rest of the message",
);
assert.equal(
  blotHandles("`@one` `@two` @three"),
  "`@one` `@two` @t....",
  "fences alternate, so the text between two of them is plain",
);
assert.equal(
  blotHandles("@a_9 done"),
  "@a.. done",
  "digits and underscores count toward the length",
);
assert.throws(() => blotHandles(7), Error, "a number is not a message");
console.log("ok");
