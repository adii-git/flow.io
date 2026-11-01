// Shared contour-field engine: marching squares over a scalar field bent by "wells". Used by the landing page and live execution.
export type Well = { id: string; label: string; x: number; y: number }; // x,y normalised 0..1
export type Colors = { field: string; panel: string; ink: string; line: string; acc: string; font: string };
type Token = { w: string; x: number; y: number; tx: number; ty: number; a: number };

export function readColors(): Colors {
  const s = getComputedStyle(document.documentElement);
  const v = (k: string) => s.getPropertyValue(k).trim();
  return { field: v("--field"), panel: v("--panel"), ink: v("--ink"), line: v("--line"), acc: v("--acc"), font: getComputedStyle(document.body).fontFamily };
}

export function createField(canvas: HTMLCanvasElement, init: { wells: Well[]; reduced: boolean; labels?: boolean }) {
  const cx = canvas.getContext("2d")!;
  let wells = init.wells, reduced = init.reduced, w = 0, h = 0, dpr = 1, step = 14, cols = 0, rows = 0, F = new Float32Array(0);
  let depth: Record<string, number> = {}, target: Record<string, number> = {};
  let route: string[] = [], upto = 0, uptoTarget = 0, tokens: Token[] = [], colors = readColors();
  const mouse = { x: -999, y: -999, on: false };
  let raf = 0, last = 0, destroyed = false;
  const pos = () => wells.map((o) => ({ x: o.x * w, y: o.y * h }));
  let px = pos();

  function resize() {
    const r = canvas.getBoundingClientRect(), small = r.width < 640;
    dpr = small ? 1 : Math.min(window.devicePixelRatio || 1, 1.5);
    w = r.width; h = r.height; canvas.width = w * dpr; canvas.height = h * dpr;
    step = small ? 22 : 14; cols = Math.ceil(w / step) + 1; rows = Math.ceil(h / step) + 1; F = new Float32Array(cols * rows);
    px = pos(); colors = readColors(); draw(performance.now());
  }
  function sample(x: number, y: number, t: number) {
    let v = 0.55 + 0.16 * (Math.sin(x * 0.004 + t * 0.00018) + Math.sin(y * 0.005 - t * 0.00015) + Math.sin((x + y) * 0.003 + t * 0.0001));
    const s = Math.max(h < 300 ? 70 : 110, Math.min(w, h) * 0.2);
    for (let i = 0; i < wells.length; i++) {
      const dx = x - px[i].x, dy = y - px[i].y;
      v += (depth[wells[i].id] ?? 0.5) * Math.exp(-(dx * dx + dy * dy) / (2 * s * s));
    }
    if (mouse.on) { const mx = x - mouse.x, my = y - mouse.y; v += 0.35 * Math.exp(-(mx * mx + my * my) / (2 * 80 * 80)); }
    return v;
  }
  function draw(t: number) {
    if (!w) return;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, w, h);
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) F[j * cols + i] = sample(i * step, j * step, reduced ? 0 : t);
    const dL = 0.1, minor = new Path2D(), major = new Path2D();
    for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
      const a = F[j * cols + i], b = F[j * cols + i + 1], c = F[(j + 1) * cols + i + 1], d = F[(j + 1) * cols + i];
      const mn = Math.min(a, b, c, d), mx = Math.max(a, b, c, d);
      for (let k = Math.ceil(mn / dL); k <= Math.floor(mx / dL); k++) {
        const L = k * dL, idx = (a > L ? 8 : 0) | (b > L ? 4 : 0) | (c > L ? 2 : 0) | (d > L ? 1 : 0);
        if (idx === 0 || idx === 15) continue;
        const x0 = i * step, y0 = j * step;
        const T = [x0 + (step * (L - a)) / (b - a), y0], R = [x0 + step, y0 + (step * (L - b)) / (c - b)];
        const B = [x0 + (step * (L - d)) / (c - d), y0 + step], Lf = [x0, y0 + (step * (L - a)) / (d - a)];
        const p = k % 5 === 0 ? major : minor;
        let S: number[][][];
        switch (idx) {
          case 1: case 14: S = [[Lf, B]]; break; case 2: case 13: S = [[B, R]]; break; case 3: case 12: S = [[Lf, R]]; break;
          case 4: case 11: S = [[T, R]]; break; case 5: S = [[T, R], [Lf, B]]; break; case 6: case 9: S = [[T, B]]; break;
          case 7: case 8: S = [[T, Lf]]; break; default: S = [[T, Lf], [B, R]];
        }
        for (const s of S) { p.moveTo(s[0][0], s[0][1]); p.lineTo(s[1][0], s[1][1]); }
      }
    }
    cx.lineJoin = "round"; cx.strokeStyle = colors.field;
    cx.globalAlpha = 0.35; cx.lineWidth = 1; cx.stroke(minor); cx.globalAlpha = 0.7; cx.lineWidth = 1.4; cx.stroke(major); cx.globalAlpha = 1;
    const ids = wells.map((o) => o.id), pts = route.map((id) => px[ids.indexOf(id)]).filter(Boolean);
    if (pts.length > 1) {
      const seg = Math.min(Math.floor(upto), pts.length - 1), fr = upto - seg;
      cx.strokeStyle = colors.acc; cx.lineWidth = 6; cx.lineCap = "round"; cx.beginPath(); cx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i <= seg; i++) cx.lineTo(pts[i].x, pts[i].y);
      let hx = pts[seg].x, hy = pts[seg].y;
      if (seg < pts.length - 1) { hx += (pts[seg + 1].x - hx) * fr; hy += (pts[seg + 1].y - hy) * fr; cx.lineTo(hx, hy); }
      cx.stroke();
      if (uptoTarget < pts.length - 1 || upto < uptoTarget) { cx.fillStyle = colors.ink; cx.beginPath(); cx.arc(hx, hy, 7, 0, 7); cx.fill(); cx.strokeStyle = colors.acc; cx.lineWidth = 3; cx.stroke(); }
    }
    if (init.labels !== false) {
      cx.font = `600 12px ${colors.font}`; cx.textBaseline = "middle";
      wells.forEach((o, i) => {
        const ri = route.indexOf(o.id), act = ri > -1 && ri <= Math.floor(upto + 0.001), lit = (target[o.id] ?? 0.5) > 0.6 || act;
        const tw = cx.measureText(o.label).width + 18, X = Math.min(Math.max(px[i].x - tw / 2, 6), w - tw - 6), Y = px[i].y - 11;
        cx.fillStyle = act ? colors.acc : colors.panel; cx.strokeStyle = lit ? colors.ink : colors.line; cx.lineWidth = lit ? 1.5 : 1;
        cx.beginPath(); cx.roundRect(X, Y, tw, 22, [11, 11, 11, 3]); cx.fill(); cx.stroke();
        cx.fillStyle = act ? "#1A1200" : colors.ink; cx.fillText(o.label, X + 9, px[i].y);
      });
    }
    for (const o of tokens) {
      cx.globalAlpha = o.a; cx.font = `500 12px ${colors.font}`; const ww = cx.measureText(o.w).width + 12;
      cx.fillStyle = colors.panel; cx.strokeStyle = colors.acc; cx.lineWidth = 1.5; cx.beginPath(); cx.roundRect(o.x - ww / 2, o.y - 9, ww, 18, 9); cx.fill(); cx.stroke();
      cx.fillStyle = colors.ink; cx.fillText(o.w, o.x - ww / 2 + 6, o.y);
    }
    cx.globalAlpha = 1;
  }
  function tick(t: number) {
    for (const o of wells) { const g = (target[o.id] ?? 0.5) - (depth[o.id] ?? 0.5); depth[o.id] = (depth[o.id] ?? 0.5) + g * (reduced ? 1 : 0.06); }
    upto += (uptoTarget - upto) * (reduced ? 1 : 0.04); if (Math.abs(uptoTarget - upto) < 0.01) upto = uptoTarget;
    tokens = tokens.filter((o) => { o.x += (o.tx - o.x) * 0.045; o.y += (o.ty - o.y) * 0.045; if (Math.hypot(o.tx - o.x, o.ty - o.y) < 14) o.a -= 0.04; return o.a > 0; });
    draw(t);
  }
  function loop(t: number) { if (destroyed) return; raf = requestAnimationFrame(loop); if (t - last >= 16) { last = t; tick(t); } }
  function start() { cancelAnimationFrame(raf); if (!reduced && !document.hidden) raf = requestAnimationFrame(loop); else tick(performance.now()); }
  const onVis = () => start();
  const ro = new ResizeObserver(resize); ro.observe(canvas);
  document.addEventListener("visibilitychange", onVis);
  resize(); start();
  return {
    setWells(ws: Well[]) { wells = ws; px = pos(); draw(performance.now()); },
    setTarget(id: string, d: number) { target[id] = d; if (reduced) tick(performance.now()); },
    setRoute(ids: string[], progress: number) { route = ids; uptoTarget = progress; if (reduced) tick(performance.now()); },
    addToken(word: string, x: number, y: number, wellId: string) {
      const i = wells.findIndex((o) => o.id === wellId); if (reduced || i < 0) return;
      tokens.push({ w: word, x, y, tx: px[i].x, ty: px[i].y, a: 1 });
    },
    setMouse(x: number, y: number, on: boolean) { const r = canvas.getBoundingClientRect(); mouse.x = x - r.left; mouse.y = y - r.top; mouse.on = on; if (reduced) draw(0); },
    setReduced(r: boolean) { reduced = r; start(); },
    refreshColors() { colors = readColors(); draw(performance.now()); },
    destroy() { destroyed = true; cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener("visibilitychange", onVis); },
  };
}
export type Field = ReturnType<typeof createField>;
