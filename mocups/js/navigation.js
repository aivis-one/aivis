/* ========== NAVIGATION SYSTEM ========== */
/* livemockup-studio v1.5.0 — CBS HOME */

/* --- Screen Navigation --- */
function navigateTo(screenId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(screenId);
  if (target) target.classList.add('active');
  const screen = document.getElementById('deviceScreen');
  if (screen) {
    screen.scrollTop = 0;
    screen.scrollTo(0, 0);
    requestAnimationFrame(() => { if (screen) screen.scrollTop = 0; });
  }
}

/* --- Tab Switching --- */
function switchTab(screenId, tabId) {
  navigateTo(screenId);
  // Find the active screen and update its tab bar
  const activeScreen = document.getElementById(screenId);
  if (activeScreen) {
    activeScreen.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
    // Try by matching tab text content
    if (tabId) {
      const tabNames = {};
      document.querySelectorAll('.tab-item').forEach(t => {
        if (t.id === tabId) t.classList.add('active');
      });
      // Fallback: match by tab ID pattern in all tab bars
      if (!document.querySelector('.tab-item.active')) {
        activeScreen.querySelectorAll('.tab-item').forEach((t, i) => {
          // Simple: activate the tab that matches screen
          if (t.getAttribute('onclick')?.includes(screenId)) t.classList.add('active');
        });
      }
    }
  }
}

/* --- Toast Notifications --- */
function showToast(message, type = 'info') {
  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  // Read colors from CSS variables with fallbacks
  const root = getComputedStyle(document.documentElement);
  const getVar = (v, fb) => root.getPropertyValue(v).trim() || fb;
  const colors = {
    success: getVar('--success', '#22c55e'),
    error: getVar('--danger', '#ef4444'),
    warning: getVar('--warning', '#f59e0b'),
    info: getVar('--primary', '#1A6B6A')
  };

  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = '<span>' + (icons[type] || icons.info) + '</span>' + message;
  toast.style.background = colors[type] || colors.info;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/* --- Navigation Map --- */
function openNavMap() {
  const overlay = document.getElementById('navMapOverlay');
  if (overlay) overlay.classList.add('active');
}

function closeNavMap() {
  const overlay = document.getElementById('navMapOverlay');
  if (overlay) overlay.classList.remove('active');
}

function closeNavMapOnOverlay(e) {
  if (e.target.id === 'navMapOverlay') closeNavMap();
}

function navMapGo(screenId) {
  closeNavMap();
  navigateTo(screenId);
  showToast('→ ' + screenId.replace('screen-', ''));
}

function navMapEndpoint(name, parentScreen) {
  closeNavMap();
  if (parentScreen) navigateTo(parentScreen);
  setTimeout(() => showToast('📌 ' + name + ' — финальная точка'), 300);
}

function navMapTab(name, parentScreen) {
  closeNavMap();
  if (parentScreen) navigateTo(parentScreen);
  setTimeout(() => showToast('🟡 Таб "' + name + '" — переключает контент'), 300);
}

function toggleSection(el) {
  const section = el.parentElement;
  if (section) section.classList.toggle('collapsed');
}
