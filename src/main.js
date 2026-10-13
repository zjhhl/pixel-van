'use strict';

/* ============================================================
 * 像素方块小车队 — HTML5 Canvas 竖屏游戏
 * 玩法：点击小车派去装货，方块从像素画飞入车斗，搬空整幅画过关
 * ============================================================ */

/* ---------- 常量 ---------- */
const DESIGN_W = 720;
const DESIGN_H = 1280;

const PALETTE = {
  white: '#FFFFFF', black: '#1A1A1A', gray: '#8A8A8A', red: '#E23B3B',
  orange: '#F28C28', yellow: '#F7D13E', green: '#3FA34D', darkgreen: '#1F6E43',
  lightblue: '#7EC8F0', blue: '#2F80ED', purple: '#8E5BD9', pink: '#F06AA8',
  brown: '#8C5A2B', beige: '#EAD9B8',
};
// 有实拍小车的 9 色，其余颜色用白车染色
const VAN_REAL = ['white', 'black', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink'];

const SLOT_COUNT = 5;
const VAN_W = 100;
const VAN_H = 125;
const DROP_INTERVAL = 0.06;   // 卸一颗方块的间隔（秒）
const CUBE_FLIGHT = 0.45;     // 方块飞行时长

// URL 调试参数
const QS = new URLSearchParams(location.search);
const DEBUG_AUTO = QS.get('auto') === '1';

/* ---------- 资源清单 ---------- */
const MANIFEST = {
  cube: 'assets/cube/cube.png',
  ground: 'assets/bg/ground.png',
  slot: 'assets/bg/slot.png',
  tree: 'assets/bg/tree.png',
  tree2: 'assets/bg/tree2.png',
  sign: 'assets/bg/sign.png',
  btn_start: 'assets/ui/btn_start.png',
  btn_next: 'assets/ui/btn_next.png',
  btn_retry: 'assets/ui/btn_retry.png',
  banner_win: 'assets/ui/banner_win.png',
  panel: 'assets/ui/panel.png',
};
for (const c of VAN_REAL) {
  MANIFEST['van_' + c] = `assets/vans/van_${c}_closed.png`;
  MANIFEST['van_' + c + '_open'] = `assets/vans/van_${c}_open.png`;
}
const SFX_NAMES = ['click', 'drop', 'drive', 'win'];

const IMG = {};
const SFX = {};
let loadPending = 0;

function loadAll(cb) {
  const names = Object.keys(MANIFEST);
  loadPending = names.length + SFX_NAMES.length;
  const done = () => { loadPending--; if (loadPending === 0) cb(); };
  for (const n of names) {
    const im = new Image();
    im.onload = done;
    im.onerror = () => { console.error('missing asset:', MANIFEST[n]); done(); };
    im.src = MANIFEST[n];
    IMG[n] = im;
  }
  for (const n of SFX_NAMES) {
    const a = new Audio(`assets/sfx/${n}.mp3`);
    a.addEventListener('canplaythrough', done, { once: true });
    a.addEventListener('error', done, { once: true });
    SFX[n] = a;
  }
}

let lastDropSfx = 0;
function playSfx(name) {
  try {
    if (G.muted) return;
    const a = SFX[name];
    if (!a) return;
    if (name === 'drop') {
      const now = performance.now();
      if (now - lastDropSfx < 160) return; // 高频节流：落块声别连成背景噪音
      lastDropSfx = now;
      a.volume = 0.3;
    } else if (name === 'drive') {
      a.volume = 0.45;
    } else {
      a.volume = 1;
    }
    a.currentTime = 0;
    a.play().catch(() => {});
  } catch (e) { /* 忽略 */ }
}

/* ---------- 染色工具（白模 → 目标色） ---------- */
const tintCache = new Map();

function tinted(key, img, hex) {
  const id = key + hex;
  if (tintCache.has(id)) return tintCache.get(id);
  const cv = document.createElement('canvas');
  cv.width = img.width;
  cv.height = img.height;
  const g = cv.getContext('2d');
  g.drawImage(img, 0, 0);
  g.globalCompositeOperation = 'source-atop';
  g.globalAlpha = 0.78;
  g.fillStyle = hex;
  g.fillRect(0, 0, cv.width, cv.height);
  tintCache.set(id, cv);
  return cv;
}

function isDark(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) < 128;
}

/* 颜色明暗调整（k>1 变亮，k<1 变暗） */
function shade(hex, k) {
  const f = v => Math.max(0, Math.min(255, Math.round(v * k)));
  const r = f(parseInt(hex.slice(1, 3), 16));
  const g = f(parseInt(hex.slice(3, 5), 16));
  const b = f(parseInt(hex.slice(5, 7), 16));
  return `rgb(${r},${g},${b})`;
}

/* 2.5D 立体小方块人（cx=水平中心，footY=脚底，s=整体尺寸）
   runPhase=null 静态站立；数字=跑步相位（腿摆动+身体颠步） */
function drawCubeGuy(g, cx, footY, s, color, runPhase) {
  const hex = PALETTE[color];
  const lite = shade(hex, 1.4);
  const dark = shade(hex, 0.62);
  const w = s * 0.72;                       // 身体宽
  const h = s * 0.66;                       // 身体高
  const bx = cx - w / 2;
  const by = footY - s * 0.82;              // 身体顶

  // 腿（先画，在身体后面露出下半截）
  const legH = s * 0.2;
  const legW = s * 0.14;
  if (runPhase === null) {
    g.fillStyle = dark;
    roundRect(g, cx - w * 0.32, footY - legH, legW, legH, legW * 0.4); g.fill();
    roundRect(g, cx + w * 0.18, footY - legH, legW, legH, legW * 0.4); g.fill();
  } else {
    const sw = Math.sin(runPhase) * s * 0.16;
    g.fillStyle = dark;
    roundRect(g, cx - w * 0.32 + sw, footY - legH, legW, legH, legW * 0.4); g.fill();
    roundRect(g, cx + w * 0.18 - sw, footY - legH, legW, legH, legW * 0.4); g.fill();
  }

  // 右侧暗面
  g.fillStyle = dark;
  g.beginPath();
  g.moveTo(bx + w, by + h * 0.18);
  g.lineTo(bx + w + w * 0.18, by + h * 0.02);
  g.lineTo(bx + w + w * 0.18, by + h * 0.86);
  g.lineTo(bx + w, by + h * 1.0);
  g.closePath();
  g.fill();
  // 顶面亮面
  g.fillStyle = lite;
  g.beginPath();
  g.moveTo(bx, by + h * 0.18);
  g.lineTo(bx + w, by + h * 0.18);
  g.lineTo(bx + w + w * 0.18, by + h * 0.02);
  g.lineTo(bx + w * 0.18, by + h * 0.02);
  g.closePath();
  g.fill();
  // 正面
  g.fillStyle = hex;
  roundRect(g, bx, by, w, h, s * 0.08);
  g.fill();

  // 眼睛（白底黑瞳）
  const ey = by + h * 0.42;
  for (const ex of [cx - w * 0.24, cx + w * 0.2]) {
    g.fillStyle = '#FFFFFF';
    g.beginPath();
    g.arc(ex, ey, s * 0.085, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = '#1A1A1A';
    g.beginPath();
    g.arc(ex + s * 0.015, ey + s * 0.02, s * 0.045, 0, Math.PI * 2);
    g.fill();
  }
  // 嘴（小弧线）
  g.strokeStyle = '#1A1A1A';
  g.lineWidth = Math.max(1, s * 0.03);
  g.beginPath();
  g.arc(cx - w * 0.02, by + h * 0.6, w * 0.14, 0.15 * Math.PI, 0.85 * Math.PI);
  g.stroke();

  // 跑步时的身体颠步由调用方处理（y 偏移）
}

/* 预渲染的静止小人贴图（画中格子用，避免每帧程序绘制上千个） */
const guyCache = new Map();
function cubeGuySprite(color) {
  if (guyCache.has(color)) return guyCache.get(color);
  const s = 96;
  const cv2 = document.createElement('canvas');
  cv2.width = s;
  cv2.height = s;
  drawCubeGuy(cv2.getContext('2d'), s / 2, s * 0.96, s, color, null);
  guyCache.set(color, cv2);
  return cv2;
}

function vanSprite(color, open) {
  const suffix = open ? '_open' : '';
  if (VAN_REAL.includes(color)) return IMG['van_' + color + suffix];
  return tinted('van' + suffix, IMG['van_white' + suffix], PALETTE[color]);
}

function cubeSprite(color) {
  return cubeGuySprite(color);
}

/* ---------- 游戏状态 ---------- */
const G = {
  screen: 'loading',   // loading | home | game | win
  level: parseInt(localStorage.getItem('pixelvan_level') || '1', 10),
  lw: 0, lh: 0,        // 关卡格数
  cell: 20,
  picX: 0, picY: 90, picW: 0, picH: 0,
  grid: null,          // 每格：颜色名=还是画里的方块 或 null=已搬走
  total: 0, removed: 0,
  pickableByColor: null, // 颜色 -> 当前有路可走的格子列表
  texts: [],           // 飘字提示
  lanes: [[], [], [], [], []], // 车队：5 列纵队，列首（index 0）最靠近装货位、可出车
  slots: new Array(SLOT_COUNT).fill(null),
  active: [],          // 派出卸货中的车
  cubes: [],           // 飞行中的方块
  pops: [],            // 落格特效
  winTimer: 0,
  autoTimer: 0,
  autoLane: 0,         // 调试轮换派车用的列指针
  muted: false,        // 静音开关
};

/* ---------- 关卡装载 ---------- */
function loadLevel(n) {
  G.level = n;
  const L = LEVELS[(n - 1) % LEVELS.length];
  G.lw = L.w;
  G.lh = L.h;
  G.cell = Math.floor(Math.min((DESIGN_W - 160) / L.w, 620 / L.h));
  G.picW = G.cell * L.w;
  G.picH = G.cell * L.h;
  G.picX = (DESIGN_W - G.picW) / 2;
  G.picY = 90;

  G.grid = new Array(L.w * L.h);
  for (let i = 0; i < L.cells.length; i++) {
    G.grid[i] = L.colors[L.cells.charCodeAt(i) - 97];
  }
  G.total = L.cells.length;
  G.removed = 0;
  G.texts = [];

  buildBaseLayer();
  const fleet = genFleet(L.counts);
  // 保底：把一辆能装到货（颜色在画底部可见）的车排到首位
  const pickColors = new Set();
  for (let x = 0; x < L.w; x++) {
    pickColors.add(G.grid[(L.h - 1) * L.w + x]);        // 底行
  }
  const qi = fleet.findIndex(v => pickColors.has(v.color));
  if (qi > 0) [fleet[0], fleet[qi]] = [fleet[qi], fleet[0]];
  // 车队按 5 列纵队排布
  G.lanes = [[], [], [], [], []];
  fleet.forEach((v, i) => {
    v.lane = i % SLOT_COUNT;
    G.lanes[v.lane].push(v);
  });
  layoutLanes(true);
  G.slots = new Array(SLOT_COUNT).fill(null);
  G.active = [];
  G.cubes = [];
  G.pops = [];
  G.winTimer = 0;
  rebuildPickable();
  G.screen = 'game';
}

/* 大色块拆成载货 5~30 的多辆车 */
function genFleet(counts) {
  const vans = [];
  for (const [color, n] of Object.entries(counts)) {
    let left = n;
    while (left > 0) {
      let k = Math.min(left, 10 + Math.floor(Math.random() * 20));
      if (left - k > 0 && left - k < 5) k = left - 5; // 避免剩下一辆 <5 的怪车
      if (k < 1) k = 1;
      vans.push(makeVan(color, k));
      left -= k;
    }
  }
  // 洗牌
  for (let i = vans.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [vans[i], vans[j]] = [vans[j], vans[i]];
  }
  return vans;
}

function makeVan(color, cargo) {
  return {
    color, cargo,
    state: 'queue',      // queue（列队中） | drive（去装货位） | unload（装货） | leave（离场）
    slotLane: -1,        // 占用的装货位编号（-1=未占）
    x: 0, y: 0,
    move: null,          // {fx,fy,tx,ty,t,dur,done}
    dropTimer: 0.3,
    closeTimer: 0,
    slotIdx: -1,
    pending: 0,          // 还在跑向这辆车的小人数
  };
}

/* ---------- 车位与队列布局 ---------- */
function slotPos(i) {
  const gap = 12;
  const w = VAN_W + 8;
  const x0 = (DESIGN_W - (SLOT_COUNT * w + (SLOT_COUNT - 1) * gap)) / 2;
  return { x: x0 + i * (w + gap) + w / 2, y: 860 };
}

function lanePos(lane, k) {
  // k=0 列首（最靠近装货位），往后排往下延伸
  return { x: slotPos(lane).x, y: 1030 + k * 142 };
}

function layoutLanes(instant) {
  G.lanes.forEach((lane, c) => {
    lane.forEach((v, k) => {
      const p = lanePos(c, k);
      if (instant) { v.x = p.x; v.y = p.y; v.move = null; }
      else moveVan(v, p.x, p.y, 0.35);
    });
  });
}

function moveVan(v, tx, ty, dur) {
  if (Math.abs(v.x - tx) < 1 && Math.abs(v.y - ty) < 1) { v.move = null; return; }
  v.move = { fx: v.x, fy: v.y, tx, ty, t: 0, dur: Math.max(dur, 0.01) };
}

/* ---------- 派车 ---------- */
function dbgLog(s) {
  if (!G.dbgLog) G.dbgLog = [];
  if (G.dbgLog.length < 25) G.dbgLog.push(s);
}

function dispatch(v) {
  G.dbg = G.dbg || { calls: 0, rej: 0 };
  G.dbg.calls++;
  dbgLog(`disp ${v.color} state=${v.state}`);
  // 只能派各列列首的车；装货位任选一个空的（一框一车）
  const lane = G.lanes[v.lane];
  if (!lane || lane[0] !== v) {
    G.dbg.rej++;
    return;
  }
  const c = freeSlot();
  if (c < 0) {
    G.dbg.rej++;
    return;
  }
  lane.shift();
  layoutLanes(false);
  v.slotLane = c;
  v.state = 'drive';
  G.active.push(v);
  const p = slotPos(c);
  v.unloadX = p.x;
  moveVan(v, p.x, p.y, 0.6);
  playSfx('drive');
}

/* ---------- 装车（消除从底部开始：与底部连通的空格是通道，挨着通道的方块可取） ---------- */
/* 重算当前所有可取格（按颜色分组），在方块被取走后调用。
   洪泛：从底行的空格出发四连通扩散，标记所有与底部连通的空格；
   方块只要四邻中有一个这样的空格（或自己就在底行），就「有通道到最底部」可上车 */
function rebuildPickable() {
  const reach = new Uint8Array(G.lw * G.lh);
  const stack = [];
  for (let x = 0; x < G.lw; x++) {
    const i = (G.lh - 1) * G.lw + x;
    if (G.grid[i] === null) { reach[i] = 1; stack.push(i); }
  }
  while (stack.length) {
    const i = stack.pop();
    const x = i % G.lw;
    const y = (i / G.lw) | 0;
    const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    for (const [dx, dy] of nb) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || nx >= G.lw || ny < 0 || ny >= G.lh) continue;
      const ni = ny * G.lw + nx;
      if (!reach[ni] && G.grid[ni] === null) { reach[ni] = 1; stack.push(ni); }
    }
  }
  G.pickableByColor = {};
  for (let y = 0; y < G.lh; y++) {
    for (let x = 0; x < G.lw; x++) {
      const i = y * G.lw + x;
      const c = G.grid[i];
      if (c === null) continue;
      let ok = y === G.lh - 1; // 底行直接可取
      if (!ok) {
        const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]];
        for (const [dx, dy] of nb) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || nx >= G.lw || ny < 0 || ny >= G.lh) continue;
          if (reach[ny * G.lw + nx]) { ok = true; break; }
        }
      }
      if (ok) (G.pickableByColor[c] = G.pickableByColor[c] || []).push(i);
    }
  }
}

/* 颜色为 color 的当前可取格 */
function pickableCells(color) {
  return (G.pickableByColor && G.pickableByColor[color]) || [];
}

/* 某个装货位是否已被占用（一框一车） */
function slotOccupied(c) {
  return G.active.some(v => v.slotLane === c && v.state !== 'leave');
}

/* 找一个空闲装货位，没有则 -1 */
function freeSlot() {
  for (let c = 0; c < SLOT_COUNT; c++) {
    if (!slotOccupied(c)) return c;
  }
  return -1;
}

function spawnCube(v) {
  const cells = pickableCells(v.color);
  if (!cells.length) return false; // 该色全被挡住/已搬空
  // 随机挑一颗（错乱上车，不按远近排队）
  const best = cells[Math.floor(Math.random() * cells.length)];
  const gx = best % G.lw;
  const gy = Math.floor(best / G.lw);
  G.grid[best] = null;
  rebuildPickable();
  v.cargo--;
  v.pending = (v.pending || 0) + 1;

  // 跑动小人：跳出格子 → 落到某条跑道 → 跑向车 → 跳进车斗
  const c = {
    color: v.color, van: v,
    sx: G.picX + gx * G.cell + G.cell / 2,
    sy: G.picY + gy * G.cell + G.cell / 2,
    state: 'jump', jumpT: 0, hopT: 0,
    x: 0, y: 0, hx: 0, hy: 0,
    runPhase: Math.random() * 6.28,
    landX: 0, laneY: 0, off: 0, speed: 0, delay: 0,
  };
  c.landX = c.sx + (Math.random() * 2 - 1) * G.cell;
  c.laneY = G.picY + G.picH + 14 + Math.floor(Math.random() * 3) * 20;
  c.speed = 320 + Math.random() * 160;
  c.delay = Math.random() * 0.2;
  c.off = (Math.random() * 2 - 1) * 26;
  G.cubes.push(c);
  return true;
}

function landCube(c) {
  G.removed++;
  c.van.pending = Math.max(0, (c.van.pending || 0) - 1);
  G.pops.push({ x: c.x, y: c.y, t: 0, color: c.color });
  playSfx('drop');
  if (G.removed >= G.total) G.winTimer = 1.0;
}

/* 撤回：把框里等货的车开回原列列首（释放装货位，零浪费） */
function retreatVan(v) {
  const i = G.active.indexOf(v);
  if (i < 0 || v.state !== 'unload' || !v.waiting) return;
  G.active.splice(i, 1);
  v.state = 'queue';
  v.waiting = false;
  v.closeTimer = 0;
  G.lanes[v.lane].push(v); // 回列尾重新排队
  v.slotLane = -1;
  const p = lanePos(v.lane, G.lanes[v.lane].length - 1);
  moveVan(v, p.x, p.y, 0.6);
  layoutLanes(false);
  playSfx('click');
}

/* ---------- 败局判定 ---------- */
function checkLose() {
  if (G.screen !== 'game' || G.winTimer > 0) return;
  // 5 个装货位全被等货中的车堵满
  if (G.active.length === SLOT_COUNT && G.active.every(v => v.waiting)) {
    G.failLevel = G.level;
    G.screen = 'lose';
    return;
  }
  // 车队耗尽且没有车在装货（全是等不到货的）而画没搬空
  if (G.lanes.every(l => l.length === 0) && G.active.every(v => v.waiting)) {
    G.failLevel = G.level;
    G.screen = 'lose';
  }
}

/* ---------- 更新 ---------- */
function update(dt) {
  if (G.screen !== 'game') return;

  const all = [...G.active, ...G.lanes.flat()];
  for (const v of all) {
    if (v.move) {
      v.move.t += dt / v.move.dur;
      const t = Math.min(v.move.t, 1);
      const e = 1 - Math.pow(1 - t, 3); // easeOutCubic
      v.x = v.move.fx + (v.move.tx - v.move.fx) * e;
      v.y = v.move.fy + (v.move.ty - v.move.fy) * e;
      if (t >= 1) {
        v.move = null;
        if (v.state === 'drive') { v.state = 'unload'; v.x = v.unloadX; dbgLog(`arrive ${v.color}`); }
        if (v.state === 'leave') v.dead = true;
      }
    }
    if (v.state === 'unload' && !v.move) {
      if (v.closeTimer > 0) {
        v.closeTimer -= dt;
        if (v.closeTimer <= 0) {
          v.state = 'leave';
          moveVan(v, v.x - 120, DESIGN_H + 180, 0.7);
        }
      } else {
        v.dropTimer -= dt;
        if (v.dropTimer <= 0) {
          if (v.cargo > 0) {
            if (spawnCube(v)) {
              v.waiting = false;
              v.dropTimer = DROP_INTERVAL;
            } else {
              // 该色暂时全被挡住：原地等货（别的车拆开后继续装）
              if (!v.waiting) {
                v.waiting = true;
                G.texts.push({ x: v.x, y: v.y - 70, t: 0, str: '等货中…' });
              }
              v.dropTimer = 0.3;
            }
          } else {
            v.waiting = false; // 装满了，只是在等路上的小人
          }
          // 装满且没有小人在路上，才关门离场
          if (v.cargo <= 0 && (v.pending || 0) <= 0 && v.closeTimer <= 0) {
            v.closeTimer = 0.5;
          }
        }
      }
    }
  }
  G.active = G.active.filter(v => !v.dead);

  // 跑动小人状态机
  for (const c of G.cubes) {
    if (c.delay > 0) { c.delay -= dt; continue; }
    if (c.state === 'jump') {
      c.jumpT += dt / 0.26;
      if (c.jumpT >= 1) { c.state = 'run'; c.x = c.landX; c.y = c.laneY; }
    } else if (c.state === 'run') {
      const tx = c.van.x + c.off;
      const ty = c.van.y + 30;
      const dx = tx - c.x;
      const dy = ty - c.y;
      const d = Math.hypot(dx, dy);
      const step = c.speed * dt;
      if (d <= Math.max(step, 12)) {
        c.state = 'hop';
        c.hopT = 0;
        c.hx = c.x;
        c.hy = c.y;
      } else {
        c.x += dx / d * step;
        c.y += dy / d * step;
      }
      c.runPhase += dt * 16;
    } else if (c.state === 'hop') {
      c.hopT += dt / 0.24;
      if (c.hopT >= 1) { c.done = true; landCube(c); }
    }
  }
  G.cubes = G.cubes.filter(c => !c.done);

  for (const p of G.pops) p.t += dt * 3;
  G.pops = G.pops.filter(p => p.t < 1);

  for (const t of G.texts) t.t += dt * 1.1;
  G.texts = G.texts.filter(t => t.t < 1);

  checkLose();

  if (G.winTimer > 0) {
    G.winTimer -= dt;
    if (G.winTimer <= 0) {
      G.screen = 'win';
      G.doneLevel = G.level;
      G.level = G.doneLevel % LEVELS.length + 1; // 通关后循环
      localStorage.setItem('pixelvan_level', String(G.level));
      playSfx('win');
    }
  }

  // 调试自动派车（模拟玩家）：优先派能装到货的列首车；无货可装时
  // 轮换车队（撤回等货车 / 派列首进去等），保持至多 4 框被等货车占用
  if (DEBUG_AUTO) {
    G.autoTimer -= dt;
    if (G.autoTimer <= 0) {
      G.autoTimer = 0.35;
      const heads = G.lanes.map(l => l[0]).filter(Boolean);
      const good = heads.find(v =>
        v.cargo > 0 && pickableCells(v.color).length > 0 && freeSlot() >= 0);
      const allWaiting = G.active.length > 0 && G.active.every(v => v.waiting);
      G.autoDbg = G.autoDbg || { good: 0, rot: 0, ret: 0, none: 0 };
      if (good) {
        G.autoDbg.good++;
        dispatch(good);
      } else if (allWaiting) {
        G.autoDbg.ret++;
        retreatVan(G.active[0]);
      } else if (G.active.length < SLOT_COUNT) {
        // 轮流把各列列首派出去等货，让后面的车顶上来
        // 但等货车最多 3 辆，给「装满待离场」的车留框
        G.autoDbg.rot++;
        const waitingN = G.active.filter(v => v.waiting).length;
        if (waitingN < SLOT_COUNT - 2) {
          let c = G.autoLane % SLOT_COUNT;
          G.autoLane = (G.autoLane + 1) % SLOT_COUNT;
          for (let k = 0; k < SLOT_COUNT && !heads[c]; k++) c = (c + 1) % SLOT_COUNT;
          if (heads[c]) dispatch(heads[c]);
        }
      } else {
        G.autoDbg.none++;
        retreatVan(G.active.find(v => v.waiting));
      }
    }
  }
}

/* ---------- 绘制 ---------- */
const cv = document.getElementById('game');
const ctx = cv.getContext('2d');

// 空格子底图（每关一次）
let baseLayer = null;
function buildBaseLayer() {
  baseLayer = document.createElement('canvas');
  baseLayer.width = G.picW;
  baseLayer.height = G.picH;
  const g = baseLayer.getContext('2d');
  g.fillStyle = 'rgba(0,0,0,0.10)';
  g.strokeStyle = 'rgba(255,255,255,0.35)';
  g.lineWidth = 1;
  for (let y = 0; y < G.lh; y++) {
    for (let x = 0; x < G.lw; x++) {
      roundRect(g, x * G.cell + 1, y * G.cell + 1, G.cell - 2, G.cell - 2, 3);
      g.fill();
      g.stroke();
    }
  }
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function txt(s, x, y, size, fill, strokeW, align) {
  ctx.font = `bold ${size}px "PingFang SC", "Microsoft YaHei", sans-serif`;
  ctx.textAlign = align || 'center';
  ctx.textBaseline = 'middle';
  if (strokeW) {
    ctx.lineWidth = strokeW;
    ctx.strokeStyle = '#1A1A1A';
    ctx.lineJoin = 'round';
    ctx.strokeText(s, x, y);
  }
  ctx.fillStyle = fill;
  ctx.fillText(s, x, y);
}

function drawVan(v) {
  const open = v.state === 'unload' && v.closeTimer <= 0;
  const spr = vanSprite(v.color, open);
  ctx.fillStyle = 'rgba(0,0,0,0.18)';
  ctx.beginPath();
  ctx.ellipse(v.x, v.y + VAN_H * 0.42, VAN_W * 0.42, VAN_H * 0.12, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.drawImage(spr, v.x - VAN_W / 2, v.y - VAN_H / 2, VAN_W, VAN_H);
  if (v.cargo > 0) {
    const dark = isDark(PALETTE[v.color]);
    txt(String(v.cargo), v.x, v.y - 28, 30,
      dark ? '#FFFFFF' : '#1A1A1A', dark ? 4 : 0);
  }
  // 列首、有空装货位且能装到货的车：显示提示箭头
  const isLaneHead = G.lanes[v.lane] && G.lanes[v.lane][0] === v;
  if (isLaneHead && freeSlot() >= 0 && v.cargo > 0 && pickableCells(v.color).length > 0) {
    const bob = Math.sin(performance.now() / 200) * 5;
    ctx.fillStyle = '#F7D13E';
    ctx.strokeStyle = '#1A1A1A';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(v.x - 12, v.y - VAN_H / 2 - 26 + bob);
    ctx.lineTo(v.x + 12, v.y - VAN_H / 2 - 26 + bob);
    ctx.lineTo(v.x, v.y - VAN_H / 2 - 10 + bob);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
}

function drawGame() {
  // 背景
  ctx.drawImage(IMG.ground, 0, 0, DESIGN_W, DESIGN_H);
  ctx.drawImage(IMG.tree, 8, 140, 70, 88);
  ctx.drawImage(IMG.tree2, 642, 200, 70, 88);
  ctx.drawImage(IMG.sign, 16, 430, 64, 100);

  // 顶部进度条
  const ratio = G.removed / G.total;
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  roundRect(ctx, 30, 24, 560, 34, 17);
  ctx.fill();
  if (ratio > 0.02) {
    ctx.fillStyle = '#F7D13E';
    roundRect(ctx, 30, 24, Math.max(34, 560 * ratio), 34, 17);
    ctx.fill();
  }
  txt(`第 ${G.level} 关`, 310, 41, 22, '#FFFFFF', 4);
  txt(`${Math.floor(ratio * 100)}%`, 600, 41, 24, '#FFFFFF', 4);
  drawMuteBtn();

  // 像素画（还在画里的方块；被搬走的只剩空格子）
  ctx.drawImage(baseLayer, G.picX, G.picY);
  for (let i = 0; i < G.grid.length; i++) {
    const c = G.grid[i];
    if (c !== null) {
      const gx = i % G.lw, gy = Math.floor(i / G.lw);
      ctx.drawImage(cubeSprite(c),
        G.picX + gx * G.cell, G.picY + gy * G.cell, G.cell, G.cell);
    }
  }
  // 跑动小人（等待出发 / 跳出 / 奔跑 / 跳上车斗）
  for (const c of G.cubes) drawMovingGuy(c);

  // 落格特效
  for (const p of G.pops) {
    ctx.strokeStyle = `rgba(255,255,255,${0.6 * (1 - p.t)})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(p.x, p.y, G.cell * (0.5 + p.t * 0.9), 0, Math.PI * 2);
    ctx.stroke();
  }

  // 飘字提示
  for (const t of G.texts) {
    ctx.globalAlpha = 1 - t.t;
    txt(t.str, t.x, t.y - 40 * t.t, 26, '#FFFFFF', 5);
    ctx.globalAlpha = 1;
  }

  // 装货中的车
  for (const v of G.active) drawVan(v);
  // 装货位（空框）
  for (let i = 0; i < SLOT_COUNT; i++) {
    const p = slotPos(i);
    ctx.drawImage(IMG.slot, p.x - 58, p.y - 70, 116, 140);
  }
  // 车队：5 列纵队
  for (const v of G.lanes.flat()) drawVan(v);

  // 调试浮层
  if (QS.get('debug') === '1') {
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(0, 60, 720, 190);
    const a0 = G.active[0];
    const info = `act=${G.active.length} cubes=${G.cubes.length} removed=${G.removed} `
      + (a0 ? `v0=${a0.state}(${Math.round(a0.x)},${Math.round(a0.y)})mv=${a0.move ? 1 : 0} cargo=${a0.cargo}` : 'v0=-')
      + ` auto=${DEBUG_AUTO ? 1 : 0} q=${G.lanes.flat().length} total=${G.total}`
      + (G.dbg ? ` disp=${G.dbg.calls}/${G.dbg.rej}` : '')
      + (G.autoDbg ? ` auto[${G.autoDbg.good}/${G.autoDbg.rot}/${G.autoDbg.ret}/${G.autoDbg.none}]` : '')
      + (G.fastErr ? ' ERR=' + G.fastErr.split('\n')[0] : '');
    txt(info, 360, 78, 18, '#0F0');
    txt('L=' + G.lanes.map(l => l.length).join(',') + ' pickColors='
      + Object.keys(G.pickableByColor || {}).join(','), 360, 100, 16, '#0F0');
    if (G.dbgLog) {
      G.dbgLog.slice(0, 6).forEach((s, i) => txt(s, 360, 125 + i * 20, 15, '#0F0'));
    }
  }
}

/* 已搬走的格子从 filledColor 移除（现 grid 值即颜色，无需额外映射） */

/* 绘制一个跑动中的小人（四种状态：站格等出发 / 跳出 / 沿跑道跑 / 跳进车斗） */
function drawMovingGuy(c) {
  const s = G.cell;
  if (c.delay > 0) {
    // 还站在自己的格子里
    drawCubeGuy(ctx, c.sx, c.sy + s * 0.45, s, c.color, null);
    return;
  }
  if (c.state === 'jump') {
    const t = Math.min(c.jumpT, 1);
    const x = c.sx + (c.landX - c.sx) * t;
    const y0 = c.sy + s * 0.45;
    const footY = y0 + (c.laneY - y0) * t - Math.sin(Math.PI * t) * s * 1.7;
    drawCubeGuy(ctx, x, footY, s, c.color, t * 20);
  } else if (c.state === 'run') {
    const bob = Math.abs(Math.sin(c.runPhase)) * s * 0.07;
    drawCubeGuy(ctx, c.x, c.y - bob, s, c.color, c.runPhase);
  } else if (c.state === 'hop') {
    const t = Math.min(c.hopT, 1);
    const x = c.hx + (c.van.x + c.off * 0.4 - c.hx) * t;
    const footY = c.hy + (c.van.y + 10 - c.hy) * t - Math.sin(Math.PI * t) * s * 1.3;
    const sc = 1 - t * 0.55;
    ctx.save();
    ctx.globalAlpha = 1 - t * 0.85;
    ctx.translate(x, footY);
    ctx.scale(sc, sc);
    drawCubeGuy(ctx, 0, 0, s, c.color, null);
    ctx.restore();
    ctx.globalAlpha = 1;
  }
}

/* 右上角静音按钮 */
const BTN_MUTE = { x: 642, y: 14, w: 56, h: 56 };
function drawMuteBtn() {
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.beginPath();
  ctx.arc(BTN_MUTE.x + 28, BTN_MUTE.y + 28, 27, 0, Math.PI * 2);
  ctx.fill();
  txt(G.muted ? '🔇' : '🔊', BTN_MUTE.x + 28, BTN_MUTE.y + 29, 28, '#FFFFFF');
}

function drawLose() {
  drawGame();
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fillRect(0, 0, DESIGN_W, DESIGN_H);
  ctx.drawImage(IMG.panel, 60, 420, 600, 460);
  txt('堵车了！', DESIGN_W / 2, 520, 60, '#E23B3B', 8);
  txt('5 个装货位全被等货的车堵死了', DESIGN_W / 2, 600, 28, '#5A4632');
  ctx.drawImage(IMG.btn_next, BTN_NEXT.x, BTN_NEXT.y + 120, BTN_NEXT.w, BTN_NEXT.h);
  txt('再试一次', BTN_NEXT.x + 200, BTN_NEXT.y + 175, 42, '#FFFFFF', 5);
}

/* ---------- 主界面 / 过关界面 ---------- */
const BTN_START = { x: 210, y: 950, w: 300, h: 96 };
const BTN_NEXT = { x: 160, y: 660, w: 400, h: 110 };
const BTN_RETRY = { x: 260, y: 800, w: 200, h: 100 };

function drawHome() {
  ctx.drawImage(IMG.ground, 0, 0, DESIGN_W, DESIGN_H);
  ctx.drawImage(IMG.tree, 30, 160, 110, 137);
  ctx.drawImage(IMG.tree2, DESIGN_W - 140, 200, 110, 137);
  ctx.drawImage(IMG.sign, 30, 420, 90, 140);

  txt('像素方块小车队', DESIGN_W / 2, 300, 64, '#F7D13E', 10);
  txt('只运露在外面的方块', DESIGN_W / 2, 380, 28, '#FFFFFF', 6);
  txt('车位堵死就输了', DESIGN_W / 2, 425, 28, '#FFFFFF', 6);

  // 方块装饰
  const demo = ['red', 'yellow', 'green', 'blue', 'pink'];
  demo.forEach((c, i) => {
    ctx.drawImage(cubeSprite(c), 260 + i * 44, 480, 40, 40);
  });

  // 小车展示
  const show = ['red', 'blue', 'yellow'];
  show.forEach((c, i) => {
    const spr = vanSprite(c, false);
    ctx.drawImage(spr, 150 + i * 150, 620, 120, 150);
  });

  ctx.drawImage(IMG.btn_start, BTN_START.x, BTN_START.y, BTN_START.w, BTN_START.h);
  txt('开始游戏', BTN_START.x + BTN_START.w / 2, BTN_START.y + BTN_START.h / 2, 40, '#7A4A00');
  txt(`第 ${Math.min(G.level, LEVELS.length)} 关`, DESIGN_W / 2, 1080, 26, '#FFFFFF', 5);
}

function drawWin() {
  drawGame();
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.fillRect(0, 0, DESIGN_W, DESIGN_H);
  ctx.drawImage(IMG.banner_win, 85, 170, 550, 275);
  ctx.drawImage(IMG.panel, 60, 420, 600, 460);
  txt('太棒了！', DESIGN_W / 2, 500, 56, '#F7D13E', 8);
  txt(`第 ${G.doneLevel || 1} 关完成`, DESIGN_W / 2, 580, 30, '#5A4632');
  const last = G.doneLevel >= LEVELS.length;
  ctx.drawImage(IMG.btn_next, BTN_NEXT.x, BTN_NEXT.y, BTN_NEXT.w, BTN_NEXT.h);
  txt(last ? '再来一轮' : '下一关', BTN_NEXT.x + 200, BTN_NEXT.y + 55, 42, '#FFFFFF', 5);
  ctx.drawImage(IMG.btn_retry, BTN_RETRY.x, BTN_RETRY.y, BTN_RETRY.w, BTN_RETRY.h);
  txt('重玩', BTN_RETRY.x + 100, BTN_RETRY.y + 50, 32, '#FFFFFF', 4);
}

/* ---------- 输入 ---------- */
function inRect(px, py, r) {
  return px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h;
}

cv.addEventListener('pointerdown', (e) => {
  const rect = cv.getBoundingClientRect();
  const scale = DESIGN_W / rect.width;
  const px = (e.clientX - rect.left) * scale;
  const py = (e.clientY - rect.top) * scale;

  if (G.screen === 'home') {
    if (inRect(px, py, BTN_START)) {
      playSfx('click');
      loadLevel(Math.min(G.level, LEVELS.length));
    }
    return;
  }
  if (G.screen === 'lose') {
    if (inRect(px, py, { x: BTN_NEXT.x, y: BTN_NEXT.y + 120, w: BTN_NEXT.w, h: BTN_NEXT.h })) {
      playSfx('click');
      loadLevel(G.failLevel || G.level);
    }
    return;
  }
  if (G.screen === 'win') {
    if (inRect(px, py, BTN_NEXT)) {
      playSfx('click');
      loadLevel(Math.min(G.level, LEVELS.length));
    } else if (inRect(px, py, BTN_RETRY)) {
      playSfx('click');
      G.level = Math.max(1, G.level - 1);
      localStorage.setItem('pixelvan_level', String(G.level));
      loadLevel(G.level);
    }
    return;
  }
  if (G.screen !== 'game') return;

  // 静音开关
  if (inRect(px, py, BTN_MUTE)) {
    G.muted = !G.muted;
    return;
  }

  // 点击装货位里等货的车 → 撤回
  for (const v of [...G.active].reverse()) {
    if (v.state === 'unload' && v.waiting
      && Math.abs(px - v.x) < VAN_W / 2 + 6 && Math.abs(py - v.y) < VAN_H / 2 + 6) {
      retreatVan(v);
      return;
    }
  }
  // 点击各列列首的车（后面的车被挡住，不可派）
  const candidates = G.lanes.map(l => l[0]).filter(Boolean).reverse();
  for (const v of candidates) {
    if (Math.abs(px - v.x) < VAN_W / 2 + 6 && Math.abs(py - v.y) < VAN_H / 2 + 6) {
      dispatch(v);
      return;
    }
  }
});

/* ---------- 缩放适配 ---------- */
function fitCanvas() {
  const scale = Math.min(window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H);
  cv.style.width = Math.floor(DESIGN_W * scale) + 'px';
  cv.style.height = Math.floor(DESIGN_H * scale) + 'px';
}
window.addEventListener('resize', fitCanvas);
fitCanvas();

/* ---------- 主循环 ---------- */
let lastT = 0;
function frame(t) {
  const dt = Math.min((t - lastT) / 1000, 0.05);
  lastT = t;
  update(dt);

  if (G.screen === 'loading') {
    ctx.fillStyle = '#2B2B33';
    ctx.fillRect(0, 0, DESIGN_W, DESIGN_H);
    txt('加载中…', DESIGN_W / 2, DESIGN_H / 2, 40, '#FFFFFF');
  } else if (G.screen === 'home') {
    drawHome();
  } else if (G.screen === 'win') {
    drawWin();
  } else if (G.screen === 'lose') {
    drawLose();
  } else {
    drawGame();
  }
  requestAnimationFrame(frame);
}

/* ---------- 启动 ---------- */
loadAll(() => {
  if (QS.get('skiphome') === '1') {
    const lv = parseInt(QS.get('level') || String(G.level), 10);
    loadLevel(Math.min(Math.max(lv, 1), LEVELS.length));
    // 调试：?fast=N 同步快进 N 秒（headless 截图用，rAF 推进不可靠）
    const fast = parseFloat(QS.get('fast') || '0');
    try {
      for (let i = 0; i < fast * 60; i++) update(1 / 60);
    } catch (err) {
      G.fastErr = String(err && err.stack || err);
    }
  } else {
    G.screen = 'home';
  }
});
requestAnimationFrame(frame);
