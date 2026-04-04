/* ========== NAVIGATION SYSTEM ========== */
/* livemockup-studio v1.6.0 — CBS HOME */

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
  const activeScreen = document.getElementById(screenId);
  if (activeScreen) {
    activeScreen.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
    if (tabId) {
      document.querySelectorAll('.tab-item').forEach(t => {
        if (t.id === tabId) t.classList.add('active');
      });
      if (!activeScreen.querySelector('.tab-item.active')) {
        activeScreen.querySelectorAll('.tab-item').forEach(t => {
          if (t.getAttribute('onclick') && t.getAttribute('onclick').includes(screenId)) t.classList.add('active');
        });
      }
    }
  }
}

/* --- Toast Notifications --- */
function showToast(message, type) {
  if (!type) type = 'info';
  var icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  var root = getComputedStyle(document.documentElement);
  var getVar = function(v, fb) { return root.getPropertyValue(v).trim() || fb; };
  var colors = {
    success: getVar('--success', '#22c55e'),
    error: getVar('--danger', '#ef4444'),
    warning: getVar('--warning', '#f59e0b'),
    info: getVar('--primary', '#084456')
  };

  var existing = document.querySelector('.toast');
  if (existing) existing.remove();

  var toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = '<span>' + (icons[type] || icons.info) + '</span>' + message;
  toast.style.background = colors[type] || colors.info;
  document.body.appendChild(toast);
  requestAnimationFrame(function() { toast.classList.add('show'); });
  setTimeout(function() {
    toast.classList.remove('show');
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
}

/* --- Navigation Map --- */
function openNavMap() {
  var overlay = document.getElementById('navMapOverlay');
  if (overlay) overlay.classList.add('active');
}

function closeNavMap() {
  var overlay = document.getElementById('navMapOverlay');
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
  var msg = (typeof I18N !== 'undefined') ? I18N.t('nav.endpoint', { name: name }) : '📌 ' + name + ' — финальная точка';
  setTimeout(function() { showToast(msg); }, 300);
}

function navMapTab(name, parentScreen) {
  closeNavMap();
  if (parentScreen) navigateTo(parentScreen);
  var msg = (typeof I18N !== 'undefined') ? I18N.t('nav.tab', { name: name }) : '🟡 Таб "' + name + '" — переключает контент';
  setTimeout(function() { showToast(msg); }, 300);
}

function toggleSection(el) {
  var section = el.parentElement;
  if (section) section.classList.toggle('collapsed');
}
