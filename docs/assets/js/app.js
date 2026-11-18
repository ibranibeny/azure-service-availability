// Azure Service Availability dashboard
import { configured, handleRedirect, account, signIn, signOut, AuthError } from "./auth.js";
import { get, ApiError, guestAllowed, isGuest, setGuest } from "./api.js";
import { WorldMap } from "./map.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "ico") => `<img class="${cls}" src="assets/icons/${esc(name)}.svg" alt="" loading="lazy">`;
const fmtNum = (n) => (n ?? 0).toLocaleString("en-US");

const state = {
  summary: null, regions: new Map(), services: [], svc: new Map(),
  lens: "vm", selected: null, tab: "map",
  vmFilter: { q: "", family: "", minCpu: "", minMem: "", restricted: false, zonal: false, gpu: false, arm: false, sort: "family", dir: 1, all: false },
  vmIndex: null, amr: null, finderSku: null, amrSku: null,
};
let mainMap, finderMap, amrMap;

// ---------- preferences: theme + motion (explicit opt-in remembered in localStorage) ----------
const prefersReduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const motionOn = () => (localStorage.getItem("asa.motion") ?? (prefersReduced ? "off" : "on")) === "on";
function applyPrefs() {
  const theme = localStorage.getItem("asa.theme") || "auto";
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.motion = motionOn() ? "on" : "off";
  $("#themeBtn").textContent = { auto: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[theme];
  $("#motionBtn").textContent = motionOn() ? "Animations: on" : "Animations: off";
}
function wirePrefs() {
  $("#themeBtn").addEventListener("click", () => {
    const order = ["auto", "light", "dark"];
    const cur = localStorage.getItem("asa.theme") || "auto";
    localStorage.setItem("asa.theme", order[(order.indexOf(cur) + 1) % 3]);
    applyPrefs();
  });
  $("#motionBtn").addEventListener("click", () => { localStorage.setItem("asa.motion", motionOn() ? "off" : "on"); applyPrefs(); });
}

// ---------- time helpers ----------
function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
}
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return m + " min ago";
  const h = Math.floor(m / 60);
  return h < 48 ? h + " h " + (m % 60) + " min ago" : Math.round(h / 24) + " days ago";
}
function until(date) {
  const m = Math.max(0, Math.round((date - Date.now()) / 60000));
  return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + (m % 60) + " min";
}
// Next occurrence of a 6-field NCRONTAB expression (sec min hour day month weekday), evaluated in UTC.
function nextRun(expr, from = new Date()) {
  const f = (expr || "").trim().split(/\s+/);
  if (f.length !== 6) return null;
  const parse = (s, lo, hi) => {
    const set = new Set();
    for (const part of s.split(",")) {
      let [range, step] = part.split("/"); step = Number(step || 1);
      let [a, b] = range === "*" ? [lo, hi] : range.split("-").map(Number);
      if (b === undefined) b = range.includes("-") ? hi : (part.includes("/") ? hi : a);
      for (let v = a; v <= b; v += step) set.add(v);
    }
    return set;
  };
  try {
    const [S, M, H, D, Mo, Wd] = [parse(f[0], 0, 59), parse(f[1], 0, 59), parse(f[2], 0, 23), parse(f[3], 1, 31), parse(f[4], 1, 12), parse(f[5], 0, 6)];
    const t = new Date(Math.ceil((from.getTime() + 1000) / 60000) * 60000);
    for (let i = 0; i < 60 * 24 * 40; i++) {
      if (Mo.has(t.getUTCMonth() + 1) && D.has(t.getUTCDate()) && Wd.has(t.getUTCDay()) && H.has(t.getUTCHours()) && M.has(t.getUTCMinutes()) && S.has(0)) return t;
      t.setTime(t.getTime() + 60000);
    }
  } catch { /* unsupported expression */ }
  return null;
}
function describeSchedule(expr) {
  const f = (expr || "").split(/\s+/);
  if (f.length === 6 && f[0] === "0" && f[1] === "0" && /^\*\/\d+$/.test(f[2]) && f.slice(3).every((x) => x === "*")) {
    return `every ${f[2].slice(2)} hours (UTC)`;
  }
  return expr ? `NCRONTAB ${expr} (UTC)` : "schedule not reported";
}

// ---------- UI helpers ----------
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 4200);
}
function tooltip(html, ev) {
  const t = $("#tooltip");
  if (!html) { t.hidden = true; return; }
  t.innerHTML = html; t.hidden = false;
  const r = ev?.target?.getBoundingClientRect?.();
  const x = ev?.clientX ?? (r ? r.left + r.width / 2 : 0), y = ev?.clientY ?? (r ? r.top : 0);
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = Math.min(innerWidth - w - 8, Math.max(8, x + 14)) + "px";
  t.style.top = Math.min(innerHeight - h - 8, Math.max(8, y + 14)) + "px";
}
function setTab(tab, push = true) {
  state.tab = tab;
  $$(".tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $$(".tabpanel").forEach((p) => { p.hidden = p.id !== "tab-" + tab; });
  if (push) writeHash();
  ({ matrix: renderMatrix, vm: openFinder, amr: openAmr, changes: openChanges }[tab] || (() => {}))();
  if (tab === "map" && mainMap) requestAnimationFrame(() => mainMap._apply());
}
function writeHash() {
  const parts = [state.tab];
  if (state.tab === "map" && state.selected) parts.push(state.selected);
  if (state.tab === "vm" && state.finderSku) parts.push(state.finderSku);
  if (state.tab === "amr" && state.amrSku) parts.push(state.amrSku);
  history.replaceState(null, "", "#" + parts.join("/"));
}
function readHash() {
  const [tab, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
  return { tab: ["map", "matrix", "vm", "amr", "changes", "about"].includes(tab) ? tab : "map", arg };
}

// ---------- gate (signed out) ----------
function showGate(kind, err) {
  $("#gate").hidden = false; $("#appView").hidden = true;
  if (!showGate._map) { showGate._map = new WorldMap($("#gateMap"), { minimal: true }); }
  const msg = $("#gateMsg");
  msg.hidden = !kind;
  if (kind === "notConfigured") msg.innerHTML = "This dashboard isn't connected to its API yet. Run <code>scripts/deploy.sh</code> and commit the generated <code>docs/config.js</code>.";
  else if (kind === "authError") msg.innerHTML = `Sign-in didn't complete: <b>${esc(err?.code)}</b> ${esc(err?.message)}`;
  else if (kind === "apiDenied") msg.innerHTML = `${esc(err?.message)} <button class="link" id="gateSignOut">Sign out</button>`;
  else if (kind === "guestOff") msg.innerHTML = "Guest access is turned off at the moment. Sign in with your <b>contoso.day</b> account.";
  $("#signInBtn").disabled = kind === "notConfigured";
  $("#guestBtn").hidden = !guestAllowed() || kind === "notConfigured" || kind === "guestOff";
  $("#guestFine").hidden = $("#guestBtn").hidden;
  $("#gateSignOut")?.addEventListener("click", signOut);
}

// ---------- app ----------
async function loadSummary() {
  $("#loading").hidden = false;
  try {
    const s = await get("/summary");
    state.summary = s;
    state.services = s.services;
    s.services.forEach((x) => state.svc.set(x.id, x));
    s.regions.forEach((r) => state.regions.set(r.name, r));
    renderStatus(); renderKpis(); renderLens(); renderRegionPicker();
    mainMap.setRegions(s.regions); paintMain();
    const h = readHash();
    const first = h.tab === "map" && state.regions.has(h.arg) ? h.arg : state.regions.has("indonesiacentral") ? "indonesiacentral" : s.regions[0]?.name;
    if (h.tab === "vm" && h.arg) state.finderSku = h.arg;
    if (h.tab === "amr" && h.arg) state.amrSku = h.arg;
    selectRegion(first, { zoom: false, push: false });
    setTab(h.tab, false);
  } catch (e) {
    if (isGuest() && e instanceof ApiError && e.status === 401) { setGuest(false); return showGate("guestOff"); }
    if (e instanceof ApiError && (e.status === 401 || e.code === "signed_out")) return showGate("authError", e);
    if (e instanceof ApiError && e.status === 403) return showGate("apiDenied", e);
    $("#appError").hidden = false;
    $("#appError").innerHTML = e.code === "not_collected"
      ? `The first scheduled collection hasn't published data yet. It usually takes a few minutes. <button class="link" id="retryBtn">Try again</button>`
      : `Couldn't load availability data: ${esc(e.message)} <button class="link" id="retryBtn">Try again</button>`;
    $("#retryBtn")?.addEventListener("click", () => { $("#appError").hidden = true; loadSummary(); });
  } finally {
    $("#loading").hidden = true;
  }
}

function renderStatus() {
  const m = state.summary.meta || {};
  const next = nextRun(m.schedule);
  $("#freshness").innerHTML = `<span class="dot-live"></span> Collected ${esc(ago(state.summary.generatedAt))}`;
  $("#freshness").title = `Collected ${fmtTime(state.summary.generatedAt)} in ${m.durationSec ?? "?"} s with ${m.azCalls ?? "?"} az calls (Azure CLI ${m.azCliVersion || ""})`;
  $("#schedule").innerHTML = `${icon("scheduler", "ico sm")} Azure Functions timer · ${esc(describeSchedule(m.schedule))}${next ? " · next in " + esc(until(next)) : ""}`;
  $("#schedule").title = next ? "Next scheduled collection: " + fmtTime(next.toISOString()) : "";
  $("#status").hidden = false;
}

function renderKpis() {
  const k = state.summary.kpis;
  const tiles = [
    ["region-management", fmtNum(k.regions), "Azure regions", `${fmtNum(k.regionsWithZones)} with availability zones`],
    ["virtual-machine", fmtNum(k.vmSkus), "VM sizes offered", `${fmtNum(k.vmAvailablePairs)} size-region pairs open to this subscription`],
    ["azure-managed-redis", fmtNum(k.amrRegions), "Azure Managed Redis regions", `${fmtNum(k.amrZonalRegions)} zone-redundant · ${fmtNum(k.amrPricedRegions)} with prices`],
    ["subscriptions", fmtNum(k.services), "Services tracked", "from az provider list"],
    ["scheduler", ago(state.summary.generatedAt), "Last collection", `${state.summary.meta?.durationSec ?? "?"} s · ${state.summary.meta?.azCalls ?? "?"} az calls`],
  ];
  $("#kpis").innerHTML = tiles.map(([ic, v, l, s]) => `<div class="kpi">${icon(ic)}<div><div class="kpi-v">${esc(v)}</div><div class="kpi-l">${esc(l)}</div><div class="kpi-s">${esc(s)}</div></div></div>`).join("");
}

function renderLens() {
  const groups = {};
  state.services.forEach((s) => (groups[s.category] ||= []).push(s));
  $("#lens").innerHTML = `<optgroup label="Overview"><option value="vm">VM sizes open to this subscription</option><option value="zones">Availability zones</option></optgroup>` +
    Object.entries(groups).map(([g, list]) => `<optgroup label="${esc(g)}">${list.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</optgroup>`).join("");
  $("#lens").value = state.lens;
}

const vmBuckets = () => {
  const vals = state.summary.regions.map((r) => r.vm.available).filter((n) => n > 0).sort((a, b) => a - b);
  const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))] || 0;
  return [q(0.2), q(0.4), q(0.6), q(0.8)];
};
function lensStyle(r) {
  if (state.lens === "vm") {
    const n = r.vm.available;
    if (!n) return { cls: "s0" };
    const b = state._vmb; let q = 1; b.forEach((t) => { if (n > t) q++; });
    return { cls: "q" + q };
  }
  if (state.lens === "zones") return { cls: r.zones ? "s2" : "s1" };
  const s = r.svc[state.lens];
  return { cls: s === 2 ? "s2" : s === 1 ? "s1" : "s0" };
}
function paintMain() {
  state._vmb = vmBuckets();
  mainMap.paint(lensStyle);
  const L = $("#legend");
  if (state.lens === "vm") {
    const b = state._vmb;
    L.innerHTML = `<span class="lg"><i class="sw q1"></i>≤ ${b[0]}</span><span class="lg"><i class="sw q2"></i>≤ ${b[1]}</span><span class="lg"><i class="sw q3"></i>≤ ${b[2]}</span><span class="lg"><i class="sw q4"></i>≤ ${b[3]}</span><span class="lg"><i class="sw q5"></i>more</span><span class="lg"><i class="sw s0"></i>none</span><span class="lg-note">VM sizes available to this subscription</span>`;
  } else if (state.lens === "zones") {
    L.innerHTML = `<span class="lg"><i class="sw s2"></i>Has availability zones</span><span class="lg"><i class="sw s1"></i>No availability zones</span>`;
  } else {
    const s = state.svc.get(state.lens);
    const count = state.summary.regions.filter((r) => r.svc[state.lens]).length;
    L.innerHTML = `${icon(s.icon, "ico sm")}<b>${esc(s.name)}</b> in ${count} regions <span class="lg"><i class="sw s2"></i>Available, zone support listed</span><span class="lg"><i class="sw s1"></i>Available</span><span class="lg"><i class="sw s0"></i>Not offered</span>`;
  }
}

function hoverHtml(r) {
  let line = "";
  if (state.lens === "vm") line = `${fmtNum(r.vm.available)} VM sizes available · ${fmtNum(r.vm.restricted)} restricted`;
  else if (state.lens === "zones") line = r.zones ? `${r.zones} availability zones` : "No availability zones";
  else { const s = r.svc[state.lens]; line = `${esc(state.svc.get(state.lens).name)}: ${s === 2 ? "available, zone support listed" : s === 1 ? "available" : "not offered"}`; }
  return `<b>${esc(r.displayName)}</b><span class="tt-sub">${esc(r.physicalLocation || r.geography || "")} · ${esc(r.name)}</span><span>${line}</span>${r.amr.available ? `<span class="tt-amr">${icon("azure-managed-redis", "ico xs")} Managed Redis${r.amr.zonal ? " · zones" : ""}</span>` : ""}`;
}

function renderRegionPicker() {
  const groups = {};
  state.summary.regions.forEach((r) => (groups[r.geographyGroup || "Other"] ||= []).push(r));
  $("#regionPick").innerHTML = Object.entries(groups).sort().map(([g, list]) => `<optgroup label="${esc(g)}">${list.map((r) => `<option value="${esc(r.name)}">${esc(r.displayName)}</option>`).join("")}</optgroup>`).join("");
  $("#geoZoom").innerHTML = `<option value="">Zoom to…</option><option value="*">Whole world</option>` + Object.keys(groups).sort().map((g) => `<option>${esc(g)}</option>`).join("");
}

function selectRegion(name, { zoom = true, push = true } = {}) {
  if (!state.regions.has(name)) return;
  state.selected = name;
  mainMap.select(name, { zoom });
  $("#regionPick").value = name;
  renderRegionHead(state.regions.get(name));
  loadRegionDoc(name);
  if (push) writeHash();
}

function renderRegionHead(r) {
  const svcTiles = state.services.map((s) => {
    const v = r.svc[s.id];
    const st = v === 2 ? ["ok", "Zones"] : v === 1 ? ["ok1", "Available"] : ["no", "Not offered"];
    return `<li class="svc ${st[0]}" title="${esc(s.name)} — ${esc(s.source)}">${icon(s.icon)}<span class="svc-n">${esc(s.name)}</span><span class="badge ${st[0]}">${st[1]}</span></li>`;
  }).join("");
  const offered = state.services.filter((s) => r.svc[s.id]).length;
  $("#regionHead").innerHTML = `
    <div class="rh-top">
      <div><h2>${esc(r.displayName)}</h2><div class="muted mono">${esc(r.name)}</div></div>
      <div class="chips">
        <span class="chip ${r.zones ? "chip-ok" : ""}">${r.zones ? r.zones + " availability zones" : "No availability zones"}</span>
        <span class="chip">${esc(r.physicalLocation || "—")}</span>
        <span class="chip">${esc(r.geography || "")}</span>
        ${r.category ? `<span class="chip">${esc(r.category)}</span>` : ""}
        ${r.paired?.length ? `<span class="chip">Paired: ${r.paired.map((p) => `<a href="#map/${esc(p)}" data-region="${esc(p)}">${esc(state.regions.get(p)?.displayName || p)}</a>`).join(", ")}</span>` : `<span class="chip">No paired region</span>`}
      </div>
    </div>
    <h3 class="sec">Services in this region <span class="muted">${offered} of ${state.services.length}</span></h3>
    <ul class="svc-grid">${svcTiles}</ul>`;
  $$("#regionHead [data-region]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); selectRegion(a.dataset.region); }));
  $("#regionAmr").innerHTML = `<div class="skeleton"></div>`;
  $("#regionVm").innerHTML = `<div class="skeleton tall"></div>`;
}

async function loadRegionDoc(name) {
  try {
    const doc = await get("/regions/" + encodeURIComponent(name));
    if (state.selected !== name) return;
    state.doc = doc;
    renderRegionAmr(doc);
    renderRegionVm(doc);
  } catch (e) {
    if (state.selected !== name) return;
    $("#regionVm").innerHTML = `<p class="error">Couldn't load this region: ${esc(e.message)}</p>`;
    $("#regionAmr").innerHTML = "";
  }
}

function amrSkuChips(skus, pick) {
  const tiers = {};
  skus.forEach((s) => (tiers[s.tier] ||= []).push(s));
  return Object.entries(tiers).map(([t, list]) => `<div class="tier"><div class="tier-n">${esc(t)}</div><div class="sku-chips">${list.map((s) =>
    `<button class="sku ${s.preview ? "preview" : ""} ${pick === s.sku ? "on" : ""}" data-sku="${esc(s.sku)}" title="${esc(s.tier)} ${esc(s.sku)}${s.usdPerHour != null ? " · $" + s.usdPerHour + "/hour (list price)" : ""}${s.preview ? " · preview" : ""}">${esc(s.sku)}${s.usdPerHour != null ? `<small>$${Number(s.usdPerHour).toFixed(s.usdPerHour < 1 ? 3 : 2)}/h</small>` : ""}</button>`).join("")}</div></div>`).join("");
}

function renderRegionAmr(doc) {
  const a = doc.amr;
  const head = `<h3 class="sec">${icon("azure-managed-redis")} Azure Managed Redis</h3>`;
  if (!a.available) {
    $("#regionAmr").innerHTML = head + `<p class="muted">Not offered in ${esc(doc.displayName)} (resource type <code>Microsoft.Cache/redisEnterprise</code> isn't listed for this region).</p>`;
    return;
  }
  $("#regionAmr").innerHTML = head + `
    <div class="chips"><span class="chip chip-ok">Available</span><span class="chip ${a.zones.length ? "chip-ok" : ""}">${a.zones.length ? "Zone redundancy: zones " + a.zones.join(", ") : "No zone mapping listed"}</span><span class="chip">${a.skus.length} SKUs with a list price</span></div>
    ${a.skus.length ? amrSkuChips(a.skus) : `<p class="muted">No pay-as-you-go meters were returned for this region.</p>`}
    <p class="fine">Preview SKUs are outlined. Prices: Azure Retail Prices API, USD per hour, "Cache Instance" meters. Select a SKU to see every region that offers it.</p>`;
  $$("#regionAmr .sku").forEach((b) => b.addEventListener("click", () => { state.amrSku = b.dataset.sku; setTab("amr"); }));
}

// ---------- VM table ----------
const COLS = [
  ["name", "VM size"], ["family", "Family"], ["vcpus", "vCPU"], ["memoryGB", "Memory GiB"], ["gpus", "GPU"],
  ["arch", "Arch"], ["zones", "Zones"], ["spot", "Spot"], ["premiumIO", "Premium SSD"], ["accelNet", "Accel. net"], ["status", "Status"],
];
function vmRows(doc) {
  const c = doc.vm.columns, idx = Object.fromEntries(c.map((n, i) => [n, i]));
  return doc.vm.rows.map((r) => Object.fromEntries(c.map((n) => [n, r[idx[n]]])));
}
function renderRegionVm(doc) {
  const rows = vmRows(doc);
  state.vmRows = rows;
  const fams = [...new Set(rows.map((r) => r.family))].sort();
  const avail = rows.filter((r) => r.status === "available").length;
  $("#regionVm").innerHTML = `
    <h3 class="sec">${icon("virtual-machine")} Virtual machine sizes <span class="muted">${fmtNum(avail)} available · ${fmtNum(rows.length - avail)} restricted for this subscription${doc.vm.stale ? " · from an earlier run" : ""}</span></h3>
    <div class="filters">
      <input id="vmQ" type="search" placeholder="Filter sizes, e.g. D4s or v6" value="${esc(state.vmFilter.q)}" aria-label="Filter VM sizes">
      <select id="vmFam" aria-label="Family"><option value="">All families</option>${fams.map((f) => `<option ${f === state.vmFilter.family ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
      <input id="vmCpu" type="number" min="0" placeholder="min vCPU" value="${esc(state.vmFilter.minCpu)}" aria-label="Minimum vCPU">
      <input id="vmMem" type="number" min="0" placeholder="min GiB" value="${esc(state.vmFilter.minMem)}" aria-label="Minimum memory">
      <label class="tog"><input type="checkbox" id="vmZonal" ${state.vmFilter.zonal ? "checked" : ""}> Zonal</label>
      <label class="tog"><input type="checkbox" id="vmGpu" ${state.vmFilter.gpu ? "checked" : ""}> GPU</label>
      <label class="tog"><input type="checkbox" id="vmArm" ${state.vmFilter.arm ? "checked" : ""}> Arm64</label>
      <label class="tog"><input type="checkbox" id="vmRes" ${state.vmFilter.restricted ? "checked" : ""}> Show restricted</label>
      <button class="ghost" id="vmCsv">Export CSV</button>
    </div>
    <div class="table-wrap"><table class="grid" id="vmTable"><thead><tr>${COLS.map(([k, l]) => `<th data-k="${k}" class="${state.vmFilter.sort === k ? (state.vmFilter.dir > 0 ? "asc" : "desc") : ""}">${l}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
    <div class="table-foot" id="vmFoot"></div>`;
  const bind = (id, key, prop = "value") => $("#" + id).addEventListener("input", (e) => { state.vmFilter[key] = e.target[prop]; drawVm(); });
  bind("vmQ", "q"); bind("vmFam", "family"); bind("vmCpu", "minCpu"); bind("vmMem", "minMem");
  bind("vmZonal", "zonal", "checked"); bind("vmGpu", "gpu", "checked"); bind("vmArm", "arm", "checked"); bind("vmRes", "restricted", "checked");
  $$("#vmTable th").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.k;
    state.vmFilter.dir = state.vmFilter.sort === k ? -state.vmFilter.dir : 1; state.vmFilter.sort = k;
    $$("#vmTable th").forEach((x) => x.className = x.dataset.k === k ? (state.vmFilter.dir > 0 ? "asc" : "desc") : "");
    drawVm();
  }));
  $("#vmCsv").addEventListener("click", exportCsv);
  drawVm();
}
function filteredVm() {
  const f = state.vmFilter, q = f.q.trim().toLowerCase();
  let rows = state.vmRows.filter((r) =>
    (f.restricted || r.status === "available") && (!q || r.name.toLowerCase().includes(q) || r.family.toLowerCase().includes(q)) &&
    (!f.family || r.family === f.family) && (!f.minCpu || (r.vcpus || 0) >= Number(f.minCpu)) && (!f.minMem || (r.memoryGB || 0) >= Number(f.minMem)) &&
    (!f.zonal || r.zones.length) && (!f.gpu || r.gpus > 0) && (!f.arm || /arm/i.test(r.arch)));
  const k = f.sort, d = f.dir;
  rows.sort((a, b) => {
    const x = k === "zones" ? a.zones.length : a[k], y = k === "zones" ? b.zones.length : b[k];
    return (typeof x === "number" || typeof y === "number" ? ((x ?? -1) - (y ?? -1)) : String(x).localeCompare(String(y))) * d || a.name.localeCompare(b.name);
  });
  return rows;
}
function drawVm() {
  const rows = filteredVm(), limit = state.vmFilter.all ? rows.length : 250;
  const yes = (v) => (v ? `<span class="y">✓</span>` : `<span class="n">—</span>`);
  $("#vmTable tbody").innerHTML = rows.slice(0, limit).map((r) => `<tr class="${r.status !== "available" ? "restricted" : ""}">
    <td class="mono">${esc(r.name)}${r.retirement ? ` <span class="pill warn" title="Retirement date ${esc(r.retirement)}">retires ${esc(r.retirement)}</span>` : ""}${r.lifecycle && !/^ga$|generallyavailable/i.test(r.lifecycle) ? ` <span class="pill">${esc(r.lifecycle)}</span>` : ""}</td>
    <td class="muted">${esc(r.family)}</td><td class="num">${r.vcpus ?? "—"}</td><td class="num">${r.memoryGB ?? "—"}</td><td class="num">${r.gpus || "—"}</td><td>${esc(r.arch)}</td>
    <td class="zones">${[...r.zones.map((z) => `<span class="z">${esc(z)}</span>`), ...r.zonesRestricted.map((z) => `<span class="z off" title="Zone ${esc(z)} restricted for this subscription">${esc(z)}</span>`)].join("") || `<span class="n">regional</span>`}</td>
    <td>${yes(r.spot)}</td><td>${yes(r.premiumIO)}</td><td>${yes(r.accelNet)}</td>
    <td>${r.status === "available" ? `<span class="badge ok">Available</span>` : `<span class="badge warn" title="${esc(r.reason)}">Restricted</span>`}</td></tr>`).join("") ||
    `<tr><td colspan="${COLS.length}" class="muted center">No VM sizes match these filters.</td></tr>`;
  $("#vmFoot").innerHTML = rows.length > limit ? `Showing ${limit} of ${fmtNum(rows.length)} <button class="link" id="vmAll">Show all</button>` : `${fmtNum(rows.length)} sizes`;
  $("#vmAll")?.addEventListener("click", () => { state.vmFilter.all = true; drawVm(); });
}
function exportCsv() {
  const rows = filteredVm();
  const cols = state.doc.vm.columns;
  const csv = [cols.join(",")].concat(rows.map((r) => cols.map((c) => {
    const v = Array.isArray(r[c]) ? r[c].join(" ") : r[c];
    return /[",\n]/.test(String(v ?? "")) ? `"${String(v).replace(/"/g, '""')}"` : (v ?? "");
  }).join(","))).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `vm-sizes-${state.selected}.csv`;
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ---------- service matrix ----------
function renderMatrix() {
  if (!state.summary) return;
  const geo = $("#mxGeo").value, q = $("#mxQ").value.trim().toLowerCase();
  if (!$("#mxGeo").options.length) {
    const gs = [...new Set(state.summary.regions.map((r) => r.geographyGroup || "Other"))].sort();
    $("#mxGeo").innerHTML = `<option value="">All geographies</option>` + gs.map((g) => `<option>${esc(g)}</option>`).join("");
  }
  const regions = state.summary.regions.filter((r) => (!geo || (r.geographyGroup || "Other") === geo) && (!q || r.displayName.toLowerCase().includes(q) || r.name.includes(q)));
  const head = `<tr><th class="sticky">Region</th><th title="Availability zones">AZ</th><th title="VM sizes available to this subscription">VM sizes</th>${state.services.map((s) => `<th class="svc-h" title="${esc(s.name)}">${icon(s.icon)}<span>${esc(s.name)}</span></th>`).join("")}</tr>`;
  const count = `<tr class="count"><td class="sticky muted">Regions offering</td><td></td><td></td>${state.services.map((s) => `<td>${regions.filter((r) => r.svc[s.id]).length}</td>`).join("")}</tr>`;
  const body = regions.map((r) => `<tr><td class="sticky"><a href="#map/${esc(r.name)}" data-region="${esc(r.name)}">${esc(r.displayName)}</a><span class="muted small">${esc(r.geographyGroup || "")}</span></td><td class="num">${r.zones || "—"}</td><td class="num">${fmtNum(r.vm.available)}</td>${state.services.map((s) => {
    const v = r.svc[s.id];
    return `<td class="cell ${v === 2 ? "s2" : v === 1 ? "s1" : "s0"}" title="${esc(s.name)} in ${esc(r.displayName)}: ${v === 2 ? "available, zone support listed" : v === 1 ? "available" : "not offered"}"><i></i></td>`;
  }).join("")}</tr>`).join("");
  $("#matrix").innerHTML = `<thead>${head}</thead><tbody>${count}${body}</tbody>`;
  $$("#matrix [data-region]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); setTab("map"); selectRegion(a.dataset.region); }));
}

// ---------- VM size finder ----------
async function openFinder() {
  if (!state.vmIndex) {
    $("#finderResult").innerHTML = `<div class="skeleton tall"></div>`;
    try { state.vmIndex = await get("/vm-skus"); } catch (e) { $("#finderResult").innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
    $("#skuList").innerHTML = state.vmIndex.skus.map((s) => `<option value="${esc(s.n)}">${esc(s.f)} · ${s.c ?? "?"} vCPU · ${s.m ?? "?"} GiB</option>`).join("");
    if (!finderMap) finderMap = new WorldMap($("#finderMap"), { minimal: false, motion: motionOn, onSelect: (n) => { setTab("map"); selectRegion(n); }, onHover: (n, ev) => tooltip(n ? finderHover(n) : null, ev) });
    finderMap.setRegions(state.summary.regions);
  }
  const sku = state.finderSku || "Standard_D4s_v5";
  $("#skuInput").value = sku;
  showSku(sku);
}
function finderHover(n) {
  const r = state.regions.get(n), st = skuStatus(n);
  return `<b>${esc(r.displayName)}</b><span>${esc(state.finderSku)}: ${st === "z" ? "available, zonal" : st === "a" ? "available (regional)" : st === "r" ? "restricted for this subscription" : "not offered"}</span>`;
}
function skuStatus(region) {
  const e = state.vmIndex.skus.find((s) => s.n === state.finderSku);
  if (!e) return "-";
  const i = state.vmIndex.regions.indexOf(region);
  return e.zn.includes(i) ? "z" : e.ok.includes(i) ? "a" : e.rs.includes(i) ? "r" : "-";
}
function showSku(name) {
  const e = state.vmIndex.skus.find((s) => s.n.toLowerCase() === String(name).trim().toLowerCase());
  if (!e) { $("#finderResult").innerHTML = `<p class="muted">Pick a VM size from the list, e.g. Standard_D4s_v5.</p>`; return; }
  state.finderSku = e.n; writeHash();
  const R = state.vmIndex.regions;
  const groups = { z: [], a: [], r: [], "-": [] };
  state.summary.regions.forEach((r) => groups[skuStatus(r.name)].push(r));
  finderMap.paint((r) => ({ cls: { z: "s2", a: "s1", r: "w1", "-": "s0" }[skuStatus(r.name)] }));
  const list = (arr) => arr.map((r) => `<a class="rchip" href="#map/${esc(r.name)}" data-region="${esc(r.name)}">${esc(r.displayName)}</a>`).join("") || `<span class="muted">none</span>`;
  $("#finderResult").innerHTML = `
    <div class="sku-head"><div><h2 class="mono">${esc(e.n)}</h2><div class="muted">${esc(e.f)} · ${e.c ?? "?"} vCPU · ${e.m ?? "?"} GiB${e.g ? " · " + e.g + " GPU" : ""} · ${esc(e.a)}</div></div>
    <div class="chips"><span class="chip chip-ok">${e.ok.length} regions available</span><span class="chip">${e.zn.length} with zones</span><span class="chip chip-warn">${e.rs.length} restricted</span><span class="chip">${R.length - e.ok.length - e.rs.length} not offered</span></div></div>
    <h4>Available with availability zones</h4><div class="rchips">${list(groups.z)}</div>
    <h4>Available, regional only</h4><div class="rchips">${list(groups.a)}</div>
    <h4>Offered but restricted for this subscription</h4><div class="rchips">${list(groups.r)}</div>
    <p class="fine">"Restricted" means the region lists the size but the Resource SKUs API returns a NotAvailableForSubscription restriction for the collector's subscription — request access through a quota/region access request.</p>`;
  $$("#finderResult [data-region]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); setTab("map"); selectRegion(a.dataset.region); }));
}

// ---------- Azure Managed Redis ----------
async function openAmr() {
  if (!state.amr) {
    $("#amrResult").innerHTML = `<div class="skeleton tall"></div>`;
    try { state.amr = await get("/managed-redis"); } catch (e) { $("#amrResult").innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
    if (!amrMap) amrMap = new WorldMap($("#amrMap"), { motion: motionOn, onSelect: (n) => { setTab("map"); selectRegion(n); }, onHover: (n, ev) => tooltip(n ? amrHover(n) : null, ev) });
    amrMap.setRegions(state.summary.regions);
  }
  const tiers = state.amr.tiers;
  if (!state.amrSku) state.amrSku = tiers.find((t) => t.tier === "Balanced")?.skus.find((s) => s === "B5") || tiers[0]?.skus[0];
  $("#amrPicker").innerHTML = tiers.map((t) => `<div class="tier"><div class="tier-n">${esc(t.tier)}</div><div class="sku-chips">${t.skus.map((s) => `<button class="sku ${t.preview.includes(s) ? "preview" : ""} ${s === state.amrSku ? "on" : ""}" data-sku="${esc(s)}">${esc(s)}</button>`).join("")}</div></div>`).join("");
  $$("#amrPicker .sku").forEach((b) => b.addEventListener("click", () => { state.amrSku = b.dataset.sku; openAmr(); writeHash(); }));
  drawAmr();
}
function amrStatus(n) {
  const a = state.amr.regions[n];
  if (!a || !a.a) return "-";
  if (state.amrSku in (a.s || {})) return a.z.length ? "z" : "a";
  return "u";
}
function amrHover(n) {
  const r = state.regions.get(n), a = state.amr.regions[n] || {}, st = amrStatus(n);
  const price = a.s?.[state.amrSku];
  return `<b>${esc(r.displayName)}</b><span>${esc(state.amrSku)}: ${st === "z" ? "offered, zone redundant" : st === "a" ? "offered" : st === "u" ? "Managed Redis available, no price for this SKU" : "Managed Redis not offered"}${price != null ? " · $" + price + "/h" : ""}</span>`;
}
function drawAmr() {
  amrMap.paint((r) => ({ cls: { z: "s2", a: "s1", u: "w1", "-": "s0" }[amrStatus(r.name)] }));
  const rows = state.summary.regions.map((r) => ({ r, st: amrStatus(r.name), p: state.amr.regions[r.name]?.s?.[state.amrSku] }))
    .filter((x) => x.st !== "-").sort((a, b) => (a.p ?? 1e9) - (b.p ?? 1e9) || a.r.displayName.localeCompare(b.r.displayName));
  const offered = rows.filter((x) => x.st === "z" || x.st === "a").length;
  $("#amrResult").innerHTML = `<h3 class="sec">${icon("azure-managed-redis")} ${esc(state.amrSku)} <span class="muted">offered in ${offered} regions · Managed Redis available in ${rows.length}</span></h3>
    <div class="table-wrap short"><table class="grid"><thead><tr><th>Region</th><th>Geography</th><th>Zones</th><th>List price (USD/hour)</th><th>Status</th></tr></thead><tbody>${rows.map((x) => `<tr>
      <td><a href="#map/${esc(x.r.name)}" data-region="${esc(x.r.name)}">${esc(x.r.displayName)}</a></td><td class="muted">${esc(x.r.geographyGroup || "")}</td>
      <td>${state.amr.regions[x.r.name].z.join(", ") || "—"}</td><td class="num">${x.p != null ? "$" + x.p : "—"}</td>
      <td>${x.st === "z" ? `<span class="badge ok">Zone redundant</span>` : x.st === "a" ? `<span class="badge ok1">Offered</span>` : `<span class="badge warn">No price for SKU</span>`}</td></tr>`).join("")}</tbody></table></div>`;
  $$("#amrResult [data-region]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); setTab("map"); selectRegion(a.dataset.region); }));
}

// ---------- changes + runs ----------
async function openChanges() {
  $("#changes").innerHTML = `<div class="skeleton tall"></div>`;
  try {
    const [c, runs] = await Promise.all([get("/changes", { fresh: true }), get("/runs", { fresh: true })]);
    const m = state.summary.meta || {};
    const next = nextRun(runs.schedule || m.schedule);
    const pairList = (arr) => arr.map(([s, r]) => `<li><span class="mono">${esc(s)}</span> in ${esc(state.regions.get(r)?.displayName || r)}</li>`).join("");
    $("#changes").innerHTML = `
      <div class="cards2">
        <div class="card"><h3 class="sec">${icon("scheduler")} Schedule</h3>
          <p>Azure Functions timer trigger <code>${esc(runs.schedule || m.schedule)}</code> — ${esc(describeSchedule(runs.schedule || m.schedule))}.</p>
          <p>Next collection: <b>${next ? esc(fmtTime(next.toISOString())) : "—"}</b>${next ? ` (in ${esc(until(next))})` : ""}</p>
          <p class="fine">Each run signs in with the collector's managed identity (<code>az login --identity</code>) and calls the Azure CLI; see How it works.</p></div>
        <div class="card"><h3 class="sec">${icon("function-apps")} Changes since the previous run</h3>
          ${c.firstRun ? `<p class="muted">This is the first collection, so there's nothing to compare yet.</p>` : `
          <p>Compared with ${esc(fmtTime(c.since))}: <b>${c.vm.addedCount}</b> VM size–region pairs became available, <b>${c.vm.removedCount}</b> disappeared, ${c.amr.length} Managed Redis changes.</p>
          ${c.vm.addedCount ? `<details><summary>New VM size–region pairs</summary><ul class="small">${pairList(c.vm.added)}</ul></details>` : ""}
          ${c.vm.removedCount ? `<details><summary>Removed VM size–region pairs</summary><ul class="small">${pairList(c.vm.removed)}</ul></details>` : ""}
          ${c.amr.length ? `<details><summary>Managed Redis changes</summary><ul class="small">${c.amr.map((x) => `<li>${esc(state.regions.get(x.region)?.displayName || x.region)}: ${esc(x.change)} ${esc(x.sku || "")}</li>`).join("")}</ul></details>` : ""}`}
        </div>
      </div>
      <h3 class="sec">Collection runs</h3>
      <div class="table-wrap short"><table class="grid"><thead><tr><th>Started</th><th>Trigger</th><th>Result</th><th>Duration</th><th>Regions</th><th>VM rows</th><th>az calls</th><th>Notes</th></tr></thead>
      <tbody>${runs.runs.map((r) => `<tr><td>${esc(fmtTime(r.at))}</td><td>${esc(r.trigger)}</td><td>${r.ok ? `<span class="badge ok">Succeeded</span>` : `<span class="badge bad">Failed</span>`}</td><td class="num">${r.durationSec ?? "—"} s</td><td class="num">${r.regions ?? "—"}</td><td class="num">${fmtNum(r.vmRows)}</td><td class="num">${r.azCalls ?? "—"}</td><td class="small">${r.ok ? (r.errors ? r.errors + " partial errors" : "") : esc(r.error || "")}</td></tr>`).join("")}</tbody></table></div>`;
  } catch (e) {
    $("#changes").innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

// ---------- boot ----------
async function boot() {
  applyPrefs(); wirePrefs();
  $("#signInBtn").addEventListener("click", () => signIn());
  $("#guestBtn").addEventListener("click", () => { setGuest(true); startApp(null); });
  $$(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  if (!configured()) return showGate("notConfigured");
  try {
    await handleRedirect();
  } catch (e) {
    return showGate("authError", e instanceof AuthError ? e : { code: "error", message: e.message });
  }
  const acct = account();
  if (acct) { setGuest(false); return startApp(acct); }
  // Public dashboard: with guest access on, everyone lands straight in the read-only view;
  // contoso.day users can still sign in from the header.
  if (guestAllowed()) {
    if (new URLSearchParams(location.search).has("guest")) history.replaceState(null, "", location.pathname + location.hash);
    setGuest(true);
    return startApp(null);
  }
  return showGate();
}

// acct = signed-in Entra ID account, or null for a read-only guest
async function startApp(acct) {
  if (acct) {
    $("#user").innerHTML = `${icon("users", "ico sm")}<span title="${esc(acct.username)}">${esc(acct.name || acct.username)}</span><button class="ghost" id="signOutBtn">Sign out</button>`;
  } else {
    $("#user").innerHTML = `<span class="badge guest" title="Anyone with the link can view this dashboard; nothing can be changed from here">Guest · read-only</span><button class="ghost" id="guestSignInBtn" title="contoso.day accounts">Sign in</button>`;
  }
  $("#user").hidden = false;
  $("#signOutBtn")?.addEventListener("click", signOut);
  $("#guestSignInBtn")?.addEventListener("click", () => { setGuest(false); signIn(); });
  $("#gate").hidden = true; $("#appView").hidden = false;
  if (startApp._started) return loadSummary();
  startApp._started = true;

  mainMap = new WorldMap($("#map"), {
    motion: motionOn,
    onSelect: (n) => selectRegion(n, { zoom: false }),
    onHover: (n, ev) => tooltip(n ? hoverHtml(state.regions.get(n)) : null, ev),
  });
  $("#lens").addEventListener("change", (e) => { state.lens = e.target.value; paintMain(); });
  $("#regionPick").addEventListener("change", (e) => selectRegion(e.target.value));
  $("#geoZoom").addEventListener("change", (e) => {
    const g = e.target.value; e.target.value = "";
    if (g === "*") return mainMap.reset();
    if (g) mainMap.fitRegions(state.summary.regions.filter((r) => (r.geographyGroup || "Other") === g).map((r) => r.name));
  });
  $("#zoomIn").addEventListener("click", () => mainMap.zoomBy(1.6));
  $("#zoomOut").addEventListener("click", () => mainMap.zoomBy(1 / 1.6));
  $("#zoomReset").addEventListener("click", () => mainMap.reset());
  $("#mxGeo").addEventListener("change", renderMatrix);
  $("#mxQ").addEventListener("input", renderMatrix);
  $("#skuInput").addEventListener("change", (e) => showSku(e.target.value));
  $("#skuInput").addEventListener("keydown", (e) => { if (e.key === "Enter") showSku(e.target.value); });
  setInterval(() => state.summary && renderStatus(), 60000);
  await loadSummary();
}

boot();
