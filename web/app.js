"use strict";
// Kuraoke Kami — the TV window. Everything here runs on the one surface guests can see.
const KK = window.KK || {};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const DISPLAY = true;   // one surface: every page load is the display (?display=1 still works)

// ------------------------------------------------------------------ state
let S = null;                  // last /api/state snapshot
let lang = "en", rev = -1, loadedRev = -1, tAt = 0;
let lines = [], cdg = null, page = -1, spans = [];
let entry = "", facets = null, facetTick = 0, scanRev = -1;
let previewTimer = 0, previewSeq = 0;
let songs = [], songOffset = 0, songSel = -1, songsSeq = 0, missingOnly = false;
let syncOn = false, syncIdx = 0;
let cands = [], candFor = null, inbox = null;
let undoFn = null, toastTimer = 0, hudTimer = 0, hudBase = null, errorAt = 0;
let confirmFn = null, qTimer = 0;

// ------------------------------------------------------------------ i18n
const t = (k) => (I18N[lang] && I18N[lang][k]) ?? I18N.en[k] ?? k;
const fmt = (k, vars) => String(t(k)).replace(/\{(\w+)\}/g, (m, n) => (vars && n in vars ? String(vars[n]) : m));

function applyI18n() {
  document.documentElement.lang = lang;
  $$("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  $$("[data-i18n-aria]").forEach((e) => e.setAttribute("aria-label", t(e.dataset.i18nAria)));
  $$("[data-i18n-title]").forEach((e) => { e.title = t(e.dataset.i18nTitle); });
  renderKeyTables();
  if (S) {
    renderQueue.sig = "";
    renderQueue();
    if (!$("#drawer").hidden) renderSongs();
    renderDrawerFilters(true);
    if (inbox) renderInbox();
    setTransport(S.phase);
  }
}

function keyRows() { return (I18N[lang] && I18N[lang].keys) || I18N.en.keys; }

function renderKeyTables() {
  for (const sel of ["#keys-table", "#help-table"]) {
    const body = $(sel);
    if (!body) continue;
    body.innerHTML = "";
    for (const [k, what] of keyRows()) {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.scope = "row"; th.textContent = k;
      const td = document.createElement("td");
      td.textContent = what;
      tr.append(th, td);
      body.append(tr);
    }
  }
}

// ------------------------------------------------------------------ tiny DOM helpers
const icon = (name) => `<svg class="ic" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const songLine = (s) => (s ? `${s.title || ""}${s.artist ? " — " + s.artist : ""}` : "");
const rowLabel = (s) => `${t("song_no")} ${s.number} · ${songLine(s)}`;
const clock = (sec) => { const v = Math.max(0, Number(sec) || 0); return `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, "0")}`; };
const signed = (v) => `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(2)} s`;
const signedInt = (v) => (v > 0 ? "+" + v : String(v));

function iconBtn(name, label, fn, cls = "ghost icon") {
  const b = document.createElement("button");
  b.type = "button"; b.className = cls; b.innerHTML = icon(name);
  b.setAttribute("aria-label", label); b.title = label;
  b.onclick = fn;
  return b;
}

function actBtn(name, label, fn, cls = "secondary sm") {
  const b = document.createElement("button");
  b.type = "button"; b.className = cls;
  b.innerHTML = icon(name) + "<span></span>";
  b.querySelector("span").textContent = label;
  b.setAttribute("aria-label", label);
  b.onclick = fn;
  return b;
}

function badge(status) {
  const d = el("span", "badge");
  const kind = status || "none";
  if (kind === "word" || kind === "line") {
    const label = t(kind === "word" ? "lyr_word" : "lyr_line");
    d.classList.add("ok"); d.innerHTML = icon("check");
    d.setAttribute("role", "img"); d.setAttribute("aria-label", label); d.title = label;
  } else if (kind === "suspect") {
    d.classList.add("warn"); d.innerHTML = icon("alert");
    d.setAttribute("role", "img"); d.setAttribute("aria-label", t("lyr_suspect")); d.title = t("lyr_suspect");
  } else if (kind === "none") {
    d.classList.add("none"); d.textContent = t("lyr_none");
  } else {
    d.hidden = true;   // embedded / cdg: the file carries its own lyrics, no badge
  }
  return d;
}

function displayNames() {
  try { return new Intl.DisplayNames([lang === "tl" ? "tl" : "en"], { type: "language" }); }
  catch (e) { return null; }
}
function langName(code, dn) {
  if (!code) return "";
  try {
    const n = dn && dn.of(code);
    if (n) return n.charAt(0).toUpperCase() + n.slice(1);
  } catch (e) { /* unknown code: show it raw */ }
  return code;
}

// ------------------------------------------------------------------ api
const H = { "X-Token": KK.token || "" };
const mediaUrl = (p) => `${p}?t=${encodeURIComponent(KK.token || "")}`;

async function get(path) {
  const r = await fetch(path, { headers: H });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

async function api(name, body = {}) {
  try {
    const r = await fetch("/api/" + name, {
      method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    return await r.json();
  } catch (e) {
    report(`api ${name}: ${e && e.message}`);
    return { ok: false, error: "network" };
  }
}

// ------------------------------------------------------------------ toast
function flash(msg, undo) {
  $("#toast-msg").textContent = msg;
  const btn = $("#toast-undo");
  btn.hidden = !undo;
  undoFn = undo || null;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").classList.remove("show"); undoFn = null; }, undo ? 7000 : 2600);
}

function doUndo() {
  const fn = undoFn;
  if (!fn) return;
  undoFn = null;
  clearTimeout(toastTimer);
  $("#toast").classList.remove("show");
  fn();
}

async function reserve(body) {
  const r = await api("reserve", body);
  flash(r.ok ? `${t("added")}: ${songLine(r.song)}` : t("notfound"));
  return r;
}

// ------------------------------------------------------------------ overlays (sheets + dialogs)
const stack = [];
const overlayKeys = new Map();
const overlayEscapes = new Map();

function restoreFocus(opener) {
  if (opener && opener.isConnected && opener.offsetParent !== null) { opener.focus(); return; }
  if (!$("#drawer").hidden) { $("#q").focus(); return; }
  if (S && S.phase === "idle") $("#numin").focus();
}

function openOverlay(sel, focusSel) {
  const node = typeof sel === "string" ? $(sel) : sel;
  if (!node || stack.some((o) => o.el === node)) return;
  stack.push({ el: node, opener: document.activeElement });
  node.hidden = false;
  const first = focusSel ? node.querySelector(focusSel) : null;
  (first || node).focus();
}

function closeOverlay(sel) {
  const node = sel ? (typeof sel === "string" ? $(sel) : sel) : (stack[stack.length - 1] || {}).el;
  const i = stack.findIndex((o) => o.el === node);
  if (i < 0) return;
  const [o] = stack.splice(i, 1);
  node.hidden = true;
  if (node.id === "drawer") {
    $$("#songs .rowactions").forEach((a) => { a.hidden = true; });
    $("#song-status").textContent = "";
  }
  restoreFocus(o.opener);
}

function trapTab(e, node) {
  const items = $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', node)
    .filter((n) => n.offsetParent !== null);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
}

// ------------------------------------------------------------------ polling
async function poll() {
  const q = ["d=1", facetTick++ % 12 === 0 ? "facets=1" : ""].filter(Boolean).join("&");
  let s = null;
  try {
    s = await get("/api/state?" + q);
  } catch (e) {
    $("#offline").hidden = false;   // only the state poll decides "offline": a bad lyrics fetch does not
  }
  if (s) {
    $("#offline").hidden = true;
    try { onState(s); } catch (e) { report("state: " + (e && e.message)); }
  }
  setTimeout(poll, 400);
}

function onState(s) {
  const first = !S, prev = S;
  if (s.facets) facets = s.facets;
  s.facets_ = facets;
  S = s; tAt = performance.now();
  if (first) hudBase = { melody: s.cfg.melody, chorus: s.cfg.chorus };
  if (s.cfg.lang !== lang) { lang = s.cfg.lang; applyI18n(); }

  if (s.rev !== rev) {
    rev = s.rev; loadedRev = -1; page = -1; lines = []; spans = []; cdg = null;
    const vid = $("#vid");
    vid.pause(); vid.removeAttribute("src"); vid.hidden = true;
    $("#cdg").hidden = true;
    if (syncOn) closeSync();
  }
  if (s.phase === "error" && (!prev || prev.phase !== "error")) errorAt = performance.now();
  if (s.song && s.phase !== "prep" && s.phase !== "error" && loadedRev !== rev) {
    loadedRev = rev;
    loadSong(s);
  }
  if (prev && prev.phase !== s.phase) onPhaseChange(prev.phase, s.phase);
  else if (!prev) setTransport(s.phase);
  if (s.scan.rev !== scanRev) {
    scanRev = s.scan.rev;
    facetTick = 0;
    if (!$("#drawer").hidden) loadSongs(true);
  }
  hudToast(s, prev);
  onTiming(prev && prev.timing, s.timing);
  if (!$("#lyrics-dialog").hidden) renderSpeech();
  render();
  if (first && s.phase === "idle") focusNum();
}

async function loadSong(s) {
  const myRev = rev, id = s.song.id;
  try {
    const r = await get("/api/lyrics");
    if (rev !== myRev) return;
    lines = r.lines || [];
  } catch (e) {
    lines = [];
    report("lyrics fetch: " + (e && e.message));   // never mark the app offline for this
  }
  if (s.has_video) {
    const vid = $("#vid");
    vid.hidden = false;
    vid.src = mediaUrl(`/media/${id}/video`);
  }
  if (s.has_cdg) {
    try {
      const buf = await (await fetch(mediaUrl(`/media/${id}/cdg`))).arrayBuffer();
      if (rev === myRev) cdg = new CDG(buf);
    } catch (e) {
      cdg = null;
      report("cdg fetch: " + (e && e.message));
    }
  }
}

function onPhaseChange(from, to) {
  setTransport(to);
  if (to === "idle") {
    $("#preview").textContent = "";
    focusNum();
  } else {
    const n = $("#numin");
    if (document.activeElement === n) n.blur();
  }
}

function focusNum() {
  if (!S || S.phase !== "idle" || stack.length) return;
  const n = $("#numin");
  if (document.activeElement !== n) n.focus();
}

// ------------------------------------------------------------------ render
function render() {
  if (!S) return;
  const ph = S.phase, song = S.song;
  const stage = $("#stage");
  stage.dataset.phase = ph;
  stage.dataset.kind = S.kind || "";
  $("#idle").hidden = ph !== "idle";
  $("#intro").hidden = !(ph === "prep" || ph === "intro");
  $("#error").hidden = ph !== "error";
  $("#stagebar").hidden = !(ph === "playing" || ph === "paused");

  const numin = $("#numin");
  if (ph !== "idle" && document.activeElement === numin) numin.blur();
  if (numin.value !== entry && document.activeElement !== numin) numin.value = entry;
  $("#pill-digits").textContent = entry;
  $("#entry-pill").hidden = !(entry && ph !== "idle");

  if (ph === "idle") renderIdle();
  if (song) {
    $("#i-num").textContent = String(song.number);
    $("#i-title").textContent = song.title || "";
    $("#i-artist").textContent = song.artist || "";
    const note = song.lyrics === "none" ? t("no_lyrics_notice") : song.lyrics === "suspect" ? t("suspect_notice") : "";
    const noteEl = $("#i-note");
    noteEl.textContent = note;
    noteEl.hidden = !note;
  }
  const next = (S.queue || [])[0];
  $("#i-next").textContent = next ? `${t("up_next")}: ${songLine(next.song)}` : (ph === "prep" ? t("preparing") : "");
  $("#bar-next").textContent = next ? `${t("up_next")}: ${songLine(next.song)}` : "";
  if (ph === "error") $("#error-msg").textContent = S.error || "";

  renderQueue();
  renderDrawerFilters();
  renderSettings();
}

function renderIdle() {
  const q = (S.queue || []).slice(0, 3);
  const sig = JSON.stringify(q.map((i) => [i.qid, i.song.number]));
  if (sig !== renderIdle.sig) {
    renderIdle.sig = sig;
    const ol = $("#idle-queue");
    ol.innerHTML = "";
    q.forEach((it, i) => {
      const li = document.createElement("li");
      li.append(el("span", "n", String(i + 1)), el("span", "ttl", songLine(it.song)));
      ol.append(li);
    });
    ol.hidden = !q.length;
    $("#idle-side-title").hidden = !q.length;
  }
  const count = $("#idle-count");
  count.textContent = facets ? fmt("song_count", { n: facets.total }) : "";
  count.hidden = !!q.length || !count.textContent;
  $("#idle-browse").hidden = !!q.length;
}

function setTransport(ph) {
  const b = $("#t-pause");
  if (!b) return;
  const playing = ph === "playing";
  b.innerHTML = icon(playing ? "pause" : "play");
  const label = playing ? t("pause") : t("play");
  b.setAttribute("aria-label", label);
  b.title = label;
}

function hudToast(s, prev) {
  if (!prev || !s.song || s.rev !== prev.rev) return;
  const msg = [];
  if (s.key !== prev.key && s.key !== 0) msg.push(`${t("key")}: ${signedInt(s.key)}`);
  if (s.tempo !== prev.tempo && s.tempo !== 1) msg.push(`${t("tempo")}: ${Math.round(s.tempo * 100)}%`);
  if (hudBase && s.melody !== prev.melody && s.melody !== hudBase.melody) msg.push(`${t("melody")}: ${s.melody ? t("on") : t("off")}`);
  if (hudBase && s.chorus !== prev.chorus && s.chorus !== hudBase.chorus) msg.push(`${t("chorus")}: ${s.chorus ? t("on") : t("off")}`);
  if (!msg.length) return;
  const box = $("#hud-toast");
  box.textContent = msg.join(" · ");
  box.classList.add("show");
  clearTimeout(hudTimer);
  hudTimer = setTimeout(() => box.classList.remove("show"), 2000);
}

// ------------------------------------------------------------------ number entry
function setEntry(value) {
  entry = String(value).replace(/\D/g, "").slice(0, 8);
  const numin = $("#numin");
  if (document.activeElement !== numin && numin.value !== entry) numin.value = entry;
  $("#pill-digits").textContent = entry;
  $("#entry-pill").hidden = !(entry && S && S.phase !== "idle");
  updatePreview();
}

function onNumInput() {
  const numin = $("#numin");
  const clean = numin.value.replace(/\D/g, "").slice(0, 8);
  if (numin.value !== clean) numin.value = clean;
  entry = clean;
  $("#pill-digits").textContent = entry;
  updatePreview();
}

function updatePreview() {
  const box = $("#preview");
  box.className = "preview";
  box.textContent = "";
  clearTimeout(previewTimer);
  if (!entry) return;
  previewTimer = setTimeout(async () => {
    const seq = ++previewSeq;
    let r;
    try { r = await get(`/api/songs?q=${encodeURIComponent(entry)}&offset=0`); }
    catch (e) { if (seq === previewSeq) { box.textContent = t("load_failed"); box.classList.add("none"); } return; }
    if (seq !== previewSeq || !entry) return;
    const want = String(Number(entry));
    const hit = (r.songs || []).find((x) => String(x.number) === want);
    box.textContent = "";
    if (!hit) { box.textContent = t("no_song_number"); box.classList.add("none"); return; }
    box.append(el("span", "pv-num", `${t("song_no")} ${hit.number}`), el("span", "pv-title", hit.title || ""));
    if (hit.artist) box.append(el("span", "pv-artist", `— ${hit.artist}`));
    box.append(badge(hit.lyrics));
  }, 130);
}

async function reserveEntry() {
  if (!entry) return;
  const number = Number(entry);
  setEntry("");
  await reserve({ number });
}

// ------------------------------------------------------------------ queue
function renderQueue() {
  if (!S) return;
  const queue = S.queue || [];
  $("#queue-empty").hidden = !!queue.length;
  $("#queue-clear").disabled = !queue.length;
  const sig = JSON.stringify(queue.map((q) => q.qid));
  if (sig === renderQueue.sig) return;
  renderQueue.sig = sig;
  const ol = $("#queue");
  ol.innerHTML = "";
  queue.forEach((q, i) => {
    const li = document.createElement("li");
    li.className = "qrow";
    const txt = el("span", "txt");
    txt.append(el("b", "", q.song.title || ""),
      el("i", "", [q.song.artist, `${t("song_no")} ${q.song.number}`].filter(Boolean).join(" · ")));
    li.append(el("span", "n", String(i + 1)), txt);
    if (i > 0) li.append(iconBtn("top", fmt("move_top_song", { s: q.song.title }), () => api("top", { qid: q.qid })));
    li.append(iconBtn("x", fmt("remove_queue_song", { s: q.song.title }), () => removeQueueItem(q)));
    ol.append(li);
  });
}

async function removeQueueItem(q) {
  await api("unqueue", { qid: q.qid });
  flash(fmt("removed", { s: q.song.title }), async () => {
    await api("reserve", { id: q.song.id });
    flash(t("queue_restored"));
  });
}

async function clearQueue() {
  if (!S || !(S.queue || []).length) return;
  const gone = S.queue.map((q) => q.song);
  await api("clear");
  flash(fmt("queue_cleared", { n: gone.length }), async () => {
    for (const s of gone) await api("reserve", { id: s.id });
    flash(t("queue_restored"));
  });
}

function openQueue() {
  if (!$("#queue-panel").hidden) return;
  openOverlay("#queue-panel");
  renderQueue();
}

// ------------------------------------------------------------------ song book
function openDrawer() {
  if (!$("#drawer").hidden) { $("#q").focus(); return; }
  openOverlay("#drawer", "#q");
  renderDrawerFilters(true);
  loadSongs(true);
}

async function loadSongs(reset) {
  const seq = ++songsSeq;
  if (reset) { songOffset = 0; songs = []; songSel = -1; }
  const params = new URLSearchParams();
  const q = $("#q").value.trim();
  if (q) params.set("q", q);
  params.set("offset", String(songOffset));
  if (missingOnly) params.set("missing", "1");
  let r;
  try { r = await get("/api/songs?" + params.toString()); }
  catch (e) { songs = []; renderSongs(); flash(t("load_failed")); return; }
  if (seq !== songsSeq) return;
  songs = reset ? (r.songs || []) : songs.concat(r.songs || []);
  songOffset += (r.songs || []).length;
  $("#more").hidden = !r.more;
  renderSongs();
}

function renderSongs() {
  const ul = $("#songs");
  if (!ul) return;
  ul.innerHTML = "";
  if (!songs.length) {
    const li = el("li", "songrow empty", t("no_songs"));
    ul.append(li);
    $("#song-status").textContent = "";
    return;
  }
  const dn = displayNames();
  songs.forEach((s, i) => {
    const li = document.createElement("li");
    li.id = "song-" + i;
    li.className = "songrow";
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", "false");

    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "pick";
    pick.tabIndex = -1;
    pick.setAttribute("aria-label", rowLabel(s));
    const txt = el("span", "txt");
    txt.append(el("b", "", s.title || ""),
      el("i", "", [s.artist, langName(s.lang, dn)].filter(Boolean).join(" · ")));
    pick.append(el("span", "num", String(s.number)), txt, badge(s.lyrics));
    pick.addEventListener("click", () => { songSel = i; markSelected(false); toggleActions(i, true); });

    const acts = el("div", "rowactions");
    acts.hidden = true;
    acts.append(
      actBtn("plus", `${t("add_queue")}: ${rowLabel(s)}`, () => reserve({ id: s.id })),
      actBtn("top", `${t("sing_next")}: ${rowLabel(s)}`, () => reserve({ id: s.id, top: true })),
      actBtn("music", `${t("find_lyrics")}: ${rowLabel(s)}`, () => openLyricsFor(s)),
    );
    li.append(pick, acts);
    ul.append(li);
  });
  if (songSel >= songs.length) songSel = -1;
  markSelected(false);
}

function markSelected(scroll, focus) {
  $$("#songs .songrow").forEach((li, i) => {
    const on = i === songSel;
    li.classList.toggle("sel", on);
    li.setAttribute("aria-selected", on ? "true" : "false");
  });
  $("#q").removeAttribute("aria-activedescendant");
  $("#song-status").textContent = songSel >= 0 && songs[songSel] ? rowLabel(songs[songSel]) : "";
  if (songSel < 0) return;
  const row = document.getElementById("song-" + songSel);
  if (!row) return;
  if (scroll) row.scrollIntoView({ block: "nearest" });
  if (focus) row.querySelector(".pick").focus();
}

function toggleActions(i, open) {
  $$("#songs .songrow").forEach((li, j) => {
    const acts = li.querySelector(".rowactions");
    if (!acts) return;
    acts.hidden = !(j === i && (open ?? acts.hidden));
  });
  const row = document.getElementById("song-" + i);
  if (!row) return;
  row.scrollIntoView({ block: "nearest" });
  const acts = row.querySelector(".rowactions");
  if (acts && !acts.hidden) {
    const first = acts.querySelector("button");
    if (first) first.focus();
  }
}

function renderDrawerFilters(force) {
  if (!S || !facets) return;
  const sig = JSON.stringify([facets.lang, facets.missing, S.cfg.lang_filter, lang, missingOnly]);
  if (!force && sig === renderDrawerFilters.sig) return;
  renderDrawerFilters.sig = sig;
  const box = $("#facets-langs");
  box.innerHTML = "";
  const sel = new Set(S.cfg.lang_filter || []);
  const dn = displayNames();
  (facets.lang || []).forEach((code) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = langName(code, dn);
    b.setAttribute("aria-pressed", sel.has(code) ? "true" : "false");
    b.onclick = async () => {
      if (sel.has(code)) sel.delete(code); else sel.add(code);
      await api("config", { lang_filter: [...sel] });
      S.cfg.lang_filter = [...sel];
      renderDrawerFilters(true);
      loadSongs(true);
    };
    box.append(b);
  });
  const mt = $("#missing-toggle");
  mt.textContent = fmt("missing_only", { n: facets.missing ?? 0 });
  mt.setAttribute("aria-pressed", missingOnly ? "true" : "false");
}

// ------------------------------------------------------------------ find lyrics
function openLyricsFor(song) {
  if (!song || song.id == null) { flash(t("nothing_playing")); return; }
  candFor = song;
  cands = [];
  $("#ld-song").textContent = `${t("song_no")} ${song.number} · ${songLine(song)}`;
  $("#ld-artist").value = song.artist || "";
  $("#ld-title-input").value = song.title || "";
  $("#ld-results").innerHTML = "";
  setLyricsStatus("", "");
  // each song starts at its folder's language label (when it is one of the choices), else Detect
  const sel = $("#ld-sr-lang"), code = String(song.lang || "").toLowerCase();
  sel.value = [...sel.options].some((o) => o.value === code) ? code : "auto";
  renderSpeech();
  openOverlay("#lyrics-dialog", "#ld-artist");
  $("#ld-artist").select();
}

function setLyricsStatus(msg, cls) {
  const s = $("#ld-status");
  s.textContent = msg || "";
  s.className = "status" + (cls ? " " + cls : "");
}

async function searchLyrics() {
  if (!candFor) return;
  const btn = $("#ld-search");
  btn.disabled = true;
  $("#ld-results").innerHTML = "";
  setLyricsStatus(t("searching"), "");
  const r = await api("lyrics_search", {
    id: candFor.id,
    artist: $("#ld-artist").value.trim(),
    title: $("#ld-title-input").value.trim(),
  });
  btn.disabled = false;
  cands = (r && r.candidates) || [];
  if (!cands.length) {
    const net = !r || r.error === "network" || r.error === "service unavailable";
    if (net) setLyricsStatus(t("err_network"), "warn");
    else if (r.ok === false && r.error) setLyricsStatus(t("err_generic"), "warn");
    else setLyricsStatus(t("no_matches"), "warn");
    return;
  }
  setLyricsStatus(r.ok ? "" : t("err_generic"), r.ok ? "" : "warn");
  renderCandidates();
  const first = $("#ld-results .cand");
  if (first) first.focus();
}

function renderCandidates() {
  const ul = $("#ld-results");
  ul.innerHTML = "";
  cands.forEach((c, i) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "cand";
    const head = el("div", "cand-head");
    head.append(el("span", "cand-title", `${c.artist || "?"} — ${c.title || "?"}`));
    const meta = [c.album, c.duration ? clock(c.duration) : "", c.delta ? fmt("delta", { n: Math.round(c.delta) }) : "",
      c.synced ? t("synced") : t("plain")].filter(Boolean).join(" · ");
    const prev = (c.preview || []).join("  /  ");
    b.append(head, el("div", "cand-meta", meta), el("div", "cand-prev", prev));
    b.setAttribute("aria-label", fmt("use_lyrics", { s: `${c.artist || "?"} — ${c.title || "?"}` }));
    b.onclick = () => saveCandidate(i);
    li.append(b);
    ul.append(li);
  });
}

// speech recognition: time the known words from the audio, or write down what is sung
function renderSpeech() {
  if (!candFor || !S) return;
  const kindOk = !candFor.kind || candFor.kind === "audio" || candFor.kind === "video";
  const ready = !!S.whisper, tm = S.timing || {};
  const mine = tm.id === candFor.id;
  const none = candFor.lyrics === "none";
  $("#ld-sr-note").textContent = !kindOk ? t("sr_note_kind") : !ready ? t("sr_note_off") : none ? t("sr_note_none") : t("sr_note_known");
  $("#ld-sr-go").disabled = !kindOk || !ready || !!tm.running;
  $("#ld-sr-lang").disabled = !kindOk || !ready;
  const st = $("#ld-sr-status");
  st.className = "status";
  if (tm.running && mine) st.textContent = t("sr_running");
  else if (tm.running) st.textContent = t("sr_busy");
  else if (mine && tm.error) { st.textContent = fmt("sr_failed", { s: tm.error }); st.classList.add("warn"); }
  else if (mine && tm.result) st.textContent = tm.result === "timed" ? fmt("sr_done_timed", { n: Math.round((tm.share || 0) * 100) }) : t("sr_done_transcribed");
  else st.textContent = "";
}

async function startSpeech() {
  if (!candFor) return;
  const r = await api("lyrics_time", { id: candFor.id, lang: $("#ld-sr-lang").value });
  if (!r || !r.ok) {
    const st = $("#ld-sr-status");
    st.textContent = r && r.error === "busy" ? t("sr_busy") : r && r.error === "unavailable" ? t("sr_note_off") : t("err_generic");
    st.className = "status warn";
    return;
  }
  S.timing = { running: true, id: candFor.id };
  renderSpeech();
}

// a finished speech run: update the song's badge and say so, even if the dialog was closed meanwhile
function onTiming(prev, now) {
  if (!prev || !prev.running || (now && now.running)) return;
  if (!now || now.id == null) return;
  if (now.error) flash(fmt("sr_failed", { s: now.error }));
  else if (now.result) {
    songs.forEach((s) => { if (s.id === now.id) s.lyrics = now.status; });
    if (candFor && candFor.id === now.id) candFor.lyrics = now.status;
    if (S.song && S.song.id === now.id) S.song.lyrics = now.status;
    renderSongs();
    facetTick = 0;
    flash(now.result === "timed" ? fmt("sr_done_timed", { n: Math.round((now.share || 0) * 100) }) : t("sr_done_transcribed"));
  }
}

async function saveCandidate(i) {
  const c = cands[i];
  if (!c || !candFor) return;
  setLyricsStatus(t("saving"), "");
  const id = candFor.id;
  const r = await api("lyrics_save", { id, idx: c.idx ?? i });
  if (!r || !r.ok) { setLyricsStatus(t("save_failed"), "warn"); return; }
  songs.forEach((s) => { if (s.id === id) s.lyrics = r.status; });
  if (S && S.song && S.song.id === id) S.song.lyrics = r.status;
  renderSongs();
  facetTick = 0;   // refresh the "missing lyrics" count on the next poll
  flash(t("lyrics_saved"));
  closeOverlay("#lyrics-dialog");
}

// ------------------------------------------------------------------ settings
function nextStart(folders) {
  const maxStart = Math.max(0, ...(folders || []).map((f) => Number(f.start) || 0));
  return String(Math.max(10000, (Math.floor(maxStart / 10000) + 1) * 10000));
}

function scanText() {
  if (!S) return "";
  const sc = S.scan;
  if (sc.error) return fmt("scan_failed", { s: sc.error });
  if (sc.running) return `${t("scanning")} ${sc.count}`;
  return facets ? fmt("song_count", { n: facets.total }) : "";
}

function setField(sel, prop, value) {
  const e = $(sel);
  if (e && document.activeElement !== e) e[prop] = value;
}

function renderSettings() {
  if (!S) return;
  const c = S.cfg;
  setField("#s-lang", "value", c.lang);
  setField("#s-intro", "value", c.intro);
  setField("#s-dedupe", "checked", !!c.dedupe);
  setField("#s-sf", "value", c.soundfont || "");
  setField("#s-inbox", "value", c.inbox || "");

  const fkey = JSON.stringify(c.folders || []);
  if (fkey !== renderSettings.fkey) {
    renderSettings.fkey = fkey;
    const ul = $("#folders");
    ul.innerHTML = "";
    if (!(c.folders || []).length) {
      ul.append(el("li", "muted", t("no_folders")));
    }
    (c.folders || []).forEach((f) => {
      const li = document.createElement("li");
      const txt = el("span", "txt");
      txt.append(el("b", "", f.path),
        el("i", "", `#${f.start} · ${f.lang || "—"} · ${f.country || "—"}`));
      li.append(txt, iconBtn("x", fmt("remove_folder", { s: f.path }), () => askRemoveFolder(f)));
      ul.append(li);
    });
    const start = $("#f-start");
    if (document.activeElement !== start) start.value = nextStart(c.folders);
  }
  $("#scanmsg").textContent = scanText();

  const ikey = JSON.stringify([S.scan.importing, S.scan.log, lang]);
  if (ikey !== renderSettings.ikey) {
    const wasImporting = renderSettings.importing;
    renderSettings.ikey = ikey;
    renderSettings.importing = S.scan.importing;
    if (wasImporting && !S.scan.importing && inbox) refreshInbox();   // imported files left the inbox
    renderImportStatus();
  }
}

const inboxOff = new Set();   // groups the user unticked; everything else is picked
async function refreshInbox() {
  try { inbox = await get("/api/inbox"); }
  catch (e) { inbox = null; flash(t("err_generic")); }
  renderInbox();
}

function renderImportStatus() {
  if (!S) return;
  $("#import-status").textContent = S.scan.importing ? t("importing") : "";
  const log = S.scan.log || [];
  const pre = $("#import-log");
  pre.textContent = log.join("\n");
  pre.hidden = !log.length;
  if (inbox) renderInbox();
}

function renderInbox() {
  const ul = $("#inbox-list");
  ul.innerHTML = "";
  $("#inbox-dest").textContent = inbox ? fmt("import_dest", { s: inbox.dest }) : "";
  const empty = $("#inbox-empty");
  empty.hidden = !(inbox && !(inbox.groups || []).length);
  empty.textContent = inbox ? fmt("inbox_empty", { s: inbox.inbox }) : "";
  const skipped = inbox && (inbox.skipped || []).length ? fmt("inbox_skipped", { s: inbox.skipped.join(", ") }) : "";
  $("#inbox-skipped").textContent = skipped;
  $("#inbox-skipped").hidden = !skipped;
  (inbox ? inbox.groups : []).forEach((g) => {
    const li = document.createElement("li");
    const lab = document.createElement("label");
    lab.className = "check";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = g.name;
    cb.checked = !inboxOff.has(g.name);
    cb.addEventListener("change", () => { cb.checked ? inboxOff.delete(g.name) : inboxOff.add(g.name); });
    const kind = g.kind === "cdg" ? t("kind_cdg") : g.kind === "chorus" ? t("kind_chorus") : t("kind_song");
    const lyr = g.kind === "cdg" || g.has_lrc ? t("has_lyrics") : t("no_lyrics_short");
    lab.append(cb, el("span", "g-name", g.name), el("span", "g-kind", kind), el("span", "g-lyr", lyr));
    li.append(lab);
    ul.append(li);
  });
}

function askRemoveFolder(f) {
  askConfirm(t("remove_folder_q"), t("remove_folder_msg"), () => api("folder_del", { path: f.path }));
}

function askConfirm(title, msg, fn, yesLabel) {
  confirmFn = fn;
  $("#cd-title").textContent = title;
  $("#cd-msg").textContent = msg;
  $("#cd-yes").textContent = yesLabel || t("remove");
  openOverlay("#confirm-dialog", "#cd-no");
}

// ------------------------------------------------------------------ stage drawing
function liveTime() {
  if (!S) return null;
  const ph = S.phase;
  if ((ph !== "playing" && ph !== "paused") || S.pos == null) return null;
  return S.pos + (ph === "playing" ? ((performance.now() - tAt) / 1000) * S.tempo : 0);
}

function frame() {
  requestAnimationFrame(frame);
  if (!S) return;
  const ph = S.phase, tt = liveTime();
  const vid = $("#vid"), cv = $("#cdg");
  vid.hidden = !(tt != null && S.has_video);
  cv.hidden = !(tt != null && S.has_cdg && cdg);

  if (ph === "playing" || ph === "paused") {
    const dur = Number(S.duration) || 0;
    const pos = tt != null ? Math.min(tt, dur || tt) : 0;
    $("#pfill").style.width = dur > 0 ? Math.max(0, Math.min(100, (pos / dur) * 100)) + "%" : "0";
    $("#elapsed").textContent = clock(pos);
    $("#remaining").textContent = "-" + clock(Math.max(0, dur - pos));
  }
  if (ph === "prep" || ph === "intro") {
    const left = Math.max(0, (Number(S.intro_left) || 0) - (performance.now() - tAt) / 1000);
    const total = Math.max(0.001, Number(S.cfg.intro) || 0);
    $("#i-fill").style.width = Math.max(0, Math.min(100, (left / total) * 100)) + "%";
  }
  if (ph === "error") {
    $("#error-skip").textContent = fmt("error_skip", { n: Math.max(0, Math.ceil(5 - (performance.now() - errorAt) / 1000)) });
  }
  if (tt == null) {
    $("#lyrics").hidden = true;
    renderDots(0);
    return;
  }
  if (S.has_video) {
    if (ph === "playing" && vid.paused) vid.play().catch(() => {});
    if (ph !== "playing" && !vid.paused) vid.pause();
    vid.playbackRate = S.tempo;
    if (!vid.seeking && Math.abs(vid.currentTime - tt) > 0.3) vid.currentTime = tt;
  }
  if (cdg) { cdg.advance(tt); cdg.draw(cv.getContext("2d")); }
  renderLyrics(tt - (Number(S.lyric_offset) || 0));
}

function buildLine(node, line, idx) {
  node.textContent = "";
  node.dataset.idx = String(idx);
  (line || []).forEach(([s, e, x]) => {
    const m = /^([\s\S]*?)(\s*)$/.exec(x || "");
    const text = m[1], gap = m[2];
    if (text) {
      const w = document.createElement("span");
      w.className = "w";
      const base = el("span", "u", text);
      const sung = el("span", "s", text);
      sung.setAttribute("aria-hidden", "true");
      w.append(base, sung);
      node.append(w);
      spans.push({ w, s, e, p: -1 });
    }
    if (gap) node.append(document.createTextNode(gap));
  });
}

function renderDots(n) {
  const box = $("#dots");
  const count = Math.max(0, n | 0);
  if (box.dataset.n === String(count)) return;
  box.dataset.n = String(count);
  box.innerHTML = "";
  for (let i = 0; i < count; i++) box.append(document.createElement("i"));
  box.hidden = !count;
}

function renderLyrics(tt) {
  $("#lyrics").hidden = !lines.length;
  if (!lines.length) { renderDots(0); return; }
  const { now: i, page: pg } = pickPage(lines, tt);
  if (pg !== page) {
    page = pg; spans = [];
    buildLine($("#l0"), lines[pg], pg);
    buildLine($("#l1"), lines[pg + 1], pg + 1);
  }
  for (const w of spans) {
    const p = Math.max(0, Math.min(1, (tt - w.s) / Math.max(0.05, w.e - w.s)));
    if (p !== w.p) { w.p = p; w.w.style.setProperty("--p", p * 100 + "%"); }
  }
  $("#l0").classList.toggle("now", i === pg);
  $("#l1").classList.toggle("now", i === pg + 1);

  // count-in dots before the first line or after a long instrumental break
  const ni = lines.findIndex((l) => l[0][0] > tt);
  let dots = 0;
  if (ni >= 0) {
    const prevEnd = ni ? lines[ni - 1][lines[ni - 1].length - 1][1] : -99;
    const wait = lines[ni][0][0] - tt;
    if (wait <= 3.5 && lines[ni][0][0] - prevEnd >= 6) dots = Math.max(1, Math.min(3, Math.ceil(wait)));
  }
  renderDots(dots);
}

// ------------------------------------------------------------------ tap to sync
const lineText = (l) => (l || []).map((w) => w[2]).join("").trim();

function openSync() {
  if (!S || !lines.length || (S.phase !== "playing" && S.phase !== "paused")) { flash(t("sync_need_play")); return; }
  syncIdx = pickPage(lines, (liveTime() ?? 0) - (Number(S.lyric_offset) || 0)).now;
  syncOn = true;
  $("#sync").hidden = false;
  renderSync();
}

function renderSync() {
  if (!S || !lines.length) return;
  $("#sync-pos").textContent = `${fmt("sync_line_n", { i: syncIdx + 1, n: lines.length })} · ${fmt("sync_offset_now", { s: signed(S.lyric_offset || 0) })}`;
  $("#sync-prev").textContent = syncIdx > 0 ? lineText(lines[syncIdx - 1]) : "";
  $("#sync-line").textContent = lineText(lines[syncIdx]);
  $("#sync-next").textContent = syncIdx + 1 < lines.length ? lineText(lines[syncIdx + 1]) : "";
}

function moveSync(d) {
  syncIdx = Math.max(0, Math.min(lines.length - 1, syncIdx + d));
  renderSync();
}

function closeSync() {
  syncOn = false;
  $("#sync").hidden = true;
}

async function applySync() {
  const idx = syncIdx;
  closeSync();
  const r = await api("sync_line", { line: idx });
  if (r && r.ok && r.offset != null) {
    if (S) S.lyric_offset = r.offset;
    flash(fmt("sync_result", { s: signed(r.offset) }));
  } else {
    flash(t("sync_failed"));
  }
}

async function nudge(delta) {
  const r = await api("sync", { delta });
  if (!r || !r.ok) return;
  if (S) S.lyric_offset = Math.round(Math.max(-60, Math.min(60, (Number(S.lyric_offset) || 0) + delta)) * 100) / 100;
  flash(fmt("sync_result", { s: signed(S ? S.lyric_offset : delta) }));
}

async function toggleFullscreen() {
  const r = await api("fullscreen");
  if (!r.ok) document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
}

// ------------------------------------------------------------------ keyboard
function drawerKeys(e, typing) {
  const k = e.key;
  const onPick = !!(e.target.classList && e.target.classList.contains("pick"));
  const inActions = !!(e.target.closest && e.target.closest(".rowactions"));
  if (k === " " && onPick) { e.preventDefault(); return true; }   // Space must not "click" the row
  if (k === "/" && !typing) { e.preventDefault(); $("#q").focus(); $("#q").select(); return true; }
  if ((k === "h" || k === "H") && !typing) { e.preventDefault(); openOverlay("#help", "#help-close"); return true; }
  if (k === "ArrowDown" || k === "ArrowUp") {
    if (!songs.length) return true;
    const dir = k === "ArrowDown" ? 1 : -1;
    songSel = songSel < 0 ? (dir > 0 ? 0 : songs.length - 1) : Math.max(0, Math.min(songs.length - 1, songSel + dir));
    markSelected(true, true);            // arrows move the highlight and hand the keyboard to the list
    e.preventDefault();
    return true;
  }
  if (k === "Enter" && !inActions) {
    if (!typing && !onPick) return false;  // some other button keeps its own Enter
    if (!songs.length) return true;
    if (songSel < 0) songSel = 0;
    const s = songs[songSel];
    e.preventDefault();
    if (e.shiftKey) reserve({ id: s.id, top: true }); else reserve({ id: s.id });
    return true;
  }
  if ((k === "l" || k === "L") && !typing && !inActions) {
    if (songSel < 0) return false;
    e.preventDefault();
    openLyricsFor(songs[songSel]);
    return true;
  }
  return false;
}

function lyricsDialogKeys(e) {
  const k = e.key;
  if (k === "ArrowDown" && e.target.matches("input")) {
    const first = $("#ld-results .cand");
    if (first) { e.preventDefault(); first.focus(); return true; }
    return false;
  }
  if (k === "ArrowDown" || k === "ArrowUp") {
    const list = $$("#ld-results .cand");
    const i = list.indexOf(e.target);
    if (i < 0) return false;
    const next = list[i + (k === "ArrowDown" ? 1 : -1)];
    e.preventDefault();
    (next || (k === "ArrowUp" ? $("#ld-title-input") : list[list.length - 1])).focus();
    return true;
  }
  return false;
}

function onKeyDown(e) {
  if (e.ctrlKey || e.altKey || e.metaKey || e.isComposing) return;
  const k = e.key;
  const tag = (e.target && e.target.tagName || "").toLowerCase();
  const typing = tag === "input" || tag === "select" || tag === "textarea";

  if (syncOn) {
    if (k === "Escape") { e.preventDefault(); closeSync(); return; }
    if (k === "ArrowLeft" || k === ",") { e.preventDefault(); moveSync(-1); return; }
    if (k === "ArrowRight" || k === ".") { e.preventDefault(); moveSync(1); return; }
    if (k === "Enter" || k.toLowerCase() === "t") { e.preventDefault(); applySync(); return; }
    return;
  }

  const top = stack[stack.length - 1];
  if (top) {
    if (k === "Tab") { trapTab(e, top.el); return; }
    if (k === "Escape") {
      e.preventDefault();
      const esc = overlayEscapes.get(top.el);
      if (esc && esc()) return;
      closeOverlay(top.el);
      return;
    }
    if ((k === "u" || k === "U") && !typing) { e.preventDefault(); doUndo(); return; }
    const fn = overlayKeys.get(top.el);
    if (fn && fn(e, typing)) return;
    return;
  }

  const numin = $("#numin");
  if (e.target === numin) {
    if (/^[0-9]$/.test(k)) return;
    if (k === "Enter") { e.preventDefault(); reserveEntry(); return; }
    if (k === "Backspace" || k === "Delete" || k === "ArrowLeft" || k === "ArrowRight" || k === "Home" || k === "End") return;
  } else if (typing) {
    if (k === "Escape") e.target.blur();
    return;
  }

  if (/^[0-9]$/.test(k)) { e.preventDefault(); setEntry(entry + k); if (S && S.phase === "idle") focusNum(); return; }
  if (k === "Enter") { if (entry) { e.preventDefault(); reserveEntry(); } return; }
  if (k === "Backspace") { e.preventDefault(); setEntry(entry.slice(0, -1)); return; }
  if (k === "Escape") { if (entry) { e.preventDefault(); setEntry(""); } return; }
  if (k === "Tab" || k === "/") { e.preventDefault(); openDrawer(); return; }

  const key = k.length === 1 ? k.toLowerCase() : k;
  const map = {
    " ": () => api("pause"),
    n: () => api("next"),
    r: () => api("restart"),
    "+": () => api("key", { delta: 1 }),
    "=": () => api("key", { delta: 1 }),
    "-": () => api("key", { delta: -1 }),
    "]": () => api("tempo", { delta: 0.05 }),
    "[": () => api("tempo", { delta: -0.05 }),
    ",": () => nudge(-0.25),
    ".": () => nudge(0.25),
    "<": () => nudge(-2),
    ">": () => nudge(2),
    m: () => api("melody"),
    c: () => api("chorus"),
    f: toggleFullscreen,
    t: openSync,
    l: () => (S && S.song ? openLyricsFor(S.song) : flash(t("nothing_playing"))),
    q: openQueue,
    s: openSettings,
    h: () => openOverlay("#help", "#help-close"),
    u: doUndo,
    ArrowUp: () => api("volume", { delta: 5 }),
    ArrowDown: () => api("volume", { delta: -5 }),
  };
  const fn = map[key];
  if (fn) { e.preventDefault(); fn(); }
}

// ------------------------------------------------------------------ settings wiring
function openSettings() {
  if (!$("#settings-panel").hidden) return;
  openOverlay("#settings-panel", "#s-lang");
  renderSettings();
}

function wireSettings() {
  $("#s-lang").addEventListener("change", (e) => {
    lang = e.target.value;           // instant feedback; the server confirms on the next poll
    applyI18n();
    api("config", { lang });
  });
  $("#s-intro").addEventListener("change", (e) => {
    const v = Math.max(0, Math.min(30, Number(e.target.value) || 0));
    e.target.value = String(v);
    api("config", { intro: v });
  });
  $("#s-dedupe").addEventListener("change", (e) => {
    api("config", { dedupe: e.target.checked });
    setTimeout(() => loadSongs(true), 150);
  });
  $("#s-sf").addEventListener("change", (e) => api("config", { soundfont: e.target.value.trim() }));
  $("#s-inbox").addEventListener("change", (e) => api("config", { inbox: e.target.value.trim() }));
  $("#scan-btn").addEventListener("click", async () => {
    $("#scan-btn").disabled = true;
    await api("scan", { rebuild: false });
    $("#scan-btn").disabled = false;
    flash(t("scanning"));
  });

  $("#addfolder").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      path: String(fd.get("path") || "").trim(),
      start: Math.max(1, Number(fd.get("start")) || 10000),
      lang: String(fd.get("lang") || "").trim(),
      country: String(fd.get("country") || "").trim(),
    };
    if (!body.path) return;
    const r = await api("folder_add", body);
    if (!r.ok) { flash(t(r.error) || t("notdir")); return; }
    e.target.reset();
    renderSettings.fkey = null;
    renderSettings();
  });

  $("#ld-sr-go").addEventListener("click", startSpeech);

  $("#inbox-check").addEventListener("click", async () => {
    const btn = $("#inbox-check");
    btn.disabled = true;
    await refreshInbox();
    btn.disabled = false; btn.focus();   // disabling dropped the focus to the top of the sheet
  });

  $("#inbox-import").addEventListener("click", async () => {
    const names = $$("#inbox-list input:checked").map((c) => c.value);
    if (!names.length) { flash(t("select_one")); return; }
    const r = await api("inbox_import", { names });
    if (!r || !r.ok) { flash(r && r.error === "busy" ? t("import_busy") : t("import_nothing")); return; }
    flash(t("importing"));
  });

  $("#run-doctor").addEventListener("click", async () => {
    const btn = $("#run-doctor");
    btn.disabled = true;
    $("#doctor-out").textContent = "…";
    try { $("#doctor-out").textContent = (await get("/api/doctor")).report; }
    catch (e) { $("#doctor-out").textContent = t("err_generic"); }
    btn.disabled = false; btn.focus();
  });

  $("#rebuild-word").addEventListener("input", (e) => {
    $("#rebuild-btn").disabled = e.target.value.trim() !== "REBUILD";
  });
  $("#rebuild-btn").addEventListener("click", async () => {
    if ($("#rebuild-word").value.trim() !== "REBUILD") return;
    $("#rebuild-word").value = "";
    $("#rebuild-btn").disabled = true;
    flash(t("rebuilding"));
    await api("scan", { rebuild: true });
  });
  $("#quit-btn").addEventListener("click", () => askConfirm(t("quit_q"), t("quit_msg"), () => api("quit"), t("quit")));
}

function wireOverlays() {
  $("#drawer-close").addEventListener("click", () => closeOverlay("#drawer"));
  $("#queue-close").addEventListener("click", () => closeOverlay("#queue-panel"));
  $("#settings-close").addEventListener("click", () => closeOverlay("#settings-panel"));
  $("#help-close").addEventListener("click", () => closeOverlay("#help"));
  $("#ld-close").addEventListener("click", () => closeOverlay("#lyrics-dialog"));
  $("#cd-yes").addEventListener("click", async () => {
    const fn = confirmFn;
    confirmFn = null;
    closeOverlay("#confirm-dialog");
    if (fn) await fn();
  });
  $("#cd-no").addEventListener("click", () => { confirmFn = null; closeOverlay("#confirm-dialog"); });

  overlayKeys.set($("#drawer"), drawerKeys);
  overlayKeys.set($("#lyrics-dialog"), lyricsDialogKeys);
  overlayEscapes.set($("#drawer"), () => {
    const open = $$("#songs .rowactions").filter((a) => !a.hidden);
    if (!open.length) return false;
    open.forEach((a) => { a.hidden = true; });
    $("#q").focus();
    return true;
  });

  $("#q").addEventListener("input", () => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => loadSongs(true), 180);
  });
  $("#more").addEventListener("click", () => loadSongs(false));
  $("#missing-toggle").addEventListener("click", () => {
    missingOnly = !missingOnly;
    $("#missing-toggle").setAttribute("aria-pressed", missingOnly ? "true" : "false");
    renderDrawerFilters.sig = "";
    renderDrawerFilters(true);
    loadSongs(true);
  });

  $("#lyrics-form").addEventListener("submit", (e) => { e.preventDefault(); searchLyrics(); });

  $("#queue-clear").addEventListener("click", clearQueue);
  $("#t-restart").addEventListener("click", () => api("restart"));
  $("#t-pause").addEventListener("click", () => api("pause"));
  $("#t-next").addEventListener("click", () => api("next"));

  $("#numin").addEventListener("input", onNumInput);
  $("#toast-undo").addEventListener("click", doUndo);
}

// ------------------------------------------------------------------ errors go to the log (kuraoke-kami --doctor shows them)
let reported = 0;
function report(msg) {
  if (reported++ < 10) api("clientlog", { msg: String(msg).slice(0, 500) }).catch(() => {});
}

// ------------------------------------------------------------------ boot
applyI18n();
wireOverlays();
wireSettings();
setTransport("idle");
addEventListener("keydown", onKeyDown);
addEventListener("error", (e) => report(`${e.message} at ${(e.filename || "").split("/").pop()}:${e.lineno}`));
addEventListener("unhandledrejection", (e) => report("promise: " + ((e.reason && e.reason.message) || e.reason)));
// closing the TV window stops the whole app (the server waits 3 s so a reload doesn't count)
if (DISPLAY) addEventListener("pagehide", () => navigator.sendBeacon(mediaUrl("/api/display_closed")));
requestAnimationFrame(frame);
poll();
