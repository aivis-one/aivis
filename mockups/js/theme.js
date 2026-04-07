/* ========== THEME MANAGER ==========
   livemockup-studio v1.6.0 — CBS HOME
   States: auto | light | dark
   Persist: localStorage('cbs-theme')
   ========== */

const ThemeManager = {
  _key: 'cbs-theme',
  _states: ['auto', 'light', 'dark'],
  _icons: { auto: 'monitor', light: 'sun', dark: 'moon' },
  _current: 'auto',

  init() {
    const saved = localStorage.getItem(this._key);
    if (saved === 'light' || saved === 'dark') {
      this._current = saved;
    } else {
      this._current = 'auto';
    }
    this._apply();
    this._updateIcon();
  },

  set(theme) {
    this._current = theme;
    if (theme === 'auto') {
      localStorage.removeItem(this._key);
      document.documentElement.removeAttribute('data-theme');
    } else {
      localStorage.setItem(this._key, theme);
      document.documentElement.setAttribute('data-theme', theme);
    }
    this._updateIcon();
  },

  cycle() {
    const idx = this._states.indexOf(this._current);
    const next = this._states[(idx + 1) % this._states.length];
    this.set(next);
    // Show toast if available
    if (typeof showToast === 'function') {
      const labels = { auto: 'Auto', light: 'Light', dark: 'Dark' };
      if (typeof I18N !== 'undefined') {
        showToast(I18N.t('theme.' + next));
      } else {
        showToast('Theme: ' + labels[next]);
      }
    }
  },

  getEffective() {
    if (this._current !== 'auto') return this._current;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  },

  _apply() {
    if (this._current === 'auto') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', this._current);
    }
  },

  _updateIcon() {
    const iconName = this._icons[this._current];
    const btn = document.querySelector('.theme-toggle');
    if (btn) {
      btn.innerHTML = '<i data-lucide="' + iconName + '"></i>';
      btn.title = this._current.charAt(0).toUpperCase() + this._current.slice(1);
      if (typeof lucide !== 'undefined') lucide.createIcons({ nodes: [btn] });
    }
  }
};
