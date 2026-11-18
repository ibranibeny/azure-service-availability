// Architecture tab: hop-by-hop traffic animation over the inline architecture SVG.
// Packets travel along the connector paths; each step is narrated and names its Microsoft Learn source.
// Motion is opt-in: it plays by itself only when animations are switched on in the header, or after the
// visitor pressed Play here once. Play and Pause are remembered in localStorage.
import { FLOWS, TOUR, SEGS, TIMING } from "./arch-flows.js";

const NS = "http://www.w3.org/2000/svg";
const KEY = "asa.archPlay", SPEED_KEY = "asa.archSpeed";

export function initArch(root, { motionOn }) {
  const svg = root && root.querySelector("#archSvg");
  if (!svg) return null;
  const q = (s) => root.querySelector(s);
  const pkLayer = svg.querySelector("#arch-pkts"), badgeLayer = svg.querySelector("#arch-badges");
  const byId = new Map(FLOWS.map((f) => [f.id, f]));
  const segG = new Map([...svg.querySelectorAll("[data-seg]")].map((g) => [g.dataset.seg, g]));
  const nodeG = new Map([...svg.querySelectorAll("[data-node]")].map((g) => [g.dataset.node, g]));
  const paths = new Map(), lens = new Map();
  const pathOf = (id) => paths.get(id) || paths.set(id, svg.querySelector("#arch-seg-" + id)).get(id);
  const lenOf = (id) => lens.get(id) ?? lens.set(id, pathOf(id).getTotalLength()).get(id);
  const stored = () => localStorage.getItem(KEY);
  const S = {
    mode: "tour", flow: TOUR[0], step: -1, plan: null, v: 0, last: 0, raf: 0, live: false, visible: false,
    want: stored() === "1" || (stored() !== "0" && motionOn()),
    speed: Number(localStorage.getItem(SPEED_KEY)) || 1, pk: new Map(),
  };
  const flow = () => byId.get(S.flow);
  const running = () => S.want && S.visible && !document.hidden;

  // ---------- drawing ----------
  function setFlowColor() { root.style.setProperty("--flow", flow().color); }

  function paint() {
    const f = flow(), st = f.steps[S.step];
    svg.classList.toggle("arch-live", S.live);
    const inSegs = new Set(), inNodes = new Set();
    for (const s of f.steps) {
      for (const [seg] of s.hops) { inSegs.add(seg); SEGS[seg].forEach((n) => inNodes.add(n)); }
      s.focus.forEach((n) => inNodes.add(n));
    }
    const onSegs = new Set(st ? st.hops.map((h) => h[0]) : []);
    const hot = new Set(st ? st.focus : []);
    onSegs.forEach((seg) => SEGS[seg].forEach((n) => hot.add(n)));
    segG.forEach((g, id) => { g.classList.toggle("in", S.live && inSegs.has(id)); g.classList.toggle("on", S.live && onSegs.has(id)); });
    nodeG.forEach((g, id) => { g.classList.toggle("in", S.live && inNodes.has(id)); g.classList.toggle("hot", S.live && hot.has(id)); });
    const timer = svg.querySelector("#arch-timer");
    if (timer) timer.classList.toggle("ring", S.live && S.flow === "collect" && S.step === 0);
    badges();
    caption();
  }

  function badges() {
    badgeLayer.replaceChildren();
    if (!S.live) return;
    flow().steps.forEach((s, i) => {
      const g = document.createElementNS(NS, "g");
      g.setAttribute("class", "az-badge arch-b" + (i === S.step ? " cur" : ""));
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", s.badge[0]); c.setAttribute("cy", s.badge[1]); c.setAttribute("r", i === S.step ? 11 : 9);
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", s.badge[0]); t.setAttribute("y", s.badge[1] + 3.8); t.textContent = String(i + 1);
      const tip = document.createElementNS(NS, "title");
      tip.textContent = `${i + 1}. ${s.title}`;
      g.append(tip, c, t);
      g.addEventListener("click", () => jump(i));
      badgeLayer.append(g);
    });
  }

  function caption() {
    const f = flow(), st = f.steps[Math.min(S.step, f.steps.length - 1)];
    const live = S.live && st;
    q("#archFlowName").textContent = live ? f.name : "Four flows";
    q("#archFlowTag").textContent = live ? f.tagline : "scheduled collection · guest read · signed-in read · deploy & publish";
    q("#archStepNo").textContent = live ? `Step ${Math.min(S.step, f.steps.length - 1) + 1} of ${f.steps.length}` : "";
    q("#archStepTitle").textContent = live ? st.title + "." : "";
    q("#archStepText").textContent = live ? st.text
      : "Press play to watch the packets, or step through with the arrows. Pick a flow above to follow just that one.";
    const a = q("#archStepSrc");
    a.hidden = !(live && st.src);
    if (live && st.src) { a.href = st.src[1]; a.textContent = st.src[0] + " ↗"; }
    q("#archChips").replaceChildren(...(S.live ? f.steps.map((s, i) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = String(i + 1); b.title = s.title;
      if (i === S.step) { b.className = "cur"; b.setAttribute("aria-current", "step"); }
      b.addEventListener("click", () => jump(i));
      return b;
    }) : []));
    root.querySelectorAll("[data-flow]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.flow === (S.mode === "tour" ? "tour" : S.flow))));
    q("#archPlay").textContent = S.want ? "⏸ Pause" : "▶ Play traffic";
    q("#archCaption").setAttribute("aria-live", S.want ? "off" : "polite");
    root.classList.toggle("arch-anim", S.want);
  }

  // ---------- packets ----------
  function packet(key, tag) {
    let g = S.pk.get(key);
    if (g) return g;
    g = document.createElementNS(NS, "g");
    g.setAttribute("class", "pkt");
    const halo = document.createElementNS(NS, "circle"); halo.setAttribute("class", "halo"); halo.setAttribute("r", 14);
    const dot = document.createElementNS(NS, "circle"); dot.setAttribute("class", "dot"); dot.setAttribute("r", 7);
    g.append(halo, dot);
    pkLayer.append(g);
    if (tag) {
      const tg = document.createElementNS(NS, "g"); tg.setAttribute("class", "tag");
      const r = document.createElementNS(NS, "rect"); r.setAttribute("height", 21); r.setAttribute("rx", 10.5);
      const t = document.createElementNS(NS, "text"); t.setAttribute("x", 8); t.setAttribute("y", 14.8); t.textContent = tag;
      tg.append(r, t); g.append(tg);
      const w = t.getComputedTextLength() + 16;
      r.setAttribute("width", w.toFixed(1));
      g.dataset.w = w.toFixed(1);
    }
    S.pk.set(key, g);
    return g;
  }
  function dropPackets() { S.pk.forEach((g) => g.remove()); S.pk.clear(); }

  function planOf(step) {
    if (!step) return { items: [], end: TIMING.flowGap };
    let t = 0;
    const items = step.hops.map(([seg, dir, tag, burst], idx) => {
      const it = { idx, seg, dir, tag, burst: burst || 1, start: t, dur: Math.max(TIMING.minHop, lenOf(seg) / TIMING.pxPerS) };
      t += it.dur + (it.burst - 1) * TIMING.burstGap;
      return it;
    });
    return { items, end: t + (items.length ? TIMING.dwell : TIMING.emptyDwell) };
  }

  function draw() {
    for (const it of S.plan.items) {
      for (let k = 0; k < it.burst; k++) {
        const key = it.idx + ":" + k, u = (S.v - it.start - k * TIMING.burstGap) / it.dur;
        if (u <= 0 || u >= 1) { const old = S.pk.get(key); if (old) { old.remove(); S.pk.delete(key); } continue; }
        const g = packet(key, k === 0 ? it.tag : "");
        const p = pathOf(it.seg).getPointAtLength((it.dir > 0 ? u : 1 - u) * lenOf(it.seg));
        g.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`);
        g.style.opacity = String(Math.max(0, Math.min(1, u / 0.1, (1 - u) / 0.1)));
        const tg = g.querySelector(".tag");
        if (tg) tg.setAttribute("transform", p.x > 1300 ? `translate(${-12 - Number(g.dataset.w)} -33)` : "translate(12 -33)");
      }
    }
  }

  function frame(now) {
    S.raf = 0;
    if (!running()) return;
    if (S.step < 0) { setFlowColor(); go(0); }
    const dt = S.last ? Math.min(0.1, (now - S.last) / 1000) : 0;
    S.last = now;
    if (!S.plan) S.plan = planOf(flow().steps[S.step]);
    S.v += dt * S.speed;
    draw();
    if (S.v >= S.plan.end) advance();
    S.raf = requestAnimationFrame(frame);
  }

  function kick() {
    if (running() && !S.raf) { S.last = 0; S.raf = requestAnimationFrame(frame); }
  }

  // ---------- navigation ----------
  function go(i) {
    dropPackets();
    S.step = i; S.v = 0; S.plan = null; S.live = true;
    q("#archOverlay").hidden = true;
    paint();
  }
  function nextFlow(d) {
    S.flow = TOUR[(TOUR.indexOf(S.flow) + d + TOUR.length) % TOUR.length];
    setFlowColor();
  }
  function advance() {
    const n = flow().steps.length;
    if (S.step < n - 1) return go(S.step + 1);
    if (S.step === n - 1) { dropPackets(); S.step = n; S.v = 0; S.plan = planOf(null); return; }   // short pause at the end
    if (S.mode === "tour") nextFlow(1);
    go(0);
  }
  function jump(i) { setFlowColor(); go(i); kick(); }
  function stepBy(d) {
    if (S.step < 0) { setFlowColor(); go(0); return; }
    let i = Math.min(S.step, flow().steps.length - 1) + d;
    if (i >= flow().steps.length) { if (S.mode === "tour") nextFlow(1); i = 0; }
    else if (i < 0) { if (S.mode === "tour") nextFlow(-1); i = flow().steps.length - 1; }
    go(i);
  }
  function selectFlow(id) {
    S.mode = id === "tour" ? "tour" : "one";
    S.flow = id === "tour" ? TOUR[0] : id;
    setFlowColor(); go(0); kick();
  }
  function setWant(on, remember = true) {
    S.want = on;
    if (remember) localStorage.setItem(KEY, on ? "1" : "0");
    if (on && S.step < 0) { setFlowColor(); go(0); }
    q("#archOverlay").hidden = on || S.live;
    caption();
    kick();
  }

  // ---------- full step list (readable without motion) ----------
  const all = q("#archAll");
  for (const f of FLOWS) {
    const h = document.createElement("h4");
    const dot = document.createElement("span"); dot.className = "dot"; dot.style.background = f.color;
    h.append(dot, document.createTextNode(`${f.name} — ${f.tagline}`));
    const ol = document.createElement("ol");
    f.steps.forEach((s) => {
      const li = document.createElement("li");
      const b = document.createElement("b"); b.textContent = s.title + ". ";
      li.append(b, document.createTextNode(s.text + " "));
      if (s.src) { const a = document.createElement("a"); a.href = s.src[1]; a.target = "_blank"; a.rel = "noopener"; a.textContent = s.src[0] + " ↗"; li.append(a); }
      ol.append(li);
    });
    all.append(h, ol);
  }

  // ---------- wiring ----------
  root.querySelectorAll("[data-flow]").forEach((b) => b.addEventListener("click", () => selectFlow(b.dataset.flow)));
  q("#archPlay").addEventListener("click", () => setWant(!S.want));
  q("#archOverlay").addEventListener("click", () => setWant(true));
  q("#archPrev").addEventListener("click", () => stepBy(-1));
  q("#archNext").addEventListener("click", () => stepBy(1));
  const full = () => (document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen?.())?.catch?.(() => {});
  const fb = q("#archFull");
  if (fb && root.requestFullscreen) fb.addEventListener("click", full); else if (fb) fb.hidden = true;
  const sp = q("#archSpeed");
  sp.value = String(S.speed);
  sp.addEventListener("change", () => { S.speed = Number(sp.value) || 1; localStorage.setItem(SPEED_KEY, sp.value); });
  root.addEventListener("keydown", (e) => {
    if (e.target.closest("select, input")) return;
    if (e.key === "ArrowRight") { stepBy(1); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { stepBy(-1); e.preventDefault(); }
    else if (e.key === " " && !e.target.closest("button, a, summary")) { setWant(!S.want); e.preventDefault(); }
    else if ((e.key === "f" || e.key === "F") && root.requestFullscreen) { full(); e.preventDefault(); }
  });
  new IntersectionObserver((es) => { S.visible = es.some((e) => e.isIntersecting); kick(); }, { threshold: 0.1 }).observe(svg);
  document.addEventListener("visibilitychange", kick);
  q("#archOverlay").hidden = S.want;
  caption();

  return {
    // header "Animations" toggle: follow it unless the visitor chose Play or Pause here
    syncMotion() { if (stored() === null) setWant(motionOn(), false); },
  };
}
