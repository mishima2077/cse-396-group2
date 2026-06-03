// Socket + live dashboard display (distances, YOLO, flame sensor, log)

const MAX_SENSOR = 340;
const socket = io();

socket.on('connect', () => {
  const b = document.getElementById('conn-badge');
  b.textContent = '● Connected';
  b.classList.add('connected');
  addLog('Connected to rover server', 'info');
});

socket.on('disconnect', () => {
  const b = document.getElementById('conn-badge');
  b.textContent = '● Disconnected';
  b.classList.remove('connected');
  addLog('Disconnected', 'warn');
});

socket.on('sensor', (data) => {
  updateDistances(data);
  updateFlame(data);
});

socket.on('fire_yolo', (data) => updateYOLO(data));

socket.on('log', (data) => addLog(data.msg, data.cls || ''));

// ── Display functions ────────────────────────────────────────────────────────

function updateDistances(d) {
  setDist('left', d.left);
  setDist('center', d.center);
  setDist('right', d.right);
}

function setDist(side, val) {
  const el  = document.getElementById('d-' + side);
  const bar = document.getElementById('bar-' + side);
  el.textContent = val || '—';
  bar.style.width = Math.min(100, (val / MAX_SENSOR) * 100) + '%';
  const color = val < 30 ? '#da3633' : val < 80 ? '#d29922' : '#3fb950';
  bar.style.background = color;
  el.style.color = val < 30 ? '#da3633' : '#e6edf3';
}

function updateFlame(d) {
  const dot  = document.getElementById('flame-dot');
  const text = document.getElementById('flame-text');
  document.getElementById('flame-analog').textContent = 'ADC: ' + d.flame_a;
  if (d.flame_d === 0) {
    dot.classList.add('alert');
    text.textContent = '🔥 FIRE'; text.style.color = '#da3633';
  } else {
    dot.classList.remove('alert');
    text.textContent = 'No Fire'; text.style.color = '#3fb950';
  }
}

function updateYOLO(data) {
  const dot  = document.getElementById('yolo-dot');
  const text = document.getElementById('yolo-text');
  document.getElementById('yolo-count').textContent = 'Count: ' + data.count;
  if (data.detected) {
    dot.style.background = '#da3633';
    dot.style.animation  = 'pulse 0.8s infinite';
    dot.style.boxShadow  = '0 0 0 0 rgba(218,54,51,0.7)';
    text.textContent = '🔥 FIRE DETECTED'; text.style.color = '#da3633';
  } else {
    dot.style.background = '#238636';
    dot.style.animation  = ''; dot.style.boxShadow = '';
    text.textContent = 'No Fire'; text.style.color = '#3fb950';
  }
  const fmt = v => (v !== null && v !== undefined) ? v : '—';
  document.getElementById('fire-cx').textContent   = fmt(data.cx);
  document.getElementById('fire-cy').textContent   = fmt(data.cy);
  const dev = data.deviation;
  const devEl = document.getElementById('fire-dev');
  devEl.textContent = (dev !== null && dev !== undefined)
    ? (dev > 0 ? '+' : '') + dev + 'px' : '—';
  devEl.style.color = (dev !== null && dev !== undefined)
    ? (Math.abs(dev) <= 40 ? '#3fb950' : '#d29922') : '#8b949e';
  document.getElementById('fire-conf').textContent =
    data.conf !== null ? (data.conf * 100).toFixed(0) + '%' : '—';
}

function addLog(msg, cls = '') {
  const box = document.getElementById('log-box');
  const d   = document.createElement('div');
  if (cls) d.className = cls;
  const ts = new Date().toLocaleTimeString('tr');
  d.textContent = `[${ts}] ${msg}`;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  while (box.children.length > 100) box.removeChild(box.firstChild);
}
