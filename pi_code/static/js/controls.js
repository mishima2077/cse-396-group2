// Manual/Auto mode toggle + motor command dispatch + keyboard shortcuts

let isManual = false;

socket.on('mode_changed', (data) => applyMode(data.manual));

function setMode(manual) {
  socket.emit('set_mode', { manual });
}

function applyMode(manual) {
  isManual = manual;
  const badge  = document.getElementById('mode-badge');
  const toggle = document.getElementById('manual-toggle');
  const card   = document.getElementById('controls-card');
  toggle.checked = manual;
  if (manual) {
    badge.textContent = 'MANUAL'; badge.classList.add('manual');
    card.classList.remove('auto-locked');
  } else {
    badge.textContent = 'AUTO'; badge.classList.remove('manual');
    card.classList.add('auto-locked');
  }
}

const MOTION_CMDS = new Set(['FWD', 'REV', 'TURN_L', 'TURN_R']);

function cmd(c) {
  if (MOTION_CMDS.has(c)) {
    const speed = parseInt(document.getElementById('speed-slider').value, 10);
    socket.emit('command', { cmd: c, speed });
  } else {
    socket.emit('command', { cmd: c });
  }
}

document.addEventListener('keydown', (e) => {
  if (!isManual) return;
  const map = {
    ArrowUp: 'FWD', ArrowDown: 'REV',
    ArrowLeft: 'TURN_L', ArrowRight: 'TURN_R',
    ' ': 'STOP',
  };
  if (map[e.key]) { e.preventDefault(); cmd(map[e.key]); }
});
