var cur = {slug: "", title: "", ep: 1, mode: "sub", quality: "best", res: null, eps: []};
var focusIdx = -1, lastResults = [];
function $(id) { return document.getElementById(id); }
function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function toast(msg, ms) {
  $("toast-msg").textContent = msg;
  $("toast").classList.remove("hidden");
  clearTimeout(window._toastT);
  window._toastT = setTimeout(function () { $("toast").classList.add("hidden"); }, ms || 2200);
}
function loadPrefs() {
  try {
    if (localStorage.getItem("tatap_crt") === "off") { document.body.classList.add("no-crt"); $("tgl-crt").checked = false; }
    if (localStorage.getItem("tatap_ambient") === "off") { document.body.classList.add("no-ambient"); $("tgl-ambient").checked = false; }
  } catch (e) {}
}
function recent() { try { return JSON.parse(localStorage.getItem("tatap_recent") || "[]"); } catch (e) { return []; } }
function pushRecent(q) {
  try {
    var r = recent().filter(function (x) { return x !== q; });
    r.unshift(q); localStorage.setItem("tatap_recent", JSON.stringify(r.slice(0, 6)));
    renderChips();
  } catch (e) {}
}
function renderChips() {
  var r = recent();
  var box = $("recent-chips");
  box.innerHTML = "";
  for (var i = 0; i < r.length; i++) {
    (function (q) {
      var b = document.createElement("button");
      b.className = "chip"; b.textContent = q;
      b.addEventListener("click", function () { $("q").value = q; doSearch(); });
      box.appendChild(b);
    })(r[i]);
  }
}
async function init() {
  loadPrefs();
  renderChips();
  renderContinue();
  try {
    var h = await window.Tatap.health();
    var el = $("health");
    el.textContent = h.success ? (h.data.reachable ? "hianime OK" : "hianime down") : "api error";
    el.className = "health " + (h.success && h.data.reachable ? "ok" : "bad");
  } catch (e) { $("health").textContent = "offline"; $("health").className = "health bad"; }
  var deb = null;
  $("q").addEventListener("input", function () {
    $("q-clear").classList.toggle("hidden", !$("q").value);
    clearTimeout(deb); deb = setTimeout(function () { if ($("q").value.trim().length >= 3) doSearch(); }, 600);
  });
  $("q").addEventListener("keydown", function (e) {
    if (e.key === "Enter") doSearch();
    else if (e.key === "ArrowDown") { e.preventDefault(); moveFocus(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveFocus(-1); }
  });
  $("q-clear").addEventListener("click", function () { $("q").value = ""; $("q-clear").classList.add("hidden"); $("q").focus(); });
  $("brand-home").addEventListener("click", goHome);
  $("tgl-crt").addEventListener("change", function () {
    document.body.classList.toggle("no-crt", !this.checked);
    try { localStorage.setItem("tatap_crt", this.checked ? "on" : "off"); } catch (e) {}
    toast(this.checked ? "Efek CRT: ON" : "Efek CRT: OFF");
  });
  $("tgl-ambient").addEventListener("change", function () {
    document.body.classList.toggle("no-ambient", !this.checked);
    try { localStorage.setItem("tatap_ambient", this.checked ? "on" : "off"); } catch (e) {}
    toast(this.checked ? "Ambient light: ON" : "Ambient light: OFF");
  });
  $("clear-hist").addEventListener("click", async function () {
    await fetch("/api/history", {method: "DELETE"}); renderContinue(); toast("History dihapus");
  });
  document.querySelectorAll("#mode-seg button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#mode-seg button").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active"); cur.mode = b.getAttribute("data-mode"); loadEps();
    });
  });
  document.querySelectorAll("#quality-seg button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#quality-seg button").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active"); cur.quality = b.getAttribute("data-q");
    });
  });
  $("ep-filter").addEventListener("input", renderEpGrid);
  $("tm-close").addEventListener("click", closeTitle);
  $("title-modal").addEventListener("click", function (e) { if (e.target === this) closeTitle(); });
  $("pm-close").addEventListener("click", closePlayer);
  $("player-modal").addEventListener("click", function (e) { if (e.target === this) closePlayer(); });
  $("pm-prev").addEventListener("click", function () { stepEp(-1); });
  $("pm-next").addEventListener("click", function () { stepEp(1); });
  $("pm-mpv").addEventListener("click", playMPV);
  document.addEventListener("keydown", onKey);
  startAmbient();
}
function goHome() { $("q").value = ""; $("results").innerHTML = ""; $("results-title").textContent = "Mulai pencarian di atas"; $("results-meta").textContent = ""; $("empty-state").style.display = ""; renderContinue(); }
function onKey(e) {
  var t = (e.target.tagName || "");
  var typing = t === "INPUT" || t === "SELECT" || t === "TEXTAREA";
  if (e.key === "Escape") {
    if (!$("player-modal").classList.contains("hidden")) closePlayer();
    else if (!$("title-modal").classList.contains("hidden")) closeTitle();
    return;
  }
  if (typing) { if (e.key === "Escape") e.target.blur(); return; }
  var v = $("vid");
  if (e.key === "/") { e.preventDefault(); $("q").focus(); }
  else if (e.key === " ") { e.preventDefault(); if (v.paused) v.play(); else v.pause(); }
  else if (e.key === "n") stepEp(1);
  else if (e.key === "p") stepEp(-1);
  else if (e.key === "m") v.muted = !v.muted;
  else if (e.key === "ArrowRight") v.currentTime += 5;
  else if (e.key === "ArrowLeft") v.currentTime -= 5;
}
async function doSearch() {
  var q = $("q").value.trim();
  if (!q) return;
  pushRecent(q);
  $("empty-state").style.display = "none";
  $("results-title").textContent = "Mencari " + q + "...";
  $("results-meta").textContent = "";
  var t0 = Date.now();
  var r = await window.Tatap.search(q);
  if (!r.success) { $("results-title").textContent = "Error"; $("results-meta").textContent = r.error || "?"; return; }
  lastResults = r.data.results || [];
  focusIdx = -1;
  $("results-title").textContent = lastResults.length ? ("Hasil untuk \"" + q + "\"") : ("Tidak ketemu \"" + q + "\"");
  $("results-meta").textContent = lastResults.length ? (lastResults.length + " judul · " + (Date.now() - t0) + "ms" + (r.data.cached ? " · cached" : "")) : "";
  renderCards();
}
function renderCards() {
  var box = $("results"); box.innerHTML = "";
  for (var i = 0; i < lastResults.length; i++) {
    (function (a, idx) {
      var d = document.createElement("div");
      d.className = "card" + (idx === focusIdx ? " focused" : "");
      d.tabIndex = 0;
      var b = document.createElement("b"); b.textContent = a.title; d.appendChild(b);
      var s = document.createElement("small"); s.textContent = a.id; d.appendChild(s);
      var n = document.createElement("div"); n.className = "card-num"; n.textContent = "#" + (idx + 1); d.insertBefore(n, b);
      d.addEventListener("click", function () { openTitle(a.id, a.title); });
      d.addEventListener("keydown", function (e) { if (e.key === "Enter") openTitle(a.id, a.title); });
      box.appendChild(d);
    })(lastResults[i], i);
  }
}
function moveFocus(d) {
  if (!lastResults.length) return;
  focusIdx = (focusIdx + d + lastResults.length) % lastResults.length;
  renderCards();
  var cards = $("results").querySelectorAll(".card");
  if (cards[focusIdx]) { cards[focusIdx].focus(); cards[focusIdx].scrollIntoView({block: "nearest"}); }
  if (d !== 0 && document.activeElement === $("q")) {
    var a = lastResults[focusIdx];
  }
}
async function openTitle(slug, title) {
  cur.slug = slug; cur.title = title; cur.eps = [];
  $("tm-title").textContent = title;
  $("tm-sub").textContent = slug;
  $("tm-eyebrow").textContent = "DETAIL ANIME";
  $("tm-count").textContent = "memuat...";
  $("tm-eps").innerHTML = "";
  $("ep-filter").value = "";
  $("title-modal").classList.remove("hidden");
  await loadEps();
}
async function loadEps() {
  var r = await window.Tatap.episodes(cur.slug);
  if (!r.success) { $("tm-count").textContent = "error: " + r.error; return; }
  cur.eps = r.data.episodes || [];
  var watched = {};
  try {
    var h = await window.Tatap.history();
    (h.data || []).forEach(function (x) { if (x.slug === cur.slug) watched[x.episode] = 1; });
  } catch (e) {}
  cur.watched = watched;
  $("tm-count").textContent = cur.eps.length + " episode · " + cur.mode.toUpperCase();
  renderEpGrid();
}
function renderEpGrid() {
  var f = $("ep-filter").value.trim();
  var box = $("tm-eps"); box.innerHTML = "";
  var shown = 0;
  for (var i = 0; i < cur.eps.length; i++) {
    (function (ep) {
      if (f && String(ep).indexOf(f) < 0) return;
      shown++;
      var b = document.createElement("button");
      b.className = "ep" + (cur.watched && cur.watched[ep] ? " watched" : "");
      b.textContent = ep;
      b.addEventListener("click", function () { openPlayer(ep); });
      box.appendChild(b);
    })(cur.eps[i].ep);
  }
  if (!shown) box.innerHTML = "<p class='dim'>Tidak ada episode cocok filter.</p>";
}
function closeTitle() { $("title-modal").classList.add("hidden"); }
async function openPlayer(ep) {
  cur.ep = ep;
  closeTitle();
  $("player-modal").classList.remove("hidden");
  $("pm-title").textContent = cur.title;
  $("pm-meta").textContent = "ep " + ep + " · " + cur.mode.toUpperCase();
  $("pm-spinner").classList.remove("hidden");
  $("pm-status").textContent = "resolving ep " + ep + "...";
  updatePrevNext();
  var t0 = Date.now();
  var r = await window.Tatap.resolve(cur.slug, ep, cur.mode, cur.quality);
  if (!r.success) { $("pm-status").textContent = "ERROR: " + r.error; return; }
  cur.res = r.data;
  var picked = r.data.picked || r.data.variants[0];
  $("pm-meta").textContent = "ep " + ep + " · " + cur.mode.toUpperCase() + " · " + picked.q + " · " + (r.data.server || "") + (r.data.cached ? " · cached" : " · " + (Date.now() - t0) + "ms");
  renderVariants();
  playUrl(picked.url, r.data.referer, r.data.sub, r.data.referer);
  window.Tatap.saveHist({slug: cur.slug, title: cur.title, episode: ep, mode: cur.mode}).then(function () { renderContinue(); });
}
function renderVariants() {
  var box = $("pm-variants"); box.innerHTML = "";
  var vs = (cur.res && cur.res.variants) || [];
  for (var i = 0; i < vs.length; i++) {
    (function (v) {
      var b = document.createElement("button");
      b.textContent = v.q;
      if (cur.res.picked && cur.res.picked.q === v.q) b.className = "active";
      else if (!cur.res.picked && i === 0) b.className = "active";
      b.addEventListener("click", function () { switchQ(v.q); });
      box.appendChild(b);
    })(vs[i]);
  }
}
function armAutohide() {
  var stage = document.querySelector(".ambient-stage");
  var shell = document.querySelector(".player-shell");
  if (!stage || stage._armed) return;
  stage._armed = true;
  var v = $("vid");
  var t = null;
  var show = function () {
    stage.classList.remove("idle");
    if (shell) shell.classList.remove("idle");
    if (v.hasAttribute("controls")) { /* keep native */ }
    clearTimeout(t);
    t = setTimeout(function () {
      if (v.paused) return;
      v.removeAttribute("controls");
      stage.classList.add("idle");
      if (shell) shell.classList.add("idle");
    }, 2800);
  };
  var wake = function () {
    if (!v.hasAttribute("controls")) v.setAttribute("controls", "");
    show();
  };
  ["mousemove", "touchstart", "click"].forEach(function (ev) {
    stage.addEventListener(ev, wake, { passive: true });
  });
  v.addEventListener("play", show);
  v.addEventListener("pause", function () {
    clearTimeout(t);
    v.setAttribute("controls", "");
    stage.classList.remove("idle");
    if (shell) shell.classList.remove("idle");
  });
  v.addEventListener("seeking", show);
  show();
}
function playUrl(url, referer, sub, subRef) {
  var v = $("vid");
  var prox = "/api/player/video?url=" + encodeURIComponent(url) + "&referer=" + encodeURIComponent(referer || "");
  var old = v.querySelector("track");
  if (old) old.remove();
  if (sub) {
    var t = document.createElement("track");
    t.kind = "subtitles"; t.label = "English"; t.srclang = "en";
    try { t["default"] = true; } catch (e) { t.setAttribute("default", ""); }
    t.src = "/api/player/sub?url=" + encodeURIComponent(sub) + "&referer=" + encodeURIComponent(subRef || "");
    v.appendChild(t);
  }
  $("pm-spinner").classList.remove("hidden");
  $("pm-status").textContent = "buffering...";
  var onCan = function () { $("pm-spinner").classList.add("hidden"); };
  v.addEventListener("canplay", onCan, {once: true});
  setTimeout(function () { $("pm-spinner").classList.add("hidden"); }, 15000);
  if (window.Hls && window.Hls.isSupported() && url.indexOf(".m3u8") >= 0) {
    if (window._hls) { try { window._hls.destroy(); } catch (e) {} }
    var h = new Hls({maxBufferLength: 60});
    window._hls = h;
    h.loadSource(prox);
    h.attachMedia(v);
    h.on(Hls.Events.ERROR, function (ev, d) { if (d && d.fatal) { $("pm-status").textContent = "player error: " + (d.type || "fatal"); } });
  } else {
    v.src = url.indexOf(".m3u8") >= 0 ? prox : url;
  }
  v.play().catch(function () { $("pm-spinner").classList.add("hidden"); });
  armAutohide();
}
function switchQ(q) {
  if (!cur.res) return;
  for (var i = 0; i < cur.res.variants.length; i++)
    if (cur.res.variants[i].q === q) {
      cur.res.picked = cur.res.variants[i];
      renderVariants();
      playUrl(cur.res.variants[i].url, cur.res.referer, cur.res.sub, cur.res.referer);
      toast("Quality: " + q);
      return;
    }
}
function updatePrevNext() {
  var idx = -1;
  for (var i = 0; i < cur.eps.length; i++) if (cur.eps[i].ep === cur.ep) idx = i;
  $("pm-prev").disabled = idx <= 0;
  $("pm-next").disabled = idx < 0 || idx >= cur.eps.length - 1;
}
function stepEp(d) {
  if ($("player-modal").classList.contains("hidden")) return;
  var idx = -1;
  for (var i = 0; i < cur.eps.length; i++) if (cur.eps[i].ep === cur.ep) idx = i;
  var nxt = cur.eps[idx + d];
  if (nxt) openPlayer(nxt.ep);
  else toast(d > 0 ? "Sudah episode terakhir" : "Sudah episode pertama");
}
function closePlayer() {
  var v = $("vid");
  try { v.pause(); } catch (e) {}
  if (window._hls) { try { window._hls.destroy(); window._hls = null; } catch (e) {} }
  v.removeAttribute("src");
  try { v.load(); } catch (e) {}
  $("player-modal").classList.add("hidden");
  $("pm-spinner").classList.add("hidden");
}
async function playMPV() {
  var r = await window.Tatap.playMPV({slug: cur.slug, title: cur.title, ep: cur.ep || 1, mode: cur.mode, quality: cur.quality});
  toast(r.success ? ("MPV: " + r.data.picked.q) : ("ERROR: " + r.error));
}
async function renderContinue() {
  try {
    var r = await window.Tatap.history();
    var h = (r.data || []).slice(0, 10);
    var sec = $("continue-sec");
    if (!h.length) { sec.classList.add("hidden"); return; }
    sec.classList.remove("hidden");
    var box = $("continue-row"); box.innerHTML = "";
    for (var i = 0; i < h.length; i++) {
      (function (x) {
        var d = document.createElement("div");
        d.className = "hist-card";
        var b = document.createElement("b"); b.textContent = x.title; d.appendChild(b);
        var s = document.createElement("span"); s.textContent = "ep " + x.episode + " · " + x.mode + " · lanjutkan ▶"; d.appendChild(s);
        d.addEventListener("click", async function () {
          cur.slug = x.slug; cur.title = x.title; cur.mode = x.mode || "sub";
          syncSeg();
          await openTitle(x.slug, x.title);
          openPlayer(x.episode);
        });
        box.appendChild(d);
      })(h[i]);
    }
  } catch (e) {}
}
function syncSeg() {
  document.querySelectorAll("#mode-seg button").forEach(function (x) { x.classList.toggle("active", x.getAttribute("data-mode") === cur.mode); });
}
function doSearch() { return window.__doSearch ? window.__doSearch() : null; }
window.__doSearch = null;
(function () {
  var realSearch = doSearch;
})();
window.doSearch = function () { var q = $("q").value; if (q && q.trim()) { pushRecentSilent(q.trim()); } return _searchNow(); };
function pushRecentSilent(q) { pushRecent(q); }
async function _searchNow() {
  var q = $("q").value.trim();
  if (!q) return;
  $("empty-state").style.display = "none";
  $("results-title").textContent = "Mencari...";
  var t0 = Date.now();
  var r = await window.Tatap.search(q);
  if (!r.success) { $("results-title").textContent = "Error: " + r.error; return; }
  lastResults = r.data.results || [];
  focusIdx = -1;
  $("results-title").textContent = lastResults.length ? ("Hasil untuk \"" + q + "\"") : ("Tidak ketemu");
  $("results-meta").textContent = lastResults.length ? (lastResults.length + " judul · " + (Date.now() - t0) + "ms") : "";
  renderCards();
}
function setFallback(r, g, b) {
  var fb = $("ambient-fallback");
  if (!fb) return;
  fb.style.background = "radial-gradient(60% 90% at 50% 50%, rgb(" + r + "," + g + "," + b + "), transparent 70%)";
}
function startAmbient() {
  var cv = $("ambient"), ctx = null;
  try { ctx = cv.getContext("2d", { willReadFrequently: true }); } catch (e) { ctx = cv.getContext("2d"); }
  var v = $("vid");
  v.setAttribute("crossorigin", "anonymous");
  var tmp = document.createElement("canvas");
  tmp.width = 48; tmp.height = 27;
  var tctx = null;
  try { tctx = tmp.getContext("2d", { willReadFrequently: true }); } catch (e) { tctx = tmp.getContext("2d"); }
  var lastOk = 0;
  setInterval(function () {
    if (document.body.classList.contains("no-ambient")) return;
    if ($("player-modal").classList.contains("hidden")) return;
    if (v.paused || v.ended || v.readyState < 2 || v.videoWidth === 0) return;
    try {
      tctx.drawImage(v, 0, 0, 48, 27);
      var px;
      try {
        px = tctx.getImageData(0, 0, 48, 27).data;
      } catch (taint) {
        // video tainted (CORS) -> fallback: glow statis dari hash episode
        var h = 0, s = String(cur.slug) + cur.ep;
        for (var k = 0; k < s.length; k++) h = (h * 31 + s.charCodeAt(k)) % 360;
        setFallback(Math.round(90 + 80 * Math.abs(Math.sin(h))), 120, 220);
        return;
      }
      var r = 0, g = 0, b = 0, n = 0;
      for (var i = 0; i < px.length; i += 12) { r += px[i]; g += px[i+1]; b += px[i+2]; n++; }
      r = Math.round(r/n); g = Math.round(g/n); b = Math.round(b/n);
      lastOk = Date.now();
      // canvas utama
      var g2 = ctx.createLinearGradient(0, 0, 96, 54);
      g2.addColorStop(0, "rgb(" + r + "," + g + "," + b + ")");
      g2.addColorStop(1, "rgb(" + Math.round(b*.7) + "," + Math.round(r*.6) + "," + Math.round(g*.8) + ")");
      ctx.fillStyle = g2;
      ctx.fillRect(0, 0, 96, 54);
      setFallback(r, g, b);
    } catch (e) {}
  }, 500);
}
window.doSearch = _searchNow;
window.openAnime = openTitle;
window.playEp = openPlayer;
window.playMPV = playMPV;
window.showHistory = renderContinue;
window.backToResults = goHome;
window.switchQ = switchQ;
init();
