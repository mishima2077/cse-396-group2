// Travel map canvas rendering, results overlay, and export

const MARKER_GLYPH = {
  start: '●', end: '■', fire: '🔥', arrived: '🎯',
  extinguish: '💧', obstacle: '⛔', scan: '🔍',
};
const MARKER_COLOR = {
  start: '#3fb950', end: '#e6edf3', fire: '#da3633', arrived: '#f78166',
  extinguish: '#58a6ff', obstacle: '#d29922', scan: '#8b949e',
};

// ── Overlay lifecycle ───────────────────────────────────────────────────────

function showOverlay() {
  document.getElementById('overlay-meta').textContent =
    new Date().toLocaleString('tr') + '  ·  ' + fmtDur(runDurationMs / 1000);

  document.getElementById('stat-duration').textContent = fmtDur(runDurationMs / 1000);
  document.getElementById('stat-distance').textContent = (RUN.stats.distCm / 100).toFixed(1) + 'm';
  document.getElementById('stat-fires').textContent    = RUN.stats.fires;
  document.getElementById('stat-ext').textContent      = RUN.stats.extinguished;
  document.getElementById('stat-obs').textContent      = RUN.stats.obstacles;
  document.getElementById('stat-scans').textContent    = RUN.stats.scans;

  buildTimeline();

  document.getElementById('overlay').classList.add('open');

  requestAnimationFrame(() => {
    const canvas  = document.getElementById('map-canvas');
    const col     = document.getElementById('map-col');
    const legendH = document.getElementById('map-legend').offsetHeight;
    const size    = Math.min(col.clientWidth - 32, col.clientHeight - legendH - 32, 640);
    canvas.width  = Math.max(size, 300);
    canvas.height = Math.max(size, 300);
    renderMap();
    setupMapTooltip();
  });
}

function closeOverlay() {
  document.getElementById('overlay').classList.remove('open');
}

// ── Timeline ────────────────────────────────────────────────────────────────

function buildTimeline() {
  const list = document.getElementById('timeline-list');
  list.innerHTML = '';
  const clsMap = { fire:'fire-item', info:'info-item', warn:'warn-item', pump:'pump-item', cmd:'' };
  for (const item of RUN.timeline) {
    const div = document.createElement('div');
    div.className = 'tl-item ' + (clsMap[item.cls] || '');
    div.innerHTML =
      `<span class="tl-time">t+${item.t_s.toFixed(0)}s</span>` +
      `<span class="tl-msg">${escHtml(item.msg)}</span>`;
    list.appendChild(div);
  }
  list.scrollTop = 0;
}

// ── Map rendering ───────────────────────────────────────────────────────────

function renderMap() {
  const canvas = document.getElementById('map-canvas');
  const ctx    = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = 55;

  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, W, H);

  const path    = RUN.dr.path;
  const markers = RUN.markers;

  // Bounding box over all points + origin
  const allX = [0, ...path.map(p => p.x), ...markers.map(m => m.x)];
  const allY = [0, ...path.map(p => p.y), ...markers.map(m => m.y)];
  const minX = Math.min(...allX), maxX = Math.max(...allX);
  const minY = Math.min(...allY), maxY = Math.max(...allY);
  const rangeX = Math.max(maxX - minX, 80);
  const rangeY = Math.max(maxY - minY, 80);
  const scale  = Math.min((W - 2*pad) / rangeX, (H - 2*pad) / rangeY, 6);
  const midX   = (minX + maxX) / 2, midY = (minY + maxY) / 2;

  // World-cm → canvas-px  (y flipped: north = up)
  const wx = x =>  W/2 + (x - midX) * scale;
  const wy = y =>  H/2 - (y - midY) * scale;

  // Faint 50cm grid
  ctx.strokeStyle = '#21262d'; ctx.lineWidth = 1;
  const step = 50;
  for (let gx = Math.floor(minX/step)*step - step; gx <= maxX + step; gx += step) {
    const px = wx(gx);
    if (px < 0 || px > W) continue;
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, H); ctx.stroke();
  }
  for (let gy = Math.floor(minY/step)*step - step; gy <= maxY + step; gy += step) {
    const py = wy(gy);
    if (py < 0 || py > H) continue;
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke();
  }

  // Grid labels
  ctx.fillStyle = '#30363d'; ctx.font = '9px monospace'; ctx.textAlign = 'left';
  for (let gx = Math.floor(minX/step)*step; gx <= maxX + step; gx += step*2) {
    const px = wx(gx);
    if (px < 10 || px > W - 10) continue;
    ctx.fillText(gx + 'cm', px + 2, H - 4);
  }

  // Path (blue gradient, old → new)
  if (path.length > 1) {
    for (let i = 1; i < path.length; i++) {
      const t = i / path.length;
      ctx.beginPath();
      ctx.moveTo(wx(path[i-1].x), wy(path[i-1].y));
      ctx.lineTo(wx(path[i].x),   wy(path[i].y));
      ctx.strokeStyle = `rgba(56,139,253,${0.3 + t * 0.7})`;
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  // Origin crosshair
  ctx.strokeStyle = '#30363d'; ctx.lineWidth = 1; ctx.setLineDash([4,4]);
  ctx.beginPath(); ctx.moveTo(wx(0)-12, wy(0)); ctx.lineTo(wx(0)+12, wy(0)); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(wx(0), wy(0)-12); ctx.lineTo(wx(0), wy(0)+12); ctx.stroke();
  ctx.setLineDash([]);

  // North arrow
  const ax = 26, ay = 26;
  ctx.strokeStyle = '#58a6ff'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(ax, ay+12); ctx.lineTo(ax, ay-12); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(ax-5, ay-6); ctx.lineTo(ax, ay-14); ctx.lineTo(ax+5, ay-6);
  ctx.fillStyle = '#58a6ff'; ctx.fill();
  ctx.font = '10px monospace'; ctx.textAlign = 'center';
  ctx.fillText('N', ax, ay+22);

  // Scale bar
  const barCm = scaleBarStep(scale);
  const barPx = barCm * scale;
  const bx = W - pad - barPx, by = H - 14;
  ctx.strokeStyle = '#8b949e'; ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(bx, by); ctx.lineTo(bx + barPx, by);
  ctx.moveTo(bx,       by-4); ctx.lineTo(bx,       by+4);
  ctx.moveTo(bx+barPx, by-4); ctx.lineTo(bx+barPx, by+4);
  ctx.stroke();
  ctx.fillStyle = '#8b949e'; ctx.font = '10px monospace'; ctx.textAlign = 'center';
  ctx.fillText(barCm + 'cm', bx + barPx/2, by-7);

  // Markers
  for (const m of markers) {
    const px = wx(m.x), py = wy(m.y);
    if (m.type === 'start' || m.type === 'end') {
      ctx.fillStyle = MARKER_COLOR[m.type];
      ctx.font = '13px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(MARKER_GLYPH[m.type], px, py);
    } else {
      ctx.font = '18px serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(MARKER_GLYPH[m.type] || '?', px, py);
    }
  }
  ctx.textBaseline = 'alphabetic';
}

// ── Map hover tooltip ───────────────────────────────────────────────────────

function setupMapTooltip() {
  const canvas  = document.getElementById('map-canvas');
  const tooltip = document.getElementById('map-tooltip');
  const W = canvas.width, H = canvas.height;
  const path    = RUN.dr.path;
  const markers = RUN.markers;

  const allX = [0, ...path.map(p=>p.x), ...markers.map(m=>m.x)];
  const allY = [0, ...path.map(p=>p.y), ...markers.map(m=>m.y)];
  const minX = Math.min(...allX), maxX = Math.max(...allX);
  const minY = Math.min(...allY), maxY = Math.max(...allY);
  const scale = Math.min((W-110)/(Math.max(maxX-minX,80)), (H-110)/(Math.max(maxY-minY,80)), 6);
  const midX  = (minX+maxX)/2, midY = (minY+maxY)/2;
  const wx = x =>  W/2 + (x - midX) * scale;
  const wy = y =>  H/2 - (y - midY) * scale;

  const HITBOX = 18;

  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const found = markers.find(m => Math.abs(wx(m.x)-mx) < HITBOX && Math.abs(wy(m.y)-my) < HITBOX);
    if (found) {
      tooltip.textContent   = found.label;
      tooltip.style.display = 'block';
      tooltip.style.left    = (e.clientX + 14) + 'px';
      tooltip.style.top     = (e.clientY - 8)  + 'px';
    } else {
      tooltip.style.display = 'none';
    }
  });
  canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
}

// ── Export ──────────────────────────────────────────────────────────────────

function exportJSON() {
  const ts   = new Date().toISOString().replace(/[:.]/g, '-').slice(0,19);
  const data = {
    date:       new Date().toISOString(),
    duration_s: runDurationMs / 1000,
    stats:      RUN.stats,
    markers:    RUN.markers,
    timeline:   RUN.timeline,
    path_cm:    RUN.dr.path,
    events:     RUN.events,
  };
  dlBlob(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}),
         `rover_run_${ts}.json`);
}

function exportPNG() {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0,19);
  document.getElementById('map-canvas').toBlob(blob => dlBlob(blob, `rover_map_${ts}.png`));
}

// ── Utilities ────────────────────────────────────────────────────────────────

function fmtDur(totalS) {
  const m = Math.floor(totalS / 60);
  const s = Math.floor(totalS % 60);
  return m + ':' + String(s).padStart(2, '0');
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function dlBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function scaleBarStep(scale) {
  for (const step of [200, 100, 50, 20, 10]) {
    if (step * scale >= 50) return step;
  }
  return 10;
}
