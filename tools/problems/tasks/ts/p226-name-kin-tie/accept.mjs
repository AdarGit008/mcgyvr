import assert from "node:assert/strict";
import { nameKinTie } from "./solution.ts";

const LINKS = [
  { child: "bo", parent: "ada" },
  { child: "cy", parent: "ada" },
  { child: "di", parent: "bo" },
  { child: "ed", parent: "bo" },
  { child: "fi", parent: "cy" },
  { child: "gus", parent: "di" },
  { child: "hal", parent: "fi" },
  { child: "ivy", parent: "gus" },
  { child: "jo", parent: "hal" },
  { child: "kim", parent: "ivy" },
  { child: "max", parent: "di" },
  { child: "max", parent: "fi" },
  { child: "quin", parent: "gus" },
  { child: "quin", parent: "cy" },
  { child: "kit", parent: "lu" },
];

function ladder(depth) {
  const links = [];
  for (const line of ["a", "b"]) {
    links.push({ child: line + "1", parent: "root" });
    for (let at = 2; at <= depth; at++) {
      links.push({ child: line + at, parent: line + (at - 1) });
    }
  }
  return links;
}

assert.equal(nameKinTie(LINKS, "bo", "bo"), "self", "a person set against themselves");
assert.equal(nameKinTie(LINKS, "bo", "ada"), "parent", "one link straight up");
assert.equal(nameKinTie(LINKS, "ada", "bo"), "child", "one link straight down");
assert.equal(nameKinTie(LINKS, "gus", "ada"), "great-grandparent", "three links up");
assert.equal(nameKinTie(LINKS, "ivy", "ada"), "great-great-grandparent", "four links up");
assert.equal(nameKinTie(LINKS, "ada", "ivy"), "great-great-grandchild", "four links down");
assert.equal(nameKinTie(LINKS, "di", "ed"), "sibling", "a shared parent");
assert.equal(nameKinTie(LINKS, "di", "cy"), "aunt-or-uncle", "a parent's sibling");
assert.equal(nameKinTie(LINKS, "cy", "di"), "niece-or-nephew", "the same tie read the other way");
assert.equal(nameKinTie(LINKS, "gus", "cy"), "great-aunt-or-uncle", "a grandparent's sibling");
assert.equal(nameKinTie(LINKS, "cy", "gus"), "great-niece-or-nephew", "and its mirror");
assert.equal(nameKinTie(LINKS, "ivy", "cy"), "great-great-aunt-or-uncle", "two greats deep on the collateral line");
assert.equal(nameKinTie(LINKS, "di", "fi"), "first cousin", "two counts of two");
assert.equal(nameKinTie(LINKS, "gus", "fi"), "first cousin once removed", "a generation apart");
assert.equal(nameKinTie(LINKS, "fi", "gus"), "first cousin once removed", "removal does not take sides");
assert.equal(nameKinTie(LINKS, "gus", "hal"), "second cousin", "two counts of three");
assert.equal(nameKinTie(LINKS, "ivy", "jo"), "third cousin", "two counts of four");
assert.equal(nameKinTie(LINKS, "ivy", "hal"), "second cousin once removed", "degree from the smaller count");
assert.equal(nameKinTie(LINKS, "ivy", "fi"), "first cousin twice removed", "two generations apart");
assert.equal(nameKinTie(LINKS, "kim", "fi"), "first cousin three times removed", "three generations apart");
assert.equal(nameKinTie(LINKS, "bo", "kit"), "unrelated", "two people with no forebear in common");
assert.equal(nameKinTie(LINKS, "max", "ed"), "aunt-or-uncle", "the nearer of two lines decides");
assert.equal(nameKinTie(LINKS, "max", "hal"), "sibling", "one shared parent out of two is a sibling");
assert.equal(nameKinTie(LINKS, "quin", "bo"), "aunt-or-uncle", "the smallest greater count wins over the longer line");
assert.equal(nameKinTie(LINKS, "quin", "di"), "grandparent", "and the same tie can read straight up");
assert.equal(nameKinTie(ladder(11), "a11", "b11"), "tenth cousin", "the furthest degree there is");
assert.equal(
  nameKinTie(ladder(12), "a12", "b2"),
  "first cousin ten times removed",
  "the furthest removal there is",
);

assert.throws(() => nameKinTie("links", "a", "b"), Error, "links that are not a list are rejected");
assert.throws(() => nameKinTie([["a", "b"]], "a", "b"), Error, "a link that is not a mapping is rejected");
assert.throws(() => nameKinTie([{ child: "", parent: "a" }], "a", "a"), Error, "an empty name is rejected");
assert.throws(() => nameKinTie([{ child: "a", parent: "a" }], "a", "a"), Error, "someone made their own parent is rejected");
assert.throws(
  () => nameKinTie([{ child: "a", parent: "b" }, { child: "a", parent: "b" }], "a", "b"),
  Error,
  "a link listed twice is rejected",
);
assert.throws(
  () =>
    nameKinTie(
      [{ child: "a", parent: "b" }, { child: "a", parent: "c" }, { child: "a", parent: "d" }],
      "a",
      "b",
    ),
  Error,
  "a third parent is rejected",
);
assert.throws(
  () => nameKinTie([{ child: "a", parent: "b" }, { child: "b", parent: "a" }], "a", "b"),
  Error,
  "links closing a loop are rejected",
);
assert.throws(() => nameKinTie(LINKS, "zed", "bo"), Error, "a second person nobody names is rejected");
assert.throws(() => nameKinTie(LINKS, "bo", "zed"), Error, "a third person nobody names is rejected");
assert.throws(() => nameKinTie(LINKS, 5, "bo"), Error, "a person who is not a string is rejected");
assert.throws(() => nameKinTie(ladder(12), "a12", "b12"), Error, "a degree past ten is rejected");
assert.throws(() => nameKinTie(ladder(13), "a13", "b2"), Error, "a removal past ten is rejected");
console.log("ok");
