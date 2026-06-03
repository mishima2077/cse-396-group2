// Run recorder + dead-reckoning engine + semantic event detection
//
// Dead-reckoning constants derived from autonomy.py / config.py values.
// FWD_CMS is a placeholder — measure on rig at each speed and update.

const DR_TURN_RATE_DPS = {   // deg/s at PWM speed
  50:  90 / (6120 / 1000),   // ≈ 14.7  (align + scan speed)
  200: 90 / (1530 / 1000),   // ≈ 58.8  (idle/roam speed)
};
const DR_FWD_CMS = {          // cm/s — PLACEHOLDER, calibrate on rig
  200: 20,
  50:  5,
};

// ── Recorder state ──────────────────────────────────────────────────────────

let RUN = makeRun();
let runTimerInterval = null;
let runDurationMs    = 0;

function makeRun() {
  return {
    active: false,
    t0: 0,
    events:   [],   // raw event log (for JSON export)
    markers:  [],   // semantic markers {type,label,x,y,t_s}
    timeline: [],   // human-readable event list {t_s,msg,cls}
    dr: {
      x: 0, y: 0,   // cm (x=east, y=north)
      hdg: 0,        // degrees CW from north (0=up)
      cmd: null,     // current motion cmd or null
      speed: 0,
      cmdAt: 0,      // performance.now() when cmd started
      path: [{x:0, y:0}],
    },
    prevFireDet: false,
    stats: { fires: 0, extinguished: 0, obstacles: 0, scans: 0, distCm: 0 },
  };
}

// ── Dead-reckoning ──────────────────────────────────────────────────────────

function drFinalize(nowMs) {
  const dr = RUN.dr;
  if (!dr.cmd) return;
  const dt = (nowMs - dr.cmdAt) / 1000;
  const c = dr.cmd, s = dr.speed;
  if (c === 'FWD' || c === 'REV') {
    const sign = c === 'FWD' ? 1 : -1;
    const dist = (DR_FWD_CMS[s] || 15) * dt * sign;
    const rad  = dr.hdg * Math.PI / 180;
    dr.x += dist * Math.sin(rad);
    dr.y += dist * Math.cos(rad);
    RUN.stats.distCm += Math.abs(dist);
    dr.path.push({ x: dr.x, y: dr.y });
  } else if (c === 'TURN_R') {
    const rate = DR_TURN_RATE_DPS[s] || 30;
    dr.hdg = (dr.hdg + rate * dt + 360) % 360;
  } else if (c === 'TURN_L') {
    const rate = DR_TURN_RATE_DPS[s] || 30;
    dr.hdg = (dr.hdg - rate * dt + 360) % 360;
  }
}

function drOnCmd(cmd, speed, nowMs) {
  drFinalize(nowMs);
  const moving = ['FWD', 'REV', 'TURN_R', 'TURN_L'];
  RUN.dr.cmd   = moving.includes(cmd) ? cmd : null;
  RUN.dr.speed = speed || 200;
  RUN.dr.cmdAt = nowMs;
}

// ── Marker / timeline helpers ───────────────────────────────────────────────

function addMarker(type, label) {
  RUN.markers.push({
    type, label,
    x: RUN.dr.x, y: RUN.dr.y,
    t_s: (performance.now() - RUN.t0) / 1000,
  });
}

function addTimeline(msg, cls) {
  RUN.timeline.push({ t_s: (performance.now() - RUN.t0) / 1000, msg, cls });
}

// ── Run lifecycle ───────────────────────────────────────────────────────────

function toggleRun() {
  if (RUN.active) endRun(); else startRun();
}

function startRun() {
  RUN = makeRun();
  RUN.active   = true;
  RUN.t0       = performance.now();
  RUN.dr.cmdAt = RUN.t0;
  RUN.markers.push({ type:'start', label:'▶ Run started', x:0, y:0, t_s:0 });
  RUN.timeline.push({ t_s:0, msg:'▶ Run started — origin at center, heading north', cls:'info' });

  const btn = document.getElementById('run-btn');
  const tmr = document.getElementById('run-timer');
  btn.textContent = '■ End Run'; btn.classList.add('active');
  tmr.style.display = ''; tmr.textContent = '●REC 0:00';

  runTimerInterval = setInterval(() => {
    runDurationMs = performance.now() - RUN.t0;
    tmr.textContent = '●REC ' + fmtDur(runDurationMs / 1000);
  }, 1000);
}

function endRun() {
  drFinalize(performance.now());
  RUN.active = false;
  clearInterval(runTimerInterval);

  const btn = document.getElementById('run-btn');
  const tmr = document.getElementById('run-timer');
  btn.textContent = '▶ Start Run'; btn.classList.remove('active');
  tmr.style.display = 'none';

  const finalT = (performance.now() - RUN.t0) / 1000;
  RUN.markers.push({ type:'end', label:'■ Run ended', x:RUN.dr.x, y:RUN.dr.y, t_s:finalT });
  RUN.timeline.push({ t_s:finalT, msg:'■ Run ended', cls:'info' });
  runDurationMs = finalT * 1000;

  showOverlay();   // defined in map.js
}

function newRun() {
  closeOverlay();
  setTimeout(startRun, 200);
}

// ── Socket hooks for recording ──────────────────────────────────────────────

socket.on('sensor', (data) => {
  if (!RUN.active) return;
  RUN.events.push({ type:'sensor', t_s:(performance.now()-RUN.t0)/1000, ...data });
});

socket.on('fire_yolo', (data) => {
  if (!RUN.active) return;
  const t_s = (performance.now() - RUN.t0) / 1000;
  RUN.events.push({ type:'fire_yolo', t_s, ...data });
  if (data.detected && !RUN.prevFireDet) {
    RUN.stats.fires++;
    addMarker('fire', `🔥 Fire detected conf=${data.conf} t+${t_s.toFixed(0)}s`);
    addTimeline(`🔥 Fire detected — conf=${data.conf} dev=${data.deviation}px`, 'fire');
  } else if (!data.detected && RUN.prevFireDet) {
    addTimeline('Fire lost — no detection', 'warn');
  }
  RUN.prevFireDet = data.detected;
});

socket.on('log', (data) => {
  if (!RUN.active) return;
  const nowMs = performance.now();
  const t_s   = (nowMs - RUN.t0) / 1000;
  RUN.events.push({ type:'log', t_s, msg:data.msg, cls:data.cls });

  if (data.cls === 'cmd') {
    const m = data.msg.match(/➤ SERIAL → (\w+)(?:,(\d+))?/);
    if (m) {
      const c = m[1], s = m[2] ? parseInt(m[2]) : 0;
      drOnCmd(c, s, nowMs);
      if (c === 'PUMP_ON') {
        RUN.stats.extinguished++;
        addMarker('extinguish', `💧 Pump ON — extinguished t+${t_s.toFixed(0)}s`);
        addTimeline('💧 Pump ON — fire suppression', 'pump');
      } else if (c === 'PUMP_OFF') {
        addTimeline('🚫 Pump OFF', 'info');
      } else {
        addTimeline(`➤ ${c}${s ? ','+s : ''}`, 'cmd');
      }
    }
  } else {
    const msg = data.msg;
    if (msg.includes('⛔') || (msg.toLowerCase().includes('obstacle') && msg.includes('front='))) {
      RUN.stats.obstacles++;
      addMarker('obstacle', `⛔ Obstacle t+${t_s.toFixed(0)}s`);
      addTimeline(msg, 'warn');
    } else if (msg.includes('360°') && (msg.includes('search') || msg.includes('scan') || msg.includes('re-scan'))) {
      RUN.stats.scans++;
      addMarker('scan', `🔍 360° scan t+${t_s.toFixed(0)}s`);
      addTimeline(msg, 'info');
    } else if (msg.includes('ARRIVED')) {
      addMarker('arrived', `🎯 Arrived at fire t+${t_s.toFixed(0)}s`);
      addTimeline(msg, 'info');
    } else if (msg.includes('free-roam')) {
      addTimeline(msg, 'info');
    }
  }
});
