// node tests/test_lyricpage.js
const assert = require("assert");
const { pickPage } = require("../web/lyricpage.js");
const L = (s, e) => [[s, e, "x"]];

// fixture timing: line 0 sung 0-2 s, line 1 from 2 s
let lines = [L(0, 2), L(2, 4)];
assert.deepStrictEqual(pickPage(lines, 1.0), { now: 0, page: 0 });      // still on line 0, no early dimming
assert.deepStrictEqual(pickPage(lines, 3.0), { now: 1, page: 0 });

// three tight lines: the page must not flip before the bottom line (1) has finished
lines = [L(0, 2), L(2, 4), L(4, 6)];
assert.deepStrictEqual(pickPage(lines, 3.9), { now: 1, page: 0 });      // line 2 is <1.5 s away but line 1 is still being sung
assert.deepStrictEqual(pickPage(lines, 4.0), { now: 2, page: 2 });

// a gap lets it flip early (1.5 s before the next line)
lines = [L(0, 2), L(2, 4), L(10, 12)];
assert.deepStrictEqual(pickPage(lines, 8.4), { now: 1, page: 0 });
assert.deepStrictEqual(pickPage(lines, 8.5), { now: 1, page: 2 });
assert.deepStrictEqual(pickPage(lines, -1), { now: 0, page: 0 });       // before the song: first page
assert.deepStrictEqual(pickPage([L(0, 1)], 5), { now: 0, page: 0 });   // single line
console.log("lyricpage ok");
