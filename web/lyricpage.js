// Which two lyric lines are on screen, and which one is being sung. Pure, so tests/test_lyricpage.js can check it.
// lines: [[ [start, end, text], ... ], ...]  ->  { now, page }  (page = index of the top line of the pair)
function pickPage(lines, t) {
  let now = 0;
  for (let i = 0; i < lines.length && lines[i][0][0] <= t; i++) now = i;   // the line really being sung: no lead time
  let page = Math.floor(now / 2) * 2;
  const next = page + 2;
  if (next < lines.length) {
    const last = lines[Math.min(page + 1, lines.length - 1)];
    const bottomDone = last[last.length - 1][1];
    // flip early (1.5 s) so the singer can read ahead, but never wipe a line that is still being sung
    if (t >= Math.max(lines[next][0][0] - 1.5, bottomDone)) page = next;
  }
  return { now, page };
}
if (typeof module !== "undefined") module.exports = { pickPage };
