import assert from "node:assert/strict";
import { newLink, linkSend, linkAck } from "./solution.ts";

assert.deepEqual(
  newLink(3),
  { size: 3, next: 0, pending: [], delivered: 0 },
  "a fresh link is empty",
);
const link = newLink(3);
linkSend(link, "syn");
assert.equal(linkSend(link, "hello"), 1, "sends take sequence numbers in order");
linkSend(link, "world");
assert.throws(() => linkSend(link, "late"), Error, "a full window refuses to send");
assert.deepEqual(linkAck(link, 0), ["syn"], "acking the oldest frame frees it");
assert.deepEqual(
  link,
  { size: 3, next: 3, pending: [[1, "hello"], [2, "world"]], delivered: 1 },
  "the freed frame leaves pending and delivered grows",
);
assert.deepEqual(linkAck(link, -1), [], "an ack of -1 frees nothing");
assert.deepEqual(
  linkAck(link, 2),
  ["hello", "world"],
  "a cumulative ack frees every covered frame oldest first",
);
assert.equal(link.delivered, 3, "delivered counts every freed frame");
assert.equal(linkSend(link, "again"), 3, "sequence numbers are never reused");
assert.throws(() => linkAck(link, 4), Error, "acking an unsent frame is rejected");
assert.throws(() => linkAck(link, 1.5), Error, "a fractional ack is rejected");
assert.throws(() => linkAck(link, -2), Error, "an ack below -1 is rejected");
assert.throws(() => newLink(0), Error, "a zero window size is rejected");
assert.throws(() => linkSend(newLink(1), ""), Error, "an empty payload is rejected");
console.log("ok");
