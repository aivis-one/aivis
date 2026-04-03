/* ========== DEVICE PREVIEW CONTROLLER ========== */
/* livemockup-studio v1.5.0 — CBS HOME */

const DevicePreview = {
  devices: {
    phone:   { width: 390,  height: 844 },
    tablet:  { width: 820,  height: 600 },
    desktop: { width: 1280, height: 800 }
  },
  currentDevice: 'phone',
  currentZoom: 100,
  frame: null,
  screen: null,

  init() {
    this.frame = document.getElementById('deviceFrame');
    this.screen = document.getElementById('deviceScreen');
    if (!this.frame || !this.screen) return;

    document.querySelectorAll('[data-device]').forEach(btn => {
      btn.addEventListener('click', () => this.setDevice(btn.dataset.device));
    });
    document.querySelectorAll('[data-zoom]').forEach(btn => {
      btn.addEventListener('click', () => this.changeZoom(parseInt(btn.dataset.zoom)));
    });
    document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    this.setDevice('phone');
  },

  setDevice(type) {
    if (!this.devices[type]) return;
    this.currentDevice = type;
    this.frame.className = 'device-frame ' + type;
    document.querySelectorAll('[data-device]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.device === type);
    });
    // Aggressive scroll reset
    const resetScroll = () => {
      this.screen.scrollTop = 0;
      this.screen.scrollTo({ top: 0, behavior: 'instant' });
    };
    resetScroll();
    requestAnimationFrame(resetScroll);
    setTimeout(resetScroll, 100);
    setTimeout(resetScroll, 400);
  },

  changeZoom(delta) {
    this.currentZoom = Math.min(150, Math.max(50, this.currentZoom + delta));
    this.frame.style.transform = `scale(${this.currentZoom / 100})`;
    this.frame.style.transformOrigin = 'center top';
    const zoomEl = document.querySelector('.zoom-value');
    if (zoomEl) zoomEl.textContent = this.currentZoom + '%';
  },

  handleKeyboard(e) {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
    switch (e.key) {
      case '1': this.setDevice('phone'); break;
      case '2': this.setDevice('tablet'); break;
      case '3': this.setDevice('desktop'); break;
      case '+': case '=': this.changeZoom(10); break;
      case '-': this.changeZoom(-10); break;
      case '0': this.currentZoom = 100; this.changeZoom(0); break;
      case 'm': case 'M':
        if (typeof openNavMap === 'function') openNavMap();
        break;
      case 'Escape':
        if (typeof closeNavMap === 'function') closeNavMap();
        break;
    }
  }
};

document.addEventListener('DOMContentLoaded', () => DevicePreview.init());
