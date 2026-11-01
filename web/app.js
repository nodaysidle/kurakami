"use strict";
const KK = window.KK || {};
const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
const DISPLAY = !!KK.display;
let S = null, loadedRev = -1, tAt = 0, lang = "en", rev = -1, lines = [], cdg = null, entry = "", page = -1, spans = [], tick = 0;

// ------------------------------------------------------------------ i18n
const t = (k) => (I18N[lang] && I18N[lang][k]) ?? I18N.en[k] ?? k;
function applyI18n() {
  document.documentElement.lang = lang;
  $$("[data-i18n]").forEach((e) => (e.textContent = t(e.dataset.i18n)));
  $$("[data-i18n-title]").forEach((e) => (e.title = t(e.dataset.i18nTitle)));
  $$("[data-i18n-ph]").forEach((e) => (e.placeholder = t(e.dataset.i18nPh)));
  for (const id of ["#keys", "#idle-keys", "#keyhelp"]) $(id).textContent = t("keys");
}

// ------------------------------------------------------------------ api
const H = { "X-Token": KK.token || "" };
const get = (p) => fetch(p, { headers: H }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
const api = (name, body = {}) =>
  fetch("/api/" + name, { method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
const mediaUrl = (p) => `${p}?t=${encodeURIComponent(KK.token || "")}`;

let toastTimer;
function flash(msg) {
  const el = $("#toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}
const label = (s) => (s ? `${t("song_no")} ${s.number} · ${s.title}${s.artist ? " — " + s.artist : ""}` : "");

async function reserve(body) {
  const r = await api("reserve", body);
  flash(r.ok ? `${t("added")}: ${label(r.song)}` : t("notfound"));
  return r;
}

// ------------------------------------------------------------------ polling
let facetTick = 0;
async function poll() {
  try {
    const q = [DISPLAY && "d=1", facetTick++ % 12 === 0 && "facets=1"].filter(Boolean).join("&");
    onState(await get("/api/state?" + q));
    $("#app").classList.remove("offline");
  } catch (e) { $("#app").classList.add("offline"); }
  setTimeout(poll, 400);
}

async function onState(s) {
  const first = !S;
  if (s.facets) s.facets_ = s.facets; else if (S) s.facets_ = S.facets_;
  S = s; tAt = performance.now();
  if (s.cfg.lang !== lang) { lang = s.cfg.lang; applyI18n(); renderAll(); }
  if (s.rev !== rev) {
    rev = s.rev; loadedRev = -1; page = -1; cdg = null; lines = [];
    $("#vid").removeAttribute("src");
  }
  if (s.song && s.phase !== "prep" && s.phase !== "error" && loadedRev !== rev) {
    loadedRev = rev;
    await loadSong(s);
  }
  render();
  if (first) renderAll();
}

async function loadSong(s) {
  lines = (await get("/api/lyrics")).lines;
  if (s.has_video) $("#vid").src = mediaUrl(`/media/${s.song.id}/video`);
  if (s.has_cdg) {
    const buf = await (await fetch(mediaUrl(`/media/${s.song.id}/cdg`))).arrayBuffer();
    cdg = new CDG(buf);
  }
}

// ------------------------------------------------------------------ panel rendering
function render() {
  const s = S, song = s.song;
  $("#np-t").textContent = song ? song.title : t("nothing");
  $("#np-a").textContent = song ? `${t("song_no")} ${song.number}${song.artist ? " · " + song.artist : ""}` : "";
  $("#bar-fill").style.width = s.pos != null && s.duration ? `${Math.min(100, (s.pos / s.duration) * 100)}%` : "0";
  $("#o-key").textContent = (s.key > 0 ? "+" : "") + s.key;
  $("#o-tempo").textContent = Math.round(s.tempo * 100) + "%";
  $("#o-vol").textContent = s.volume;
  $("#o-sync").textContent = (s.lyric_offset > 0 ? "+" : "") + s.lyric_offset.toFixed(2) + " s";
  for (const k of ["melody", "chorus"]) {
    const b = $("#b-" + k);
    b.textContent = `${t(k)}: ${s[k] ? t("on") : t("off")}`;
    b.classList.toggle("on", s[k] && s.caps[k]);
    b.disabled = !s.caps[k];
    b.title = s.caps[k] ? "" : t("no_layer");
  }
  $("#t-queue").textContent = `${t("queue")}${s.queue.length ? " (" + s.queue.length + ")" : ""}`;
  $("#remote-url").textContent = s.remote;
  $("#scanmsg").textContent = s.scan.error || (s.scan.running ? `${t("scanning")} ${s.scan.count}` : s.facets_ ? `${t("scanned")}: ${s.facets_.total}` : "");
  renderQueue();
  renderSettings();
  renderFacets();
  if (DISPLAY) renderStageStatic();
}

function renderQueue() {
  const key = JSON.stringify(S.queue.map((q) => q.qid));
  if (key === renderQueue.key) return;
  renderQueue.key = key;
  const ol = $("#queue");
  ol.innerHTML = "";
  if (!S.queue.length) ol.innerHTML = `<li class="muted">${t("empty_queue")}</li>`;
  S.queue.forEach((q, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="t"><b></b><i></i></span>`;
    li.querySelector("b").textContent = `${i + 1}. ${q.song.title}`;
    li.querySelector("i").textContent = `${t("song_no")} ${q.song.number}${q.song.artist ? " · " + q.song.artist : ""}`;
    if (i > 0) li.append(btn("⤒", t("top"), () => api("top", { qid: q.qid })));
    li.append(btn("✕", t("remove"), () => api("unqueue", { qid: q.qid })));
    ol.append(li);
  });
}

function btn(text, title, fn, cls = "sm") {
  const b = document.createElement("button");
  b.textContent = text; b.title = title; b.className = cls; b.onclick = fn;
  return b;
}

function chips(el, key, values) {
  const sel = new Set(S.cfg[key]);
  el.innerHTML = "";
  values.forEach((v) => {
    const b = btn(v, v, async () => {
      sel.has(v) ? sel.delete(v) : sel.add(v);
      await api("config", { [key]: [...sel] });
      S.cfg[key] = [...sel]; renderFacets(true); loadSongs(true);
    }, "chip" + (sel.has(v) ? " on" : ""));
    el.append(b);
  });
}

function renderFacets(force) {
  const f = S.facets_;
  if (!f) return;
  const key = JSON.stringify([f, S.cfg.lang_filter, S.cfg.country_filter]);
  if (!force && key === renderFacets.key) return;
  renderFacets.key = key;
  chips($("#s-langs"), "lang_filter", f.lang);
  chips($("#s-countries"), "country_filter", f.country);
  chips($("#facets"), "lang_filter", f.lang);
}

function renderSettings() {
  const c = S.cfg, set = (id, prop, v) => { const e = $(id); if (document.activeElement !== e) e[prop] = v; };
  set("#s-lang", "value", c.lang); set("#s-dedupe", "checked", c.dedupe);
  set("#s-intro", "value", c.intro); set("#s-sf", "value", c.soundfont); set("#s-remote", "checked", c.remote);
  const key = JSON.stringify(c.folders);
  if (key === renderSettings.key) return;
  renderSettings.key = key;
  const ul = $("#folders");
  ul.innerHTML = "";
  c.folders.forEach((f) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="t"><b></b><i></i></span>`;
    li.querySelector("b").textContent = f.path;
    li.querySelector("i").textContent = `#${f.start} · ${f.lang || "—"} · ${f.country || "—"}`;
    li.append(btn("✕", t("remove"), () => api("folder_del", { path: f.path })));
    ul.append(li);
  });
}

function renderAll() { renderQueue.key = renderSettings.key = renderFacets.key = null; if (S) { render(); } loadSongs(true); }

// ------------------------------------------------------------------ song book
let songOffset = 0, qTimer;
async function loadSongs(reset) {
  if (reset) songOffset = 0;
  const q = $("#q").value;
  const r = await get(`/api/songs?q=${encodeURIComponent(q)}&offset=${songOffset}`);
  const ul = $("#songs");
  if (reset) ul.innerHTML = "";
  r.songs.forEach((s) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n"></span><span class="t"><b></b><i></i></span><span class="k"></span>`;
    li.querySelector(".n").textContent = s.number;
    li.querySelector("b").textContent = s.title;
    li.querySelector("i").textContent = s.artist + (s.lang ? ` · ${s.lang}` : "");
    li.querySelector(".k").textContent = s.kind;
    li.append(btn("＋", t("reserve"), () => reserve({ id: s.id })));
    li.append(btn("⤒", t("sing_next"), () => reserve({ id: s.id, top: true })));
    ul.append(li);
  });
  songOffset += r.songs.length;
  $("#more").hidden = !r.more;
}
$("#q").addEventListener("input", () => { clearTimeout(qTimer); qTimer = setTimeout(() => loadSongs(true), 200); });
$("#more").onclick = () => loadSongs(false);

// ------------------------------------------------------------------ stage
function renderStageStatic() {
  const s = S, st = $("#stage"), ph = s.phase;
  st.dataset.phase = ph;
  st.dataset.kind = s.kind || "";
  $("#idle").hidden = ph !== "idle";
  $("#intro").hidden = !(ph === "prep" || ph === "intro");
  $("#error").hidden = ph !== "error";
  $("#error").textContent = s.error;
  const next = s.queue[0];
  if (s.song) {
    $("#i-num").textContent = `${t("song_no")} ${s.song.number}`;
    $("#i-title").textContent = s.song.title;
    $("#i-artist").textContent = s.song.artist;
  }
  $("#i-next").textContent = next ? `${t("up_next")}: ${label(next.song)}` : (ph === "prep" ? t("preparing") : "");
  $("#nextbar").textContent = next ? `${t("up_next")}: ${label(next.song)}` : "";
  $("#chips").textContent = s.song ? `${t("key")} ${(s.key > 0 ? "+" : "") + s.key}  ·  ${t("tempo")} ${Math.round(s.tempo * 100)}%` +
    (s.caps.melody ? `  ·  ${t("melody")} ${s.melody ? t("on") : t("off")}` : "") + (s.caps.chorus ? `  ·  ${t("chorus")} ${s.chorus ? t("on") : t("off")}` : "") : "";
  $("#idle-url").textContent = s.remote;
  $("#hud").hidden = !(ph === "playing" || ph === "paused");
  $("#entry").textContent = entry ? `${t("song_no")} ${entry}` : "";
  $("#entry").hidden = !entry;
}

function build(el, line, idx) {
  el.textContent = "";
  el.dataset.idx = idx;
  (line || []).forEach(([s, e, x]) => {
    const sp = document.createElement("span");
    sp.textContent = x;
    el.append(sp);
    spans.push({ sp, s, e, idx, p: -1 });
  });
}

function frame() {
  requestAnimationFrame(frame);
  if (!S || !DISPLAY) return;
  const ph = S.phase, playing = ph === "playing" || ph === "paused";
  const tt = playing && S.pos != null ? S.pos + (ph === "playing" ? ((performance.now() - tAt) / 1000) * S.tempo : 0) : null;
  const vid = $("#vid"), cv = $("#cdg");
  vid.hidden = !(playing && S.has_video);
  cv.hidden = !(playing && S.has_cdg && cdg);
  if (tt == null) { $("#lyrics").hidden = true; $("#dots").textContent = ""; return; }
  if (S.has_video) {
    if (ph === "playing" && vid.paused) vid.play().catch(() => {});
    if (ph !== "playing" && !vid.paused) vid.pause();
    vid.playbackRate = S.tempo;
    if (!vid.seeking && Math.abs(vid.currentTime - tt) > 0.3) vid.currentTime = tt;
  }
  if (cdg) { cdg.advance(tt); cdg.draw(cv.getContext("2d")); }
  renderLyrics(tt - (S.lyric_offset || 0));   // per-song lyric sync nudge
}

function renderLyrics(tt) {
  $("#lyrics").hidden = !lines.length;
  if (!lines.length) return;
  const { now: i, page: pg } = pickPage(lines, tt);
  if (pg !== page) {
    page = pg; spans = [];
    build($("#l0"), lines[pg], pg); build($("#l1"), lines[pg + 1], pg + 1);
  }
  for (const w of spans) {
    const p = Math.max(0, Math.min(1, (tt - w.s) / Math.max(0.05, w.e - w.s)));
    if (p !== w.p) { w.p = p; w.sp.style.setProperty("--p", p * 100 + "%"); }
  }
  $("#l0").classList.toggle("now", i === pg);
  $("#l1").classList.toggle("now", i === pg + 1);
  // count-in dots before the first line or after a long instrumental break
  const ni = lines.findIndex((l) => l[0][0] > tt);
  let dots = "";
  if (ni >= 0) {
    const prevEnd = ni ? lines[ni - 1][lines[ni - 1].length - 1][1] : -99;
    const wait = lines[ni][0][0] - tt;
    if (wait <= 3.5 && lines[ni][0][0] - prevEnd >= 6) dots = "●".repeat(Math.max(1, Math.min(3, Math.ceil(wait)))).split("").join(" ");
  }
  $("#dots").textContent = dots;
}

// ------------------------------------------------------------------ menu / tabs
function showTab(name) {
  $$("main > section").forEach((s) => (s.hidden = s.id !== "p-" + name));
  $$("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  if (name === "songs") { loadSongs(true); }
}
$$("nav button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
const menu = (on) => document.body.classList.toggle("menu", on ?? !document.body.classList.contains("menu"));
$("#close").onclick = () => menu(false);

// ------------------------------------------------------------------ controls (buttons)
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-a]");
  if (!b || b.tagName !== "BUTTON") return;
  const a = b.dataset.a, body = {};
  if (b.dataset.d != null) body.delta = Number(b.dataset.d);
  if (b.dataset.v != null) body.value = Number(b.dataset.v);
  if (a === "scan") body.rebuild = b.dataset.rebuild === "1";
  if (a === "fullscreen") return toggleFullscreen();
  if (a === "scan" && body.rebuild && !confirm(t("rebuild") + "?")) return;
  api(a, body);
});

async function nudge(delta) {
  await api("sync", { delta });
  const o = (await get("/api/state")).lyric_offset;
  flash(`${t("lyrics")} ${o > 0 ? "+" : ""}${o.toFixed(2)} s`);
}

async function toggleFullscreen() {
  const r = await api("fullscreen");
  if (!r.ok && DISPLAY) document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
}

$("#numform").onsubmit = async (e) => {
  e.preventDefault();
  const n = $("#numin").value.trim();
  if (n && (await reserve({ number: Number(n) })).ok) $("#numin").value = "";
};

$("#addfolder").onsubmit = async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  const r = await api("folder_add", f);
  if (!r.ok) return flash(t(r.error));
  e.target.reset();
};

const cfgInput = (id, key, read) => $(id).addEventListener("change", () => api("config", { [key]: read($(id)) }));
cfgInput("#s-lang", "lang", (e) => e.value);
cfgInput("#s-dedupe", "dedupe", (e) => e.checked);
cfgInput("#s-intro", "intro", (e) => Number(e.value));
cfgInput("#s-sf", "soundfont", (e) => e.value.trim());
cfgInput("#s-remote", "remote", (e) => e.checked);
$("#s-dedupe").addEventListener("change", () => setTimeout(() => loadSongs(true), 150));

// ------------------------------------------------------------------ keyboard (display window)
addEventListener("keydown", (e) => {
  if (e.target.matches("input,select,textarea")) { if (e.key === "Escape") e.target.blur(); return; }
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  const k = e.key;
  const go = (fn) => { e.preventDefault(); fn(); };
  if (/^[0-9]$/.test(k)) return go(() => { entry = (entry + k).slice(0, 8); renderStageStatic(); });
  if (k === "Enter" && entry) return go(async () => { const n = entry; entry = ""; renderStageStatic(); await reserve({ number: Number(n) }); });
  if (k === "Backspace" && entry) return go(() => { entry = entry.slice(0, -1); renderStageStatic(); });
  if (k === "Escape") return go(() => { entry = ""; menu(false); });
  if (k === "Tab") return go(() => menu());
  if (k === "/") return go(() => { menu(true); showTab("songs"); $("#q").focus(); });
  const map = {
    " ": () => api("pause"), n: () => api("next"), r: () => api("restart"),
    "+": () => api("key", { delta: 1 }), "=": () => api("key", { delta: 1 }), "-": () => api("key", { delta: -1 }),
    "]": () => api("tempo", { delta: 0.05 }), "[": () => api("tempo", { delta: -0.05 }),
    h: () => ($("#keyhelp").hidden = !$("#keyhelp").hidden),
    ",": () => nudge(-0.25), ".": () => nudge(0.25), "<": () => nudge(-2), ">": () => nudge(2),
    m: () => api("melody"), c: () => api("chorus"), f: toggleFullscreen,
    q: () => { menu(true); showTab("queue"); }, s: () => { menu(true); showTab("set"); },
    ArrowUp: () => api("volume", { delta: 5 }), ArrowDown: () => api("volume", { delta: -5 }),
  };
  if (map[k.length === 1 ? k.toLowerCase() : k]) go(map[k.length === 1 ? k.toLowerCase() : k]);
});

// ------------------------------------------------------------------ errors go to the log (kuraoke-kami --doctor shows them)
let reported = 0;
function report(msg) { if (reported++ < 10) api("clientlog", { msg }).catch(() => {}); }
addEventListener("error", (e) => report(`${e.message} at ${(e.filename || "").split("/").pop()}:${e.lineno}`));
addEventListener("unhandledrejection", (e) => report("promise: " + (e.reason && e.reason.message || e.reason)));

$("#run-doctor").onclick = async () => { $("#doctor-out").textContent = (await get("/api/doctor")).report; };

// ------------------------------------------------------------------ boot
// closing the TV window stops the whole app (the server waits 3 s so a reload doesn't count)
if (DISPLAY) addEventListener("pagehide", () => navigator.sendBeacon(mediaUrl("/api/display_closed")));
document.body.classList.toggle("display", DISPLAY);
$("#stage").hidden = !DISPLAY;
$("#qr").src = mediaUrl("/api/qr.svg");
$("#qr").onerror = () => ($("#qr").hidden = true);
applyI18n();
showTab(DISPLAY ? "songs" : "sing");
if (DISPLAY) { document.body.classList.remove("menu"); requestAnimationFrame(frame); }
poll();
