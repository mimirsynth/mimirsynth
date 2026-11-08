// The guided tour's decisions (src/ui/tourLogic.ts, issue 364): when it shows on its own, skipping it, finishing it, replaying it from
// the help menu, and where its card goes on a wide screen and on a phone.
//   node --experimental-strip-types --test scripts/
import assert from "node:assert/strict";
import test from "node:test";
import { move, onScreen, placeCard, shouldAutoStart } from "../src/ui/tourLogic.ts";

test("it shows on its own on the first visit, once there is a brain, and not again", () => {
  assert.equal(shouldAutoStart({ tourSeen: false, hasBrain: true, startedHere: false }), true);
  assert.equal(shouldAutoStart({ tourSeen: true, hasBrain: true, startedHere: false }), false);        // finished or skipped, on any device
  assert.equal(shouldAutoStart({ tourSeen: false, hasBrain: false, startedHere: false }), false);      // a new instance: first a brain
  assert.equal(shouldAutoStart({ tourSeen: false, hasBrain: true, startedHere: true }), false);       // closed while the answer is on its way
  assert.equal(shouldAutoStart({ tourSeen: undefined, hasBrain: true, startedHere: false }), false);  // an older server that does not say
});

test("skipping ends it at any step and marks it seen", () => {
  for (const i of [0, 3, 7]) assert.deepEqual(move(i, 8, "skip"), { index: null, persist: true });
});

test("next and back walk the steps, and next on the last one finishes it", () => {
  assert.deepEqual(move(0, 8, "next"), { index: 1, persist: false });
  assert.deepEqual(move(4, 8, "back"), { index: 3, persist: false });
  assert.deepEqual(move(0, 8, "back"), { index: 0, persist: false });      // nothing before the first step
  assert.deepEqual(move(7, 8, "next"), { index: null, persist: true });
});

test("a replay from the help menu walks the same steps and ends the same way", () => {
  let i = 0, end = null;
  while (end === null) { const r = move(i, 8, "next"); if (r.index === null) end = r; else i = r.index; }
  assert.equal(i, 7);
  assert.deepEqual(end, { index: null, persist: true });
});

const view = { width: 1280, height: 800 };
const card = { width: 360, height: 220 };

test("a target off screen is no target: the card goes to the middle", () => {
  assert.equal(onScreen(null, view), null);
  assert.equal(onScreen({ top: 100, left: -240, width: 220, height: 36 }, view), null);   // a phone's navigation, still closed
  assert.equal(onScreen({ top: 0, left: 0, width: 0, height: 0 }, view), null);           // not laid out
  assert.deepEqual(placeCard(null, card, view, false), { mode: "center" });
});

test("on a wide screen the card floats beside the target, inside the window", () => {
  const nav = { top: 300, left: 8, width: 220, height: 36 };
  assert.deepEqual(placeCard(nav, card, view, false), { mode: "float", left: 240, top: 208 });
  const low = { top: 760, left: 8, width: 220, height: 36 };                              // the help button, at the bottom
  assert.deepEqual(placeCard(low, card, view, false), { mode: "float", left: 240, top: 800 - 220 - 16 });
  const wide = { top: 100, left: 1000, width: 270, height: 40 };                          // no room on the right: below
  assert.deepEqual(placeCard(wide, card, view, false), { mode: "float", left: 1280 - 360 - 16, top: 152 });
});

test("on a phone the card is docked at the edge away from the target", () => {
  const phone = { width: 375, height: 812 };
  assert.deepEqual(placeCard({ top: 120, left: 8, width: 300, height: 40 }, card, phone, true), { mode: "dock", edge: "bottom" });
  assert.deepEqual(placeCard({ top: 700, left: 8, width: 300, height: 40 }, card, phone, true), { mode: "dock", edge: "top" });
  assert.deepEqual(placeCard(null, card, phone, true), { mode: "center" });
});
