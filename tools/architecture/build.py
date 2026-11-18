#!/usr/bin/env python3
"""Builds every architecture artifact from model.py (run: python3 tools/architecture/build.py):
  docs/index.html            inline SVG for the dashboard (between <!-- arch:svg --> markers)
  docs/assets/js/arch-flows.js  flow data for the hop-by-hop animation
  docs/assets/css/app.css    diagram styles + light/dark palette (between /* arch:css */ markers)
  docs/assets/img/architecture.svg                 static diagram (light)
  docs/assets/img/architecture-animated.svg        self-running animation for the README (light)
  docs/assets/img/architecture-animated-dark.svg   same, dark
"""
import base64, html, json, math, os, re, sys
try:
    from PIL import ImageFont          # optional: only used to warn about text that may not fit
except ImportError:
    ImageFont = None

sys.path.insert(0, os.path.dirname(__file__))
from model import W, H, ZONES, NODES, SEGS, FLOWS, FLOW_ORDER, SRC

REPO = os.environ.get("ASA_REPO") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ICONS = REPO + "/docs/assets/icons/"
FONT = '"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif'
MONO = '"Cascadia Code",Consolas,"SFMono-Regular",Menlo,monospace'
CAP = 84                      # caption band height (animated versions)
PX_PER_S, MIN_HOP, BURST_GAP, DWELL, EMPTY_DWELL, FLOW_GAP = 240, 0.45, 0.14, 0.9, 2.4, 1.2
README_SPEED = 1.25
esc = lambda s: html.escape(str(s), quote=True)
WARN = []

# ---------------------------------------------------------------- text metrics (Arial metrics: wider than Segoe UI)
_F = {}
def tw(text, size, weight="normal", mono=False):
    key = (weight, mono)
    if key not in _F:
        base = "/usr/share/fonts/metric-compat/"
        f = "LiberationMono-Regular.ttf" if mono else ("LiberationSans-Bold.ttf" if weight == "bold" else "LiberationSans-Regular.ttf")
        try:
            _F[key] = ImageFont.truetype(base + f, size=100)
        except Exception:
            _F[key] = None
    if _F[key] is None:               # rough Arial-like estimate
        return len(text) * size * (0.6 if mono else 0.62 if weight == "bold" else 0.55)
    return _F[key].getlength(text) * size / 100

def fit(text, size, avail, what, weight="normal", mono=False):
    w = tw(text, size, weight, mono)
    if w > avail + 0.5:
        WARN.append(f"{what}: '{text}' is {w:.0f}px, room {avail:.0f}px")
    return text

# ---------------------------------------------------------------- palettes (tokens used by the CSS template)
LIGHT = {
    "bg": "#ffffff", "text": "#1b1f24", "muted": "#5d6b7a", "card": "#ffffff", "card-s": "#c9d3de", "halo": "#ffffff",
    "zweb-f": "#f6f8fa", "zweb-s": "#b4bec9", "zid-f": "#f5f2fc", "zid-s": "#9d86d8", "zaz-f": "#f2f8fe", "zaz-s": "#0078d4",
    "zvn-f": "#ffffff", "zvn-s": "#5b9bd9", "zsn-f": "#edf5fd", "zsn-s": "#98bfe6", "zsn-t": "#0b5cab", "zop-f": "#fbf7ef", "zop-s": "#c9a35a",
    "pill-f": "#0078d4", "pill-t": "#ffffff", "chip-f": "#f7f5fd", "chip-s": "#cfc3ee", "port-f": "#f7fbff", "port-s": "#98bfe6",
    "timer-f": "#fff6e5", "timer-s": "#e8a33c", "timer-t": "#7a4b00", "lock": "#c4314b",
    "e-pub": "#6f7f90", "e-pri": "#0f6cbd", "e-id": "#7a5bd0", "e-tel": "#9a6fb0", "e-ops": "#a5761f", "e-link": "#7f8ea0",
    "f-collect": "#e07b00", "f-guest": "#0e9384", "f-signedin": "#2f6fe0", "f-deploy": "#b4389a",
}
DARK = {
    "bg": "#0f141a", "text": "#e8eef4", "muted": "#9aabbc", "card": "#161d25", "card-s": "#334252", "halo": "#121a22",
    "zweb-f": "#121a22", "zweb-s": "#3b4857", "zid-f": "#17142a", "zid-s": "#7d68c8", "zaz-f": "#0f1b29", "zaz-s": "#3d8bd0",
    "zvn-f": "#111c29", "zvn-s": "#3f78b5", "zsn-f": "#14263a", "zsn-s": "#33608f", "zsn-t": "#8cc3f7", "zop-f": "#1d1910", "zop-s": "#8c7038",
    "pill-f": "#3d8bd0", "pill-t": "#0f141a", "chip-f": "#1f1b33", "chip-s": "#4b3f80", "port-f": "#14263a", "port-s": "#33608f",
    "timer-f": "#2a2010", "timer-s": "#c48a2c", "timer-t": "#f5c46b", "lock": "#ef6f86",
    "e-pub": "#8d9aab", "e-pri": "#4f9fe8", "e-id": "#a58cf0", "e-tel": "#c39bd6", "e-ops": "#d1a050", "e-link": "#8d9aab",
    "f-collect": "#f5a524", "f-guest": "#2cc3b0", "f-signedin": "#6b9bff", "f-deploy": "#e070c4",
}
FLOWCOL = {"collect": "f-collect", "guest": "f-guest", "signedin": "f-signedin", "deploy": "f-deploy"}

CSS = """
.arch-svg{font-family:@FONT@}
.az-zr{stroke-width:1.2}
.z-web .az-zr{fill:@zweb-f@;stroke:@zweb-s@}
.z-identity .az-zr{fill:@zid-f@;stroke:@zid-s@}
.z-azure .az-zr{fill:@zaz-f@;stroke:@zaz-s@;stroke-width:1.6}
.z-vnet .az-zr{fill:@zvn-f@;stroke:@zvn-s@;stroke-dasharray:8 4}
.z-subnet .az-zr{fill:@zsn-f@;stroke:@zsn-s@;stroke-dasharray:4 3}
.z-ops .az-zr{fill:@zop-f@;stroke:@zop-s@}
.z-box .az-zr{fill:@card@;stroke:@card-s@}
.az-zt{font-size:13px;font-weight:600;fill:@text@}
.az-zk{font-size:10.5px;fill:@muted@}
.z-subnet .az-zt{font-size:11.5px;fill:@zsn-t@}
.az-card{fill:@card@;stroke:@card-s@;stroke-width:1.2}
.az-t{font-size:12.5px;font-weight:600;fill:@text@}
.az-m{font-size:10.5px;fill:@muted@;font-family:@MONO@}
.az-s{font-size:11px;fill:@muted@}
.az-pill rect{fill:@pill-f@}
.az-pill text{font-size:9px;font-weight:700;fill:@pill-t@;letter-spacing:.06em}
.az-chip rect{fill:@chip-f@;stroke:@chip-s@}
.az-chip text{font-size:10.5px;fill:@text@}
.az-port .az-card{fill:@port-f@;stroke:@port-s@}
.az-port .az-t{font-size:11px}
.az-timer rect{fill:@timer-f@;stroke:@timer-s@}
.az-timer text{font-size:10px;font-weight:600;fill:@timer-t@;font-family:@MONO@}
.az-lock{fill:@lock@}
.az-seg{fill:none;stroke-width:1.8}
.cat-public .az-seg{stroke:@e-pub@;marker-end:url(#@MID@-public)}
.cat-private .az-seg{stroke:@e-pri@;stroke-width:2.2;stroke-dasharray:7 4;marker-end:url(#@MID@-private)}
.cat-identity .az-seg{stroke:@e-id@;stroke-dasharray:1.5 4;stroke-linecap:round;stroke-width:2.2;marker-end:url(#@MID@-identity)}
.cat-telemetry .az-seg{stroke:@e-tel@;stroke-dasharray:1.5 4;stroke-linecap:round;stroke-width:2.2;marker-end:url(#@MID@-telemetry)}
.cat-ops .az-seg{stroke:@e-ops@;stroke-dasharray:10 4;marker-end:url(#@MID@-ops)}
.cat-link .az-seg{stroke:@e-link@;stroke-dasharray:1.5 4;stroke-linecap:round;stroke-width:2}
.az-sl{font-size:10.5px;fill:@muted@;paint-order:stroke;stroke:@halo@;stroke-width:4px;stroke-linejoin:round}
.mk-public{fill:@e-pub@}.mk-private{fill:@e-pri@}.mk-identity{fill:@e-id@}.mk-telemetry{fill:@e-tel@}.mk-ops{fill:@e-ops@}
.az-note{font-size:10.5px;fill:@muted@}
.az-lgh{font-size:12px;font-weight:600;fill:@text@}
.az-lg{font-size:11px;fill:@text@}
.az-badge circle{stroke:@card@;stroke-width:2}
.az-badge text{font-size:10.5px;font-weight:700;fill:#fff;text-anchor:middle}
.az-cap{fill:@card@;stroke:@card-s@}
.az-capt{font-size:14px;font-weight:600;fill:@text@}
.az-capx{font-size:12.5px;fill:@text@}
.az-capn{font-size:11px;fill:@muted@}
.az-flowchip text{font-size:11.5px;font-weight:700;fill:#fff}
"""

def css(mode, pal=None):
    out = CSS.replace("@FONT@", FONT).replace("@MONO@", MONO).replace("@MID@", "arch-m" if mode == "inline" else "m")
    return re.sub(r"@([a-z0-9-]+)@", (lambda m: f"var(--az-{m.group(1)})") if mode == "inline" else (lambda m: pal[m.group(1)]), out)

# ---------------------------------------------------------------- geometry
def sgn(v): return (v > 0) - (v < 0)

def path_d(pts, r=9, hops=()):
    """Orthogonal polyline with rounded corners and little bridges where it crosses another line."""
    d = [f"M{pts[0][0]} {pts[0][1]}"]
    cur = pts[0]
    def line_to(p):
        nonlocal cur
        (x0, y0), (x1, y1) = cur, p
        if y0 == y1 and x0 != x1:
            dirx = sgn(x1 - x0)
            for hx in sorted(hops, key=lambda h: (h - x0) * dirx):
                if min(x0, x1) + 8 < hx < max(x0, x1) - 8:
                    a, b = hx - 6 * dirx, hx + 6 * dirx
                    d.append(f"L{a} {y0}")
                    d.append(f"A6 6 0 0 {1 if dirx > 0 else 0} {b} {y0}")
        d.append(f"L{p[0]} {p[1]}")
        cur = p
    for i in range(1, len(pts)):
        x1, y1 = pts[i]
        if i < len(pts) - 1:
            x0, y0 = pts[i - 1]; x2, y2 = pts[i + 1]
            lin = abs(x1 - x0) + abs(y1 - y0); lout = abs(x2 - x1) + abs(y2 - y1)
            rr = min(r, lin / 2, lout / 2)
            a = (x1 - sgn(x1 - x0) * rr, y1 - sgn(y1 - y0) * rr)
            b = (x1 + sgn(x2 - x1) * rr, y1 + sgn(y2 - y1) * rr)
            line_to(a)
            d.append(f"Q{x1} {y1} {b[0]} {b[1]}")
            cur = b
        else:
            line_to((x1, y1))
    return " ".join(d)

def poly_len(pts):
    L = sum(abs(pts[i][0] - pts[i - 1][0]) + abs(pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))
    return L - (len(pts) - 2) * 9 * (2 - 1.1478)

def point_at(pts, frac):
    total = sum(abs(pts[i][0] - pts[i - 1][0]) + abs(pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))
    goal, acc = total * frac, 0
    for i in range(1, len(pts)):
        (x0, y0), (x1, y1) = pts[i - 1], pts[i]
        l = abs(x1 - x0) + abs(y1 - y0)
        if acc + l >= goal:
            u = (goal - acc) / l if l else 0
            return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
        acc += l
    return pts[-1]

def nbox(nid):
    b = NODES[nid]["box"]
    return (b[0], b[1], b[2], b[3] if len(b) > 3 else 72)

# ---------------------------------------------------------------- icons
_URI = {}
def icon_uri(name):
    if name not in _URI:
        _URI[name] = "data:image/svg+xml;base64," + base64.b64encode(open(ICONS + name + ".svg", "rb").read()).decode()
    return _URI[name]

class Ctx:
    def __init__(self, mode):
        self.mode = mode                       # inline | static | anim
        self.inline = mode == "inline"
        self.pre = "arch-" if self.inline else ""
        self.used = set()
    def icon(self, name, x, y, s, extra=""):
        if self.inline:
            return f'<image href="assets/icons/{name}.svg" x="{x}" y="{y}" width="{s}" height="{s}"{extra}/>'
        self.used.add(name)
        return f'<use xlink:href="#i-{name}" x="{x}" y="{y}" width="{s}" height="{s}"{extra}/>'

# ---------------------------------------------------------------- pieces
def zone_svg(c, z):
    x, y, w, h = z["box"]
    o = [f'<g class="az-zone z-{z["kind"]}"><rect class="az-zr" x="{x}" y="{y}" width="{w}" height="{h}" rx="{14 if z["kind"] in ("azure", "web", "identity", "ops") else 10}"/>']
    ix = z.get("tx", x + 12)
    tx = ix + 2
    ty = y + 22 if z["kind"] != "subnet" else y + 19
    if z.get("icon"):
        s = 18 if z["kind"] != "subnet" else 15
        o.append(c.icon(z["icon"], ix, ty - (14 if s == 18 else 12), s))
        tx = ix + s + 6
    if z.get("kicker"):
        o.append(f'<text class="az-zk" x="{tx}" y="{ty - 3}">{esc(z["kicker"])}</text>')
        ty += 14
    size = 13 if z["kind"] != "subnet" else 11.5
    fit(z["title"], size, w - (tx - x) - 12, "zone " + z["id"], "bold")
    o.append(f'<text class="az-zt" x="{tx}" y="{ty}">{esc(z["title"])}</text></g>')
    return "".join(o)

def node_svg(c, nid):
    n = NODES[nid]
    x, y, w, h = nbox(nid)
    port = n.get("kind") == "port"
    o = [f'<g class="az-node{" az-port" if port else ""}" data-node="{nid}" id="{c.pre}node-{nid}">',
         f'<rect class="az-card" x="{x}" y="{y}" width="{w}" height="{h}" rx="{8 if port else 10}"/>']
    if port:
        o.append(c.icon(n["icon"], x + 10, y + 9, 22))
        fit(n["title"], 11, w - 48, "node " + nid, "bold")
        o.append(f'<text class="az-t" x="{x + 40}" y="{y + 24}">{esc(n["title"])}</text></g>')
        return "".join(o)
    o.append(c.icon(n["icon"], x + 12, y + 19, 34))
    tx, avail = x + 56, w - 56 - 10
    if n.get("chips"):
        avail = 470
    fit(n["title"], 12.5, avail - (40 if n.get("pill") else 0), "node " + nid, "bold")
    o.append(f'<text class="az-t" x="{tx}" y="{y + 24}">{esc(n["title"])}</text>')
    if n.get("mono"):
        fit(n["mono"], 10.5, avail, "node " + nid, mono=True)
        o.append(f'<text class="az-m" x="{tx}" y="{y + 41}">{esc(n["mono"])}</text>')
    elif n.get("sub2"):
        fit(n["sub2"], 11, avail, "node " + nid)
        o.append(f'<text class="az-s" x="{tx}" y="{y + 41}">{esc(n["sub2"])}</text>')
    if n.get("sub"):
        fit(n["sub"], 11, avail, "node " + nid)
        o.append(f'<text class="az-s" x="{tx}" y="{y + 57}">{esc(n["sub"])}</text>')
    if n.get("pill"):
        pw = tw(n["pill"], 9, "bold") + 1 + 12
        px = x + w - 8 - pw
        o.append(f'<g class="az-pill"><rect x="{px:.1f}" y="{y + 12}" width="{pw:.1f}" height="15" rx="7.5"/><text x="{px + pw / 2:.1f}" y="{y + 22.5}" text-anchor="middle">{esc(n["pill"])}</text></g>')
    if n.get("lock"):
        lx, ly = x + w - 20, y + 9
        o.append(f'<g class="az-lockg"><title>Public network access disabled</title><path class="az-lock" d="M{lx + 2} {ly + 6}h8a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1zm1.6 0v-2.2a2.4 2.4 0 0 1 4.8 0v2.2h-1.4v-2.2a1 1 0 0 0-2 0v2.2z"/></g>')
    if n.get("timer"):
        t = n["timer"]
        pw = tw(t, 10, mono=True) + 34
        o.append(f'<g class="az-timer" id="{c.pre}timer"><rect x="{x + 10}" y="{y - 11}" width="{pw:.1f}" height="22" rx="11"/>{c.icon("scheduler", x + 15, y - 8, 16)}<text x="{x + 36}" y="{y + 3.5}">{esc(t)}</text></g>')
    if n.get("chips"):
        cy = y + 6
        for ic, label in n["chips"]:
            cw = 214
            fit(label, 10.5, cw - 34, "chip")
            cx = x + w - cw - 10
            o.append(f'<g class="az-chip"><rect x="{cx}" y="{cy}" width="{cw}" height="26" rx="13"/>{c.icon(ic, cx + 8, cy + 5, 16)}<text x="{cx + 30}" y="{cy + 17}">{esc(label)}</text></g>')
            cy += 32
    o.append("</g>")
    return "".join(o)

def seg_svg(c, sid):
    s = SEGS[sid]
    d = path_d(s["pts"], hops=s.get("hops", ()))
    cls = f'az-seg-g cat-{s["cat"]}'
    arrow = "" if s.get("arrow", True) else ' style="marker-end:none"'
    o = [f'<g class="{cls}" data-seg="{sid}"><path id="{c.pre}seg-{sid}" class="az-seg" d="{d}"{arrow}/>']
    if s.get("label"):
        lab = s["label"]
        text, lx, ly, anchor = lab[:4]
        rot = f' transform="rotate({lab[4]} {lx} {ly})"' if len(lab) > 4 else ""
        dy = ' dominant-baseline="middle"' if rot else ""
        o.append(f'<text class="az-sl" x="{lx}" y="{ly}" text-anchor="{anchor}"{rot}{dy}>{esc(text)}</text>')
    o.append("</g>")
    return "".join(o)

def markers(c, flows_too=False, pal=None):
    mid = "arch-m" if c.inline else "m"
    o = ["<defs>"]
    for cat in ["public", "private", "identity", "telemetry", "ops"]:
        o.append(f'<marker id="{mid}-{cat}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="mk-{cat}" d="M0 0L10 5L0 10z"/></marker>')
    if c.inline:
        o.append(f'<marker id="{mid}-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="mk-on" d="M0 0L10 5L0 10z"/></marker>')
    if flows_too:
        for f in FLOW_ORDER:
            o.append(f'<marker id="m-{f}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path fill="{pal[FLOWCOL[f]]}" d="M0 0L10 5L0 10z"/></marker>')
    o.append("</defs>")
    return "".join(o)

def extras_svg(c):
    o = []
    # egress note in snet-functions
    o.append('<text class="az-note" x="744" y="434" text-anchor="middle">All outbound traffic from both apps leaves through this subnet</text>')
    o.append('<text class="az-note" x="744" y="450" text-anchor="middle">internet egress is platform-managed here · a NAT gateway gives a fixed IP</text>')
    fit("All outbound traffic from both apps leaves through this subnet", 10.5, 500, "note")
    fit("internet egress is platform-managed here · a NAT gateway gives a fixed IP", 10.5, 500, "note")
    # legend
    x, y, w, h = 1236, 548, 268, 252
    o.append(f'<g class="az-zone z-box"><rect class="az-zr" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/></g>')
    o.append(f'<text class="az-lgh" x="{x + 14}" y="{y + 22}">Legend</text>')
    yy = y + 42
    for f in FLOWS:
        o.append(f'<circle cx="{x + 22}" cy="{yy - 4}" r="5" class="lg-dot lg-{f["id"]}"/><text class="az-lg" x="{x + 36}" y="{yy}">{esc(f["name"])}</text>')
        yy += 17
    yy += 4
    for cat, label in [("public", "HTTPS to a public endpoint"), ("private", "private: VNet → private endpoint"),
                       ("identity", "identity: tokens, signing keys"), ("telemetry", "telemetry"),
                       ("ops", "deployment and operations"), ("link", "private DNS zone link")]:
        o.append(f'<g class="az-seg-g cat-{cat}"><path class="az-seg" d="M{x + 14} {yy - 4}h34"{' style="marker-end:none"' if cat == "link" else ""}/></g><text class="az-lg" x="{x + 58}" y="{yy}">{esc(label)}</text>')
        fit(label, 11, w - 66, "legend")
        yy += 18
    lx, ly = x + 24, yy - 14
    o.append(f'<path class="az-lock" d="M{lx + 2} {ly + 6}h8a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1zm1.6 0v-2.2a2.4 2.4 0 0 1 4.8 0v2.2h-1.4v-2.2a1 1 0 0 0-2 0v2.2z"/><text class="az-lg" x="{x + 58}" y="{yy}">public network access disabled</text>')
    # security box
    x, y, w, h = 16, 696, 248, 104
    o.append(f'<g class="az-zone z-box"><rect class="az-zr" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/></g>')
    o.append(f'<text class="az-lgh" x="{x + 14}" y="{y + 22}">Security by design</text>')
    for i, t in enumerate(["No secrets in the page or the repo", "Managed identities for ARM, Redis, storage",
                           "Redis and storage: no public access, no keys", "API CORS: ibranibeny.github.io only"]):
        fit(t, 10.5, w - 34, "security")
        o.append(f'<circle cx="{x + 18}" cy="{y + 39 + i * 17}" r="2.2" class="lg-bullet"/><text class="az-note" x="{x + 26}" y="{y + 43 + i * 17}">{esc(t)}</text>')
    return "".join(o)

# ---------------------------------------------------------------- badges
def badge_positions():
    pos = {}
    manual = {("collect", 0): (950, 247), ("guest", 2): (296, 246)}
    for f in FLOWS:
        placed = []
        for i, st in enumerate(f["steps"]):
            p = manual.get((f["id"], i))
            if not p:
                pts = SEGS[st["hops"][0][0]]["pts"]
                for frac in (0.5, 0.3, 0.7, 0.2, 0.8, 0.4, 0.6, 0.12, 0.88):
                    q = point_at(pts, frac)
                    if all(math.dist(q, o) >= 24 for o in placed):
                        p = q
                        break
                p = p or point_at(pts, 0.5)
            placed.append(p)
            pos[(f["id"], i)] = (round(p[0], 1), round(p[1], 1))
    return pos
BADGES = badge_positions()

def badge_svg(fid, i, color):
    x, y = BADGES[(fid, i)]
    return f'<g class="az-badge"><circle cx="{x}" cy="{y}" r="9" fill="{color}"/><text x="{x}" y="{y + 3.8}">{i + 1}</text></g>'

# ---------------------------------------------------------------- timeline (same constants as arch.js)
def timeline(speed):
    t, flows = 0.0, []
    for fid in FLOW_ORDER:
        f = next(x for x in FLOWS if x["id"] == fid)
        f0, steps = t, []
        for i, st in enumerate(f["steps"]):
            s0, hops, ht = t, [], 0.0
            for hop in st["hops"]:
                seg, dirn, tag = hop[:3]
                burst = hop[3] if len(hop) > 3 else 1
                dur = max(MIN_HOP, poly_len(SEGS[seg]["pts"]) / PX_PER_S) / speed
                hops.append(dict(seg=seg, dir=dirn, tag=tag, burst=burst, start=s0 + ht, dur=dur))
                ht += dur + (burst - 1) * BURST_GAP / speed
            end = s0 + ht + (DWELL if st["hops"] else EMPTY_DWELL) / speed
            steps.append(dict(i=i, start=s0, end=end, hops=hops, st=st))
            t = end
        t += FLOW_GAP / speed
        flows.append(dict(f=f, start=f0, end=t, steps=steps))
    return flows, t

def wrap(text, size, width):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        nxt = (cur + " " + wd).strip()
        if tw(nxt, size) > width and cur:
            lines.append(cur); cur = wd
        else:
            cur = nxt
    lines.append(cur)
    return lines

def tag_left(h):
    """Tags of packets that travel near the right edge are drawn to the left of the dot."""
    xs = [p[0] for p in SEGS[h["seg"]]["pts"]]
    return max(xs) > 1300

def smil(c, pal, speed):
    flows, total = timeline(speed)
    T = lambda v: f"clk.begin+{v:.2f}s"
    o = [f'<rect width="1" height="1" x="-10" y="-10" fill="none"><animate id="clk" attributeName="x" values="-10;-10" dur="{total:.2f}s" begin="0s;clk.end"/></rect>']
    hl, nodes_hl, pk, caps = [], [], [], []
    for fl in flows:
        f, col = fl["f"], pal[FLOWCOL[fl["f"]["id"]]]
        # badges for the whole flow
        bad = "".join(badge_svg(f["id"], i, col) for i in range(len(f["steps"])))
        hl.append(f'<g opacity="0">{bad}<set attributeName="opacity" to="1" begin="{T(fl["start"])}" dur="{fl["end"] - fl["start"]:.2f}s"/></g>')
        for s in fl["steps"]:
            st, dur = s["st"], s["end"] - s["start"]
            segs = []
            for h in s["hops"]:
                if h["seg"] not in segs:
                    segs.append(h["seg"])
            for sid in segs:
                d = path_d(SEGS[sid]["pts"], hops=SEGS[sid].get("hops", ()))
                mk = "" if SEGS[sid].get("arrow", True) is False else f' marker-end="url(#m-{f["id"]})"'
                hl.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="3.4" stroke-linecap="round" opacity="0"{mk}><set attributeName="opacity" to="1" begin="{T(s["start"])}" dur="{dur:.2f}s"/></path>')
            nodes = set(st.get("focus", []))
            for sid in segs:
                nodes.update(n for n in SEGS[sid]["ends"] if n in NODES)
            for nid in sorted(nodes):
                x, y, w, h = nbox(nid)
                nodes_hl.append(f'<rect x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="12" fill="none" stroke="{col}" stroke-width="2.6" opacity="0"><set attributeName="opacity" to="1" begin="{T(s["start"])}" dur="{dur:.2f}s"/></rect>')
            if f["id"] == "collect" and s["i"] == 0:
                cx, cy = NODES["collector"]["box"][0] + 20, NODES["collector"]["box"][1]
                for k in range(3):
                    b = s["start"] + k * 0.7 / speed
                    nodes_hl.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="none" stroke="{col}" stroke-width="2" opacity="0"><animate attributeName="r" values="10;30" begin="{T(b)}" dur="{1.2 / speed:.2f}s"/><animate attributeName="opacity" values="0.9;0" begin="{T(b)}" dur="{1.2 / speed:.2f}s"/></circle>')
            for h in s["hops"]:
                for k in range(h["burst"]):
                    b = h["start"] + k * BURST_GAP / speed
                    kp = "0;1" if h["dir"] > 0 else "1;0"
                    tag = ""
                    if h["tag"] and k == 0:
                        tw_ = tw(h["tag"], 13, "bold") + 16
                        tx_ = 12 if not tag_left(h) else -12 - tw_
                        tag = (f'<g transform="translate({tx_:.1f} -34)"><rect width="{tw_:.1f}" height="22" rx="11" fill="{pal["card"]}" stroke="{col}" stroke-width="1.6"/>'
                               f'<text x="8" y="15.5" font-size="13" font-weight="600" fill="{pal["text"]}">{esc(h["tag"])}</text></g>')
                    pk.append(f'<g opacity="0"><circle r="16" fill="{col}" opacity=".25"/><circle r="8" fill="{col}" stroke="{pal["card"]}" stroke-width="2.5"/>{tag}'
                              f'<animateMotion begin="{T(b)}" dur="{h["dur"]:.2f}s" fill="freeze" calcMode="linear" keyPoints="{kp}" keyTimes="0;1"><mpath xlink:href="#seg-{h["seg"]}"/></animateMotion>'
                              f'<animate attributeName="opacity" begin="{T(b)}" dur="{h["dur"]:.2f}s" values="0;1;1;0" keyTimes="0;0.1;0.9;1" fill="freeze"/></g>')
            # caption
            lines = wrap(st["text"], 12.5, 1150)
            if len(lines) > 2:
                WARN.append(f"caption {f['id']}#{s['i'] + 1} wraps to {len(lines)} lines")
            chipw = tw(f["name"], 11.5, "bold") + 24
            cap = [f'<g class="az-flowchip"><rect x="32" y="{H + 12}" width="{chipw:.1f}" height="22" rx="11" fill="{col}"/><text x="44" y="{H + 27}">{esc(f["name"])}</text></g>',
                   f'<text class="az-capn" x="{40 + chipw:.1f}" y="{H + 27}">step {s["i"] + 1} of {len(f["steps"])}</text>',
                   f'<circle cx="{215 + 20}" cy="{H + 54}" r="0" />',
                   f'<text class="az-capt" x="32" y="{H + 56}">{esc(st["title"])}</text>']
            tx = 32 + tw(st["title"], 14, "bold") + 14
            for li, line in enumerate(lines[:2]):
                cap.append(f'<text class="az-capx" x="{tx if li == 0 else 32:.1f}" y="{H + 56 + li * 17}">{esc(line)}</text>' if li == 0 else f'<text class="az-capx" x="32" y="{H + 73}">{esc(line)}</text>')
            caps.append(f'<g opacity="0">{"".join(cap)}<set attributeName="opacity" to="1" begin="{T(s["start"])}" dur="{dur:.2f}s"/></g>')
    return "".join(o) + "".join(nodes_hl) + "".join(hl) + "".join(pk), "".join(caps), total

# ---------------------------------------------------------------- whole SVG
def svg(mode, pal=None, theme="light", preview=False):
    c = Ctx(mode)
    anim = mode == "anim"
    height = H + (CAP if anim else 0)
    body = [markers(c, flows_too=anim, pal=pal)]
    for z in ZONES:
        body.append(zone_svg(c, z))
    body.append(f'<g id="{c.pre}segs">' + "".join(seg_svg(c, s) for s in SEGS) + "</g>")
    body.append(extras_svg(c))
    body.append(f'<g id="{c.pre}nodes">' + "".join(node_svg(c, n) for n in NODES) + "</g>")
    caps, total = "", 0
    if mode == "static":
        for fid in ("collect", "signedin"):
            f = next(x for x in FLOWS if x["id"] == fid)
            body.append("".join(badge_svg(fid, i, pal[FLOWCOL[fid]]) for i in range(len(f["steps"]))))
    if anim:
        layer, caps, total = smil(c, pal, README_SPEED)
        body.append(layer)
        body.append(f'<rect class="az-cap" x="16" y="{H + 2}" width="{W - 32}" height="{CAP - 10}" rx="12"/>' + caps)
    if c.inline:
        body.append('<g id="arch-badges"></g><g id="arch-pkts"></g>')
    title = "Azure Service Availability architecture"
    desc = ("GitHub Pages dashboard in the browser; optional Microsoft Entra ID sign-in; API and collector Function apps "
            "(Flex Consumption, Indonesia Central) with user-assigned managed identities; VNet integration and private endpoints "
            "to Azure Managed Redis and Storage; the collector calls Azure Resource Manager and the Azure Retail Prices API every 6 hours.")
    if c.inline:
        head = (f'<svg class="arch-svg" id="archSvg" viewBox="0 0 {W} {height}" role="img" aria-labelledby="arch-title arch-desc">'
                f'<title id="arch-title">{title}</title><desc id="arch-desc">{esc(desc)}</desc>')
        return head + "".join(body) + "</svg>"
    style = css("standalone", pal)
    lg = "".join(f".lg-{f}{{fill:{pal[FLOWCOL[f]]}}}" for f in FLOW_ORDER) + f".lg-bullet{{fill:{pal['muted']}}}"
    if preview:
        style = style.replace(FONT, '"Liberation Sans",Arial,sans-serif').replace(MONO, '"Liberation Mono",monospace')
    syms = "".join(f'<symbol id="i-{n}" viewBox="0 0 64 64"><image width="64" height="64" xlink:href="{icon_uri(n)}"/></symbol>' for n in sorted(c.used))
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" class="arch-svg" viewBox="0 0 {W} {height}" '
            f'width="{W}" height="{height}" role="img" aria-labelledby="t d"><title id="t">{title}</title><desc id="d">{esc(desc)}</desc>'
            f'<style>{style}{lg}</style><defs>{syms}</defs><rect width="{W}" height="{height}" fill="{pal["bg"]}"/>')
    return head + "".join(body) + "</svg>", total

# ---------------------------------------------------------------- outputs
def flows_js():
    flows = []
    for f in FLOWS:
        steps = []
        for i, st in enumerate(f["steps"]):
            src = SRC[st["src"]] if st.get("src") else None
            steps.append(dict(title=st["title"], text=st["text"], src=list(src) if src else None,
                              hops=[[h[0], h[1], h[2], h[3] if len(h) > 3 else 1] for h in st["hops"]],
                              focus=st.get("focus", []), badge=list(BADGES[(f["id"], i)])))
        flows.append(dict(id=f["id"], name=f["name"], short=f["short"], tagline=f["tagline"], color=f"var(--az-{FLOWCOL[f['id']]})", steps=steps))
    segs = {k: list(v["ends"]) for k, v in SEGS.items()}
    js = ("// Generated by the architecture builder (model + build). Do not edit by hand.\n"
          f"export const TOUR = {json.dumps(FLOW_ORDER)};\n"
          f"export const SEGS = {json.dumps(segs, separators=(',', ':'))};\n"
          f"export const TIMING = {json.dumps(dict(pxPerS=PX_PER_S, minHop=MIN_HOP, burstGap=BURST_GAP, dwell=DWELL, emptyDwell=EMPTY_DWELL, flowGap=FLOW_GAP))};\n"
          f"export const FLOWS = {json.dumps(flows, ensure_ascii=False, indent=1)};\n")
    return js

def palette_css():
    lv = ";".join(f"--az-{k}:{v}" for k, v in LIGHT.items())
    dv = ";".join(f"--az-{k}:{v}" for k, v in DARK.items())
    return (f":root{{{lv}}}\n:root[data-theme=\"dark\"]{{{dv}}}\n@media (prefers-color-scheme: dark){{:root[data-theme=\"auto\"]{{{dv}}}}}\n"
            + css("inline") + "".join(f".lg-{f}{{fill:var(--az-{FLOWCOL[f]})}}" for f in FLOW_ORDER) + ".lg-bullet{fill:var(--az-muted)}\n")

def replace_between(path, start, end, content):
    s = open(path, encoding="utf-8").read()
    i, j = s.find(start), s.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f"markers missing in {path}")
    open(path, "w", encoding="utf-8").write(s[:i + len(start)] + content + s[j:])

if __name__ == "__main__":
    out = {}
    s, _ = svg("static", LIGHT); out["architecture.svg"] = s
    s, total = svg("anim", LIGHT); out["architecture-animated.svg"] = s
    s, _ = svg("anim", DARK); out["architecture-animated-dark.svg"] = s
    for name, data in out.items():
        open(REPO + "/docs/assets/img/" + name, "w", encoding="utf-8").write(data)
    replace_between(REPO + "/docs/index.html", "<!-- arch:svg -->", "<!-- /arch:svg -->", svg("inline"))
    open(REPO + "/docs/assets/js/arch-flows.js", "w", encoding="utf-8").write(flows_js())
    replace_between(REPO + "/docs/assets/css/app.css", "/* arch:css */", "/* /arch:css */", "\n" + palette_css())
    if "--preview" in sys.argv:                       # Liberation-font copies for a local PNG check
        pdir = sys.argv[sys.argv.index("--preview") + 1]
        os.makedirs(pdir, exist_ok=True)
        for name, pal in (("static", LIGHT), ("static-dark", DARK)):
            s, _ = svg("static", pal, preview=True)
            open(os.path.join(pdir, name + ".svg"), "w", encoding="utf-8").write(s)
    print(json.dumps({k: len(v) for k, v in out.items()}), f"README loop {total:.1f}s")
    for w in WARN:
        print("WARN", w)
