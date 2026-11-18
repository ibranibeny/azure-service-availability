// Deployment guide: theme and animation preferences, "your values" form, copy buttons,
// contents highlight and the storage-account traffic animation.
import { initArch } from "./arch.js";
import * as STORAGE from "./storage-flows.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

// ---------- preferences (same keys as the dashboard) ----------
const prefersReduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const motionOn = () => (localStorage.getItem("asa.motion") ?? (prefersReduced ? "off" : "on")) === "on";
let arch = null;
function applyPrefs() {
  const theme = localStorage.getItem("asa.theme") || "auto";
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.motion = motionOn() ? "on" : "off";
  $("#themeBtn").textContent = { auto: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[theme] || "Theme: auto";
  $("#motionBtn").textContent = motionOn() ? "Animations: on" : "Animations: off";
}
$("#themeBtn").addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const cur = localStorage.getItem("asa.theme") || "auto";
  localStorage.setItem("asa.theme", order[(order.indexOf(cur) + 1) % 3]);
  applyPrefs();
});
$("#motionBtn").addEventListener("click", () => {
  localStorage.setItem("asa.motion", motionOn() ? "off" : "on");
  applyPrefs();
  arch?.syncMotion();
});
applyPrefs();

// ---------- your values: rewrite the commands on the page ----------
const VALUES_KEY = "asa.guideValues";
const DEFAULTS = { owner: "ibranibeny", repo: "azure-service-availability", domain: "contoso.day", location: "indonesiacentral", rg: "rg-azure-service-availability" };
const CLEAN = {
  owner: (v) => v.replace(/[^A-Za-z0-9-]/g, "").slice(0, 39),
  repo: (v) => v.replace(/[^A-Za-z0-9._-]/g, "").slice(0, 100),
  domain: (v) => v.replace(/[^A-Za-z0-9.,-]/g, "").toLowerCase().slice(0, 200),
  location: (v) => v.replace(/[^A-Za-z0-9]/g, "").toLowerCase().slice(0, 40),
  rg: (v) => v.replace(/[^\w.()-]/g, "").slice(0, 90),
};
const form = $("#valuesForm");
function readStored() {
  try { return JSON.parse(localStorage.getItem(VALUES_KEY) || "{}") || {}; } catch { return {}; }
}
function current() {
  const out = {};
  for (const k of Object.keys(DEFAULTS)) out[k] = CLEAN[k](form.elements[k].value.trim()) || DEFAULTS[k];
  return out;
}
function render() {
  const v = current();
  const host = `${v.owner.toLowerCase()}.github.io`;
  const derived = {
    ...v,
    pages: v.repo.toLowerCase() === host ? `https://${host}/` : `https://${host}/${v.repo}/`,
    clone: `https://github.com/${v.owner}/${v.repo}.git`,
  };
  $$("var.v[data-v]").forEach((el) => { el.textContent = derived[el.dataset.v] ?? el.textContent; });
}
if (form) {
  const saved = readStored();
  for (const k of Object.keys(DEFAULTS)) {
    const input = form.elements[k];
    input.placeholder = DEFAULTS[k];
    input.value = typeof saved[k] === "string" ? CLEAN[k](saved[k]) : "";
  }
  form.addEventListener("input", () => {
    const keep = {};
    for (const k of Object.keys(DEFAULTS)) { const c = CLEAN[k](form.elements[k].value.trim()); if (c) keep[k] = c; }
    localStorage.setItem(VALUES_KEY, JSON.stringify(keep));
    render();
  });
  form.addEventListener("change", (e) => { const k = e.target.name; if (CLEAN[k]) e.target.value = CLEAN[k](e.target.value.trim()); });
  form.addEventListener("submit", (e) => e.preventDefault());
  $("#valuesReset").addEventListener("click", () => {
    localStorage.removeItem(VALUES_KEY);
    for (const k of Object.keys(DEFAULTS)) form.elements[k].value = "";
    render();
  });
  render();
}

// ---------- copy buttons on command blocks ----------
for (const pre of $$("pre.code:not(.out)")) {
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "copy"; btn.textContent = "Copy";
  btn.setAttribute("aria-label", "Copy these commands");
  btn.addEventListener("click", async () => {
    const text = pre.querySelector("code").innerText.replace(/\s+$/, "") + "\n";
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied";
    } catch {
      const r = document.createRange(); r.selectNodeContents(pre.querySelector("code"));
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
      btn.textContent = "Press Ctrl+C";
    }
    setTimeout(() => { btn.textContent = "Copy"; }, 1800);
  });
  pre.append(btn);
}

// ---------- highlight the current section in the contents ----------
const links = new Map($$(".toc a[href^='#']").map((a) => [a.getAttribute("href").slice(1), a]));
const seen = new Map();
const spy = new IntersectionObserver((entries) => {
  for (const e of entries) seen.set(e.target.id, e.isIntersecting);
  const firstVisible = [...links.keys()].find((id) => seen.get(id));
  if (!firstVisible) return;
  links.forEach((a, id) => (id === firstVisible ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current")));
}, { rootMargin: "-80px 0px -55% 0px" });
links.forEach((_, id) => { const sec = document.getElementById(id); if (sec) spy.observe(sec); });

// ---------- storage-account traffic animation ----------
try { arch = initArch($("#arch"), { motionOn, data: STORAGE }); } catch (e) { console.error("Storage animation:", e); }
