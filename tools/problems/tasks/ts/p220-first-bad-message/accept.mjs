import assert from "node:assert/strict";
import { firstBadMessage } from "./solution.ts";

const said = (from, kind) => ({ from, kind });
const opening = [
  said("client", "HELLO"),
  said("server", "OFFER"),
  said("client", "CHOOSE"),
  said("server", "ACCEPT"),
];
const closing = [said("client", "BYE"), said("server", "BYE")];

assert.equal(
  firstBadMessage([...opening, ...closing]),
  -1,
  "an exchange with no data at all is whole"
);
assert.equal(
  firstBadMessage([
    ...opening,
    said("client", "DATA"),
    said("server", "DATA"),
    ...closing,
  ]),
  -1,
  "one round of data is whole"
);
assert.equal(
  firstBadMessage([
    ...opening,
    said("client", "DATA"),
    said("server", "DATA"),
    said("client", "DATA"),
    said("server", "DATA"),
    ...closing,
  ]),
  -1,
  "two rounds of data are whole"
);
assert.equal(
  firstBadMessage([said("client", "HELLO")]),
  1,
  "an exchange that has only begun reports its length"
);
assert.equal(firstBadMessage(opening), 4, "an exchange that never says goodbye");
assert.equal(
  firstBadMessage([...opening, said("client", "BYE")]),
  5,
  "the server's closing BYE is still owed"
);
assert.equal(
  firstBadMessage([said("server", "HELLO"), said("server", "OFFER")]),
  0,
  "the wrong side opens"
);
assert.equal(
  firstBadMessage([said("client", "HELLO"), said("client", "OFFER")]),
  1,
  "the right kind from the wrong side"
);
assert.equal(
  firstBadMessage([...opening, said("server", "DATA")]),
  4,
  "the server cannot speak data first"
);
assert.equal(
  firstBadMessage([...opening, said("client", "DATA"), said("client", "BYE")]),
  5,
  "the server owes an answer before goodbye"
);
assert.equal(
  firstBadMessage([...opening, said("client", "BYE"), said("client", "BYE")]),
  5,
  "the client cannot answer its own goodbye"
);
assert.equal(
  firstBadMessage([...opening, ...closing, said("client", "DATA")]),
  6,
  "nothing may follow the closing BYE"
);

assert.throws(
  () => firstBadMessage("HELLO"),
  Error,
  "an exchange that is not a list is rejected"
);
assert.throws(() => firstBadMessage([]), Error, "an empty exchange is rejected");
assert.throws(
  () => firstBadMessage([["client", "HELLO"]]),
  Error,
  "a message that is not a mapping is rejected"
);
assert.throws(
  () => firstBadMessage([said("proxy", "HELLO")]),
  Error,
  "an unknown side is rejected"
);
assert.throws(
  () => firstBadMessage([said("client", "hello")]),
  Error,
  "a kind in the wrong case is rejected"
);
assert.throws(
  () => firstBadMessage([said("client", "PING")]),
  Error,
  "a kind outside the six names is rejected"
);

console.log("ok");
