// Interactive world map of Azure regions (SVG, no external libraries).
// Base map: Natural Earth 1:110m (public domain), Natural Earth I projection.
const NS = "http://www.w3.org/2000/svg";
const W = window.ASA_WORLD;

export function project(lon, lat) {
  const lam = (lon * Math.PI) / 180, phi = (lat * Math.PI) / 180;
  const p2 = phi * phi, p4 = p2 * p2;
  const x = lam * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)));
  const y = phi * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)));
  const m = W.meta;
  return [(x + m.xmax) * m.k, (m.ymax - y) * m.k];
}

function line(points) {
  return points.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
}

function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

export class WorldMap {
  constructor(svg, { onSelect, onHover, motion = () => true, minimal = false } = {}) {
    this.svg = svg;
    this.onSelect = onSelect || (() => {});
    this.onHover = onHover || (() => {});
    this.motion = motion;
    this.k = 1; this.tx = 0; this.ty = 0;
    this.regions = []; this.nodes = new Map(); this.selected = null;
    const w = W.meta.w, h = W.meta.h;
    svg.setAttribute("viewBox", `0 0 ${w} ${Math.round(h)}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.vp = el("g", { class: "viewport" }, svg);
    const sphere = [];
    for (let lat = -90; lat <= 90; lat += 3) sphere.push(project(-180, lat));
    for (let lat = 90; lat >= -90; lat -= 3) sphere.push(project(180, lat));
    el("path", { class: "sphere", d: line(sphere) + "Z" }, this.vp);
    let grat = "";
    for (let lon = -180; lon <= 180; lon += 30) {
      const pts = []; for (let lat = -80; lat <= 80; lat += 4) pts.push(project(lon, lat)); grat += line(pts);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const pts = []; for (let lon = -180; lon <= 180; lon += 4) pts.push(project(lon, lat)); grat += line(pts);
    }
    el("path", { class: "graticule", d: grat }, this.vp);
    el("path", { class: "land", d: W.land }, this.vp);
    el("path", { class: "borders", d: W.borders }, this.vp);
    this.gRegions = el("g", { class: "regions" }, this.vp);
    this.gLabels = el("g", { class: "labels" }, this.vp);
    if (!minimal) this._interact();
  }

  setRegions(regions) {
    this.regions = regions;
    this.gRegions.textContent = ""; this.gLabels.textContent = ""; this.nodes.clear();
    // draw south-to-north so northern markers overlap less awkwardly
    [...regions].sort((a, b) => a.lat - b.lat).forEach((r) => {
      const [x, y] = project(r.lon, r.lat);
      const g = el("g", { class: "mk", tabindex: "0", role: "button", "aria-label": r.displayName, "data-name": r.name }, this.gRegions);
      el("circle", { class: "halo", r: 9 }, g);
      el("circle", { class: "dot", r: 5 }, g);
      const label = el("text", { class: "lbl" }, this.gLabels);
      label.textContent = r.displayName;
      this.nodes.set(r.name, { g, label, x, y, r });
      g.addEventListener("click", (ev) => { ev.stopPropagation(); if (!this._dragged) this.onSelect(r.name); });
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.onSelect(r.name); } });
      g.addEventListener("pointerenter", (ev) => this.onHover(r.name, ev));
      g.addEventListener("pointermove", (ev) => this.onHover(r.name, ev));
      g.addEventListener("pointerleave", () => this.onHover(null));
      g.addEventListener("focus", (ev) => this.onHover(r.name, ev));
      g.addEventListener("blur", () => this.onHover(null));
    });
    this._apply();
  }

  // styleFn(region) -> { cls: "s2" | "s1" | "s0" | "q3" ..., title }
  paint(styleFn) {
    for (const n of this.nodes.values()) {
      const s = styleFn(n.r) || {};
      n.g.setAttribute("class", "mk " + (s.cls || "") + (this.selected === n.r.name ? " sel" : ""));
    }
  }

  select(name, { zoom = false } = {}) {
    if (this.selected && this.nodes.get(this.selected)) this.nodes.get(this.selected).g.classList.remove("sel");
    this.selected = name;
    const n = this.nodes.get(name);
    if (!n) return;
    n.g.classList.add("sel");
    this.gRegions.appendChild(n.g); // bring to front
    if (zoom) this.zoomTo(n.x, n.y, Math.max(this.k, 3));
  }

  zoomTo(x, y, k) {
    const w = W.meta.w, h = W.meta.h;
    this._animate(k, w / 2 - x * k, h / 2 - y * k);
  }

  fitRegions(names) {
    const pts = names.map((n) => this.nodes.get(n)).filter(Boolean);
    if (!pts.length) return this.reset();
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const w = W.meta.w, h = W.meta.h;
    const k = Math.max(1, Math.min(8, 0.8 * Math.min(w / Math.max(x1 - x0, 20), h / Math.max(y1 - y0, 12))));
    this.zoomTo((x0 + x1) / 2, (y0 + y1) / 2, k);
  }

  reset() { this._animate(1, 0, 0); }
  zoomBy(f) {
    const w = W.meta.w, h = W.meta.h;
    const cx = (w / 2 - this.tx) / this.k, cy = (h / 2 - this.ty) / this.k;
    const k = this._clampK(this.k * f);
    this._animate(k, w / 2 - cx * k, h / 2 - cy * k);
  }

  _clampK(k) { return Math.max(1, Math.min(14, k)); }
  _clampT() {
    const w = W.meta.w, h = W.meta.h;
    this.tx = Math.min(0, Math.max(w - w * this.k, this.tx));
    this.ty = Math.min(0, Math.max(h - h * this.k, this.ty));
  }

  _animate(k, tx, ty) {
    k = this._clampK(k);
    const from = { k: this.k, tx: this.tx, ty: this.ty };
    if (!this.motion()) { this.k = k; this.tx = tx; this.ty = ty; this._clampT(); return this._apply(); }
    const t0 = performance.now(), dur = 420;
    cancelAnimationFrame(this._raf);
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      this.k = from.k + (k - from.k) * e; this.tx = from.tx + (tx - from.tx) * e; this.ty = from.ty + (ty - from.ty) * e;
      this._clampT(); this._apply();
      if (p < 1) this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }

  _apply() {
    this.vp.setAttribute("transform", `translate(${this.tx.toFixed(2)} ${this.ty.toFixed(2)}) scale(${this.k.toFixed(4)})`);
    const s = 1 / Math.pow(this.k, 0.85);
    for (const n of this.nodes.values()) {
      n.g.setAttribute("transform", `translate(${n.x.toFixed(2)} ${n.y.toFixed(2)}) scale(${s.toFixed(4)})`);
      n.label.setAttribute("x", (n.x + 7 * s).toFixed(2));
      n.label.setAttribute("y", (n.y + 3.2 * s).toFixed(2));
      n.label.setAttribute("font-size", (10 * s).toFixed(2));
    }
    this.svg.classList.toggle("show-labels", this.k >= 2.6);
    this.vp.querySelectorAll(".land, .borders, .graticule, .sphere").forEach((p) => p.setAttribute("stroke-width", (0.6 / this.k).toFixed(3)));
  }

  _point(ev) {
    const pt = this.svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    return pt.matrixTransform(this.svg.getScreenCTM().inverse());
  }

  _interact() {
    const svg = this.svg;
    svg.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const p = this._point(ev);
      const k = this._clampK(this.k * Math.pow(1.0018, -ev.deltaY));
      const cx = (p.x - this.tx) / this.k, cy = (p.y - this.ty) / this.k;
      this.k = k; this.tx = p.x - cx * k; this.ty = p.y - cy * k;
      this._clampT(); this._apply();
    }, { passive: false });
    const ptrs = new Map();
    let start = null, pinch = null;
    svg.addEventListener("pointerdown", (ev) => {
      ptrs.set(ev.pointerId, this._point(ev));
      if (ptrs.size === 1) { start = { p: this._point(ev), tx: this.tx, ty: this.ty }; this._dragged = false; }
      if (ptrs.size === 2) {
        const [a, b] = [...ptrs.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: this.k, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, tx: this.tx, ty: this.ty };
      }
    });
    svg.addEventListener("pointermove", (ev) => {
      if (!ptrs.has(ev.pointerId)) return;
      ptrs.set(ev.pointerId, this._point(ev));
      if (ptrs.size === 2 && pinch) {
        const [a, b] = [...ptrs.values()];
        const k = this._clampK(pinch.k * Math.hypot(a.x - b.x, a.y - b.y) / pinch.d);
        const mx = (pinch.cx - pinch.tx) / pinch.k, my = (pinch.cy - pinch.ty) / pinch.k;
        this.k = k; this.tx = pinch.cx - mx * k; this.ty = pinch.cy - my * k;
        this._dragged = true; this._clampT(); this._apply();
      } else if (start) {
        const p = this._point(ev);
        const dx = p.x - start.p.x, dy = p.y - start.p.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) {
          if (!this._dragged) svg.setPointerCapture?.(ev.pointerId);
          this._dragged = true;
        }
        if (this._dragged) { this.tx = start.tx + dx; this.ty = start.ty + dy; this._clampT(); this._apply(); svg.classList.add("dragging"); }
      }
    });
    const end = (ev) => {
      ptrs.delete(ev.pointerId);
      if (ptrs.size < 2) pinch = null;
      if (!ptrs.size) { start = null; svg.classList.remove("dragging"); setTimeout(() => { this._dragged = false; }, 0); }
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", end);
    svg.addEventListener("dblclick", (ev) => {
      const p = this._point(ev);
      const cx = (p.x - this.tx) / this.k, cy = (p.y - this.ty) / this.k;
      const k = this._clampK(this.k * 2);
      this._animate(k, p.x - cx * k, p.y - cy * k);
    });
  }
}
