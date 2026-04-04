---
name: shell
description: "v1.8.0 | Device Preview shell with Navigation Map"
---

# Shell

Device Preview shell — wrapper for mockup content with Navigation Map.

---

## ❌/✅ Examples

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| Floating toolbar `left:50%` | Full-width `left:0; right:0` |
| `position: fixed` inside mockup | `position: sticky` inside mockup |
| Content overlapped by toolbar | Clear space below toolbar |
| No keyboard shortcuts | 1/2/3 for devices, +/- for zoom |
| Children block parent onclick | `pointer-events: none` on children |
| Tab bar floats up | Full flex chain to bottom |
| `align-items: center` on container | `align-items: flex-start` + `margin: auto` on frame |
| `form` + `onsubmit` | `div` + `onclick` on button |
| No navigation visibility | Navigation Map shows all screens |
| Unclear dead ends | Toast `📌 ... — финальная точка` |

---

## Forms Pattern ⚠️

Use `div` + `onclick`, NOT `form` + `onsubmit`.

### ✅ Correct

```html
<div class="form">
  <input type="email" value="user@example.com" readonly>
  <button type="button" onclick="handleLogin()">Войти</button>
</div>
```

### ❌ Wrong

```html
<form onsubmit="handleLogin(event)">
  <button type="submit">Войти</button>
</form>
```

**Why:** Form submit handlers are unreliable in device preview context.

---

## Structure

```
<!DOCTYPE html>
├── <head>
│   ├── meta viewport
│   ├── Google Fonts
│   └── <style>
│       ├── Shell CSS (toolbar, frame)
│       ├── Navigation Map CSS ⭐
│       ├── Mobile Toolbar CSS ⭐
│       ├── Clickability Fix CSS ⚠️
│       └── Mockup CSS (content styles)
├── <body>
│   ├── Preview Toolbar (fixed, top:0)
│   │   └── Map Button ⭐
│   ├── Preview Container (below toolbar)
│   │   └── Device Frame
│   │       ├── Device Notch (phone only)
│   │       ├── Device Screen (flex column, overflow:auto)
│   │       │   └── .mockup-content (flex:1, flex column)
│   │       │       ├── .screen.active (flex:1, flex column)
│   │       │       │   ├── header (sticky top)
│   │       │       │   ├── main (flex:1)
│   │       │       │   └── tab-bar (sticky bottom)
│   │       └── Home Indicator (phone only)
│   ├── Navigation Map Popup ⭐
│   ├── Toast Container
│   └── <script> (controller + nav map)
```

---

## CSS Variables

```css
:root {
  /* Shell Theme */
  --shell-bg: #0f172a;
  --shell-surface: #1e293b;
  --shell-border: #334155;
  --shell-text: #ffffff;
  --shell-text-dim: rgba(255,255,255,0.5);
  --shell-accent: #3b82f6;
  --shell-accent-glow: rgba(59,130,246,0.3);
  
  /* Device Frame */
  --frame-bg: #374151;
  --frame-radius-phone: 44px;
  --frame-radius-tablet: 24px;
  --frame-radius-desktop: 12px;
  --frame-padding: 12px;
  
  /* Screen */
  --screen-radius-phone: 38px;
  --screen-radius-tablet: 16px;
  --screen-radius-desktop: 8px;
}
```

---

## Device Specs

| Device | Width | Height | Frame Radius |
|--------|-------|--------|--------------|
| Phone | 390 | 844 | 44px |
| Tablet | 820 | 600 | 24px |
| Desktop | 1280 | 800 | 12px |

---

## Toolbar HTML (with Map Button)

```html
<div class="preview-toolbar">
  <div class="toolbar-left">
    <div class="project-info">
      <span class="project-name">{PROJECT} v1</span>
      <span class="project-badge">LIVE</span>
    </div>
    <a href="../index.html" class="home-btn" title="Hub"><i data-lucide="layout-grid"></i></a>
  </div>

  <div class="toolbar-center">
    <div class="device-switcher">
      <button class="device-btn active" data-device="phone">
        <i data-lucide="smartphone" style="width:14px;height:14px"></i>
        <span class="device-label">Phone</span>
        <span class="device-size">390</span>
      </button>
      <button class="device-btn" data-device="tablet">
        <i data-lucide="tablet" style="width:14px;height:14px"></i>
        <span class="device-label">Tablet</span>
        <span class="device-size">820</span>
      </button>
      <button class="device-btn" data-device="desktop">
        <i data-lucide="monitor" style="width:14px;height:14px"></i>
        <span class="device-label">Desktop</span>
        <span class="device-size">1280</span>
      </button>
    </div>
  </div>
  
  <div class="toolbar-right">
    <button class="theme-toggle" onclick="ThemeManager.cycle()" title="Theme">
      <i data-lucide="monitor"></i>
    </button>
    <div class="lang-switcher">
      <button class="lang-btn active" data-lang="ru" onclick="I18N.setLocale('ru')">RU</button>
      <button class="lang-btn" data-lang="en" onclick="I18N.setLocale('en')">EN</button>
      <button class="lang-btn" data-lang="de" onclick="I18N.setLocale('de')">DE</button>
    </div>
    <button class="map-btn" onclick="openNavMap()">
      📍 <span class="map-label">Map</span>
    </button>
    <div class="zoom-control">
      <button class="zoom-btn" data-zoom="-10">−</button>
      <span class="zoom-value">100%</span>
      <button class="zoom-btn" data-zoom="+10">+</button>
    </div>
  </div>
</div>
```

---

## Toolbar CSS

```css
.preview-toolbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: var(--shell-surface);
  border-bottom: 1px solid var(--shell-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  z-index: 1000;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 200px;
}

.toolbar-right {
  justify-content: flex-end;
}

.toolbar-center {
  display: flex;
  justify-content: center;
}

.project-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--shell-text);
}

.project-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--shell-accent);
  color: white;
}

.device-switcher {
  display: flex;
  background: rgba(0,0,0,0.3);
  border-radius: 10px;
  padding: 4px;
}

.device-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--shell-text-dim);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.device-btn:hover {
  background: rgba(255,255,255,0.05);
  color: var(--shell-text);
}

.device-btn.active {
  background: var(--shell-accent);
  color: white;
  box-shadow: 0 2px 8px var(--shell-accent-glow);
}

.device-size {
  font-size: 11px;
  opacity: 0.6;
  font-family: monospace;
}

.zoom-control {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0,0,0,0.3);
  border-radius: 8px;
  padding: 4px;
}

.zoom-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--shell-text-dim);
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.zoom-btn:hover {
  background: rgba(255,255,255,0.1);
  color: var(--shell-text);
}

.zoom-value {
  width: 50px;
  text-align: center;
  font-size: 12px;
  font-family: monospace;
  color: var(--shell-text);
}

@media (max-width: 768px) {
  .device-label { display: none; }
  .project-info { display: none; }
}
```

---

## Frame HTML

```html
<div class="preview-container">
  <div class="device-frame phone" id="deviceFrame">
    <div class="device-notch"></div>
    <div class="device-screen" id="deviceScreen">
      <div class="mockup-content">
        <!-- CONTENT HERE -->
      </div>
    </div>
    <div class="device-home-indicator"></div>
  </div>
</div>
```

---

## Frame CSS ⚠️ CRITICAL

```css
/* ⚠️ CRITICAL: align-items: flex-start prevents top clipping */
.preview-container {
  position: fixed;
  top: 48px;  /* Below toolbar */
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: flex-start;  /* ⚠️ NOT center — prevents top clipping */
  justify-content: center;
  background: var(--shell-bg);
  padding: 20px;
  overflow: auto;
}

/* ⚠️ CRITICAL: margin: auto centers frame when it fits */
.device-frame {
  background: var(--frame-bg);
  position: relative;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  margin: auto;  /* ⚠️ Centers when smaller than container */
}

/* Phone */
.device-frame.phone {
  width: calc(390px + var(--frame-padding) * 2);
  height: calc(844px + var(--frame-padding) * 2 + 40px);
  border-radius: var(--frame-radius-phone);
  padding: var(--frame-padding);
  padding-top: 28px;
  padding-bottom: 20px;
}

.device-frame.phone .device-screen {
  border-radius: var(--screen-radius-phone);
  width: 390px;
  height: 844px;
}

/* Tablet */
.device-frame.tablet {
  width: calc(820px + var(--frame-padding) * 2);
  height: calc(600px + var(--frame-padding) * 2);
  border-radius: var(--frame-radius-tablet);
  padding: var(--frame-padding);
}

.device-frame.tablet .device-screen {
  border-radius: var(--screen-radius-tablet);
  width: 820px;
  height: 600px;
}

.device-frame.tablet .device-notch,
.device-frame.tablet .device-home-indicator {
  display: none;
}

/* Desktop */
.device-frame.desktop {
  width: calc(1280px + var(--frame-padding) * 2);
  height: calc(800px + var(--frame-padding) * 2);
  border-radius: var(--frame-radius-desktop);
  padding: var(--frame-padding);
}

.device-frame.desktop .device-screen {
  border-radius: var(--screen-radius-desktop);
  width: 1280px;
  height: 800px;
}

.device-frame.desktop .device-notch,
.device-frame.desktop .device-home-indicator {
  display: none;
}

/* Screen - CRITICAL: flex column for layout chain */
.device-screen {
  background: #fff;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
  scroll-behavior: auto;
  min-height: 0;
  position: relative;
}

/* Notch */
.device-notch {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  width: 120px;
  height: 28px;
  background: #000;
  border-radius: 14px;
  z-index: 10;
}

/* Home Indicator */
.device-home-indicator {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  width: 134px;
  height: 5px;
  background: rgba(255,255,255,0.3);
  border-radius: 3px;
}
```

---

## Clickability Fix ⚠️ REQUIRED

**Critical:** Add this CSS to prevent children from blocking parent onclick.

```css
/* ========== CLICKABLE CONTAINERS FIX ========== */
/* Disable pointer-events on children of clickable containers */
.alert-card[onclick] *,
.stat-card[onclick] *,
.card[onclick] *,
.master-card[onclick] *,
.moderation-card[onclick] *,
.metric-row[onclick] *,
.user-mode-btn[onclick] *,
table tr[onclick] * {
  pointer-events: none;
}

/* Re-enable pointer-events for nested interactive elements */
button,
input,
select,
textarea,
.checkbox,
.doc-checkbox {
  pointer-events: auto;
}
```

**Why:** Child elements (text, icons, progress bars) intercept clicks and prevent parent onclick from firing.

---

## Sticky Rules ⚠️

**Critical:** Inside `.device-screen`, use `sticky` NOT `fixed`.

| Element | Correct | Wrong |
|---------|---------|-------|
| Header | `position: sticky; top: 0` | `position: fixed` |
| Tab Bar | `position: sticky; bottom: 0` | `position: fixed` |
| Sidebar | `position: sticky; top: 0` | `position: fixed` |
| Popup overlay | `position: fixed` (OK) | — |

**Why:** `position: fixed` is relative to viewport, not `.device-screen`.

---

## Flex Layout Chain ⚠️ REQUIRED

**Critical:** Full flex chain from device-screen to tab-bar.

```css
/* Screen container */
.device-screen {
  display: flex;
  flex-direction: column;
}

/* Mockup wrapper */
.mockup-content {
  min-height: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  flex: 1;
}

/* Active screen */
.screen.active {
  display: flex;
  flex: 1;
  flex-direction: column;
}

/* Header - sticky top */
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: white;
}

/* Main content - fills space */
.main {
  flex: 1;
}

/* Tab bar - sticky bottom */
.tab-bar {
  position: sticky;
  bottom: 0;
  z-index: 100;
  background: white;
}
```

**Why:** Without full flex chain, tab-bar floats up instead of staying at bottom.

---

## JS Controller

```javascript
const DevicePreview = {
  devices: {
    phone:   { width: 390,  height: 844,  label: 'Phone' },
    tablet:  { width: 820,  height: 600,  label: 'Tablet' },
    desktop: { width: 1280, height: 800,  label: 'Desktop' }
  },
  currentDevice: 'phone',
  currentZoom: 100,
  frame: null,
  screen: null,

  init() {
    this.frame = document.getElementById('deviceFrame');
    this.screen = document.getElementById('deviceScreen');
    
    document.querySelectorAll('[data-device]').forEach(btn => {
      btn.addEventListener('click', () => this.setDevice(btn.dataset.device));
    });
    
    document.querySelectorAll('[data-zoom]').forEach(btn => {
      btn.addEventListener('click', () => this.changeZoom(parseInt(btn.dataset.zoom)));
    });
    
    document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    this.setDevice('phone');

    // Init theme and i18n if available
    if (typeof ThemeManager !== 'undefined') ThemeManager.init();
    if (typeof I18N !== 'undefined') I18N.init();
  },

  setDevice(type) {
    if (!this.devices[type]) return;
    this.currentDevice = type;
    
    this.frame.className = 'device-frame ' + type;
    
    document.querySelectorAll('[data-device]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.device === type);
    });
    
    // ⚠️ Aggressive scroll reset - multiple attempts
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
    switch(e.key) {
      case '1': this.setDevice('phone'); break;
      case '2': this.setDevice('tablet'); break;
      case '3': this.setDevice('desktop'); break;
      case '+': case '=': this.changeZoom(10); break;
      case '-': this.changeZoom(-10); break;
      case '0': this.currentZoom = 100; this.changeZoom(0); break;
      case 'm': case 'M':
        if (typeof openNavMap === 'function') openNavMap();
        break;
      case 't': case 'T':
        if (typeof ThemeManager !== 'undefined') ThemeManager.cycle();
        break;
      case 'l': case 'L':
        if (typeof I18N !== 'undefined') I18N.toggleLocale();
        break;
      case 'Escape':
        if (typeof closeNavMap === 'function') closeNavMap();
        break;
    }
  }
};

document.addEventListener('DOMContentLoaded', () => DevicePreview.init());

// ⚠️ Navigation with scroll reset
function navigateTo(screenId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(screenId).classList.add('active');
  
  // Reliable scroll reset
  const screen = document.getElementById('deviceScreen');
  screen.scrollTop = 0;
  screen.scrollTo(0, 0);
  requestAnimationFrame(() => screen.scrollTop = 0);
}
```

---

## Map Button CSS ⭐

```css
.map-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  background: rgba(59,130,246,0.2);
  color: var(--shell-accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.map-btn:hover {
  background: var(--shell-accent);
  color: white;
}
```

---

## Theme Toggle CSS ⭐

```css
.theme-toggle {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; border-radius: 6px;
  background: rgba(255,255,255,0.08); color: var(--shell-text-dim);
  cursor: pointer; transition: all 0.2s; padding: 0;
}
.theme-toggle:hover { background: rgba(255,255,255,0.15); color: var(--shell-text); }
.theme-toggle svg { width: 16px; height: 16px; }
```

---

## Language Switcher CSS ⭐

```css
.lang-switcher {
  display: flex; background: rgba(0,0,0,0.3); border-radius: 6px; padding: 2px;
}
.lang-btn {
  padding: 4px 8px; border: none; border-radius: 4px;
  background: transparent; color: var(--shell-text-dim);
  font-size: 11px; font-weight: 600; cursor: pointer;
  transition: all 0.2s; font-family: inherit;
}
.lang-btn:hover { color: var(--shell-text); }
.lang-btn.active { background: var(--shell-accent); color: #fff; }
```

---

## Mobile Toolbar CSS ⭐

```css
@media (max-width: 768px) {
  .device-label { display: none; }
  .project-info { display: none; }
}

@media (max-width: 480px) {
  .preview-toolbar {
    padding: 0 8px;
    gap: 4px;
  }
  
  .toolbar-left, .toolbar-right {
    min-width: auto;
    gap: 4px;
  }
  
  .device-switcher {
    padding: 2px;
    border-radius: 8px;
  }
  
  .device-btn {
    padding: 6px 8px;
    font-size: 14px;
  }
  
  .device-btn .device-size {
    display: none;
  }
  
  .zoom-control {
    padding: 2px;
  }
  
  .zoom-btn {
    width: 24px;
    height: 24px;
    font-size: 14px;
  }
  
  .zoom-value {
    display: none;
  }
  
  .map-btn {
    padding: 6px 8px !important;
    font-size: 14px !important;
  }
  
  .map-btn .map-label {
    display: none;
  }

  .theme-toggle {
    width: 24px;
    height: 24px;
    padding: 4px;
  }

  .lang-btn {
    padding: 3px 5px;
    font-size: 10px;
  }
}
```

---

## Navigation Map HTML ⭐

```html
<div class="nav-map-overlay" id="navMapOverlay" onclick="closeNavMapOnOverlay(event)">
  <div class="nav-map" onclick="event.stopPropagation()">
    <div class="nav-map-header">
      <div class="nav-map-title">📍 Navigation Map</div>
      <button class="nav-map-close" onclick="closeNavMap()">×</button>
    </div>
    <div class="nav-map-body">
      <!-- Stats -->
      <div class="nav-map-stats">
        <div class="nav-map-stat">
          <div class="nav-map-stat-value">{SCREENS}</div>
          <div class="nav-map-stat-label">экранов</div>
        </div>
        <div class="nav-map-stat">
          <div class="nav-map-stat-value">{PATHS}</div>
          <div class="nav-map-stat-label">полных путей</div>
        </div>
        <div class="nav-map-stat">
          <div class="nav-map-stat-value">{ENDPOINTS}</div>
          <div class="nav-map-stat-label">финальных точек</div>
        </div>
      </div>

      <!-- Legend: Traffic Light -->
      <div class="nav-map-legend">
        <div class="nav-map-legend-item">
          <span class="legend-dot green"></span> Экран
        </div>
        <div class="nav-map-legend-item">
          <span class="legend-dot yellow"></span> Табы
        </div>
        <div class="nav-map-legend-item">
          <span class="legend-dot red"></span> Тупик
        </div>
      </div>

      <!-- Tree: horizontal chip layout -->
      <div class="nav-map-tree">
        <!-- Collapsible Section -->
        <div class="nav-map-section">
          <div class="nav-map-section-title" onclick="toggleSection(this)">
            <span class="section-info"><span data-i18n="nav.section.tabs">ТАБЫ</span> <span class="section-count">(N)</span></span>
            <span class="section-arrow">&#x25BC;</span>
          </div>
          <div class="nav-map-section-content">
            <!-- Chips: no wrapper divs, no icons, dot before name -->
            <div class="nav-map-item tab-item" onclick="navMapTab('Dashboard','screen-dashboard')">
              <span class="status-dot yellow"></span>
              <span class="nav-map-item-name" data-i18n="nav.inv.dashboard">Главная</span>
              <span class="level-badge tab">TAB</span>
            </div>
            <div class="nav-map-item screen-item" onclick="navMapGo('screen-detail')" data-depth="1">
              <span class="status-dot green"></span>
              <span class="nav-map-item-name" data-i18n="nav.inv.productDetail">Детали продукта</span>
              <span class="level-badge">L1</span>
            </div>
            <div class="nav-map-item endpoint-item" onclick="navMapEndpoint('Покупка','screen-detail')">
              <span class="status-dot red"></span>
              <span class="nav-map-item-name">Покупка</span>
              <span class="level-badge end">END</span>
            </div>
                <span class="nav-map-item-icon">👤</span>
                <span class="nav-map-item-name">↳ Detail Screen</span>
                <span class="level-badge">L3</span>
                <span class="status-dot green"></span>
              </div>
            </div>

            <!-- L3: Endpoint -->
            <div class="nav-map-level" data-level="3">
              <div class="nav-map-item endpoint-item" onclick="navMapEndpoint('Item Name', 'screen-list')">
                <span class="nav-map-item-name">↳ Item Name</span>
                <span class="level-badge end">END</span>
                <span class="status-dot red"></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

---

## Navigation Map CSS ⭐

```css
.nav-map-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.8);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 20px;
}

.nav-map-overlay.active { display: flex; }

.nav-map {
  background: var(--shell-surface);
  border: 1px solid var(--shell-border);
  border-radius: 16px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.nav-map-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--shell-border);
}

.nav-map-title { font-size: 18px; font-weight: 600; color: var(--shell-text); }

.nav-map-close {
  width: 32px; height: 32px;
  border: none; border-radius: 8px;
  background: rgba(255,255,255,0.1);
  color: var(--shell-text);
  font-size: 18px; cursor: pointer;
  transition: all 0.2s;
}

.nav-map-close:hover { background: var(--velo-error, #EF4444); }

.nav-map-body { flex: 1; overflow-y: auto; padding: 20px; }

/* Stats: grid 3 columns, dark card per stat */
.nav-map-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.nav-map-stat {
  background: rgba(0,0,0,0.2);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}

.nav-map-stat-value { font-size: 24px; font-weight: 700; color: var(--shell-accent); }
.nav-map-stat-label { font-size: 11px; color: var(--shell-text-dim); }

/* Legend: dark background bar */
.nav-map-legend {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: rgba(0,0,0,0.2);
  border-radius: 6px;
}

.nav-map-legend-item {
  font-size: 12px;
  color: var(--shell-text-dim);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Traffic Light Dots */
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.status-dot.green { background: #22C55E; }
.status-dot.yellow { background: #F59E0B; }
.status-dot.red { background: #EF4444; }

.legend-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
.legend-dot.green { background: #22C55E; }
.legend-dot.yellow { background: #F59E0B; }
.legend-dot.red { background: #EF4444; }

.nav-map-item .status-dot { margin-left: 8px; }

/* Tree */
.nav-map-tree { display: flex; flex-direction: column; gap: 4px; }

/* Level indentation via CSS variables */
.nav-map-level { padding-left: calc(var(--level, 0) * 16px); }
.nav-map-level[data-level="1"] { --level: 1; }
.nav-map-level[data-level="2"] { --level: 2; }
.nav-map-level[data-level="3"] { --level: 3; }

/* Items */
.nav-map-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-map-item:hover { background: rgba(59,130,246,0.2); }
.nav-map-item-icon { font-size: 14px; }
.nav-map-item-name { flex: 1; font-size: 13px; color: var(--shell-text); }

.nav-map-item-badge {
  font-size: 10px; font-weight: 600;
  padding: 2px 6px; border-radius: 4px;
}
.nav-map-item-badge.screen { background: rgba(34,197,94,0.2); color: #22C55E; }
.nav-map-item-badge.endpoint { background: rgba(251,146,60,0.2); color: #FB923C; }

/* Item type hovers (traffic-light differentiation) */
.nav-map-item.screen-item:hover { background: rgba(34,197,94,0.15); }
.nav-map-item.tab-item { opacity: 0.85; }
.nav-map-item.tab-item:hover { opacity: 1; background: rgba(245,158,11,0.15); }
.nav-map-item.endpoint-item { opacity: 0.7; }
.nav-map-item.endpoint-item:hover { opacity: 1; background: rgba(239,68,68,0.15); }

/* Level badges (right-aligned, semantic colors) */
.level-badge {
  font-size: 9px; font-weight: 700;
  padding: 2px 6px; border-radius: 4px;
  background: rgba(255,255,255,0.1);
  color: var(--shell-text-dim);
  margin-left: auto;
}
.level-badge.hub { background: rgba(59,130,246,0.3); color: #60A5FA; }
.level-badge.tab { background: rgba(245,158,11,0.2); color: #FBBF24; }
.level-badge.end { background: rgba(239,68,68,0.2); color: #F87171; }

/* Collapsible Sections */
.nav-map-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--shell-border);
}
.nav-map-section:first-child { margin-top: 0; padding-top: 0; border-top: none; }

.nav-map-section-title {
  font-size: 11px; font-weight: 600;
  color: var(--shell-text-dim);
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 8px; padding: 8px 12px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  border-radius: 6px;
  transition: all 0.2s;
}
.nav-map-section-title:hover { background: rgba(255,255,255,0.05); color: var(--shell-text); }
.nav-map-section-title .section-info { display: flex; align-items: center; gap: 8px; }
.nav-map-section-title .section-count { font-size: 10px; color: var(--shell-accent); font-weight: 700; }
.nav-map-section-title .section-arrow { font-size: 10px; transition: transform 0.2s; }
.nav-map-section.collapsed .section-arrow { transform: rotate(-90deg); }

.nav-map-section-content {
  display: flex; flex-direction: column; gap: 4px;
  overflow: hidden; transition: all 0.2s;
}
.nav-map-section.collapsed .nav-map-section-content { display: none; }
```

---

## Navigation Map JS ⭐

```javascript
// ========== NAVIGATION MAP ==========
function openNavMap() {
  document.getElementById('navMapOverlay').classList.add('active');
}

function closeNavMap() {
  document.getElementById('navMapOverlay').classList.remove('active');
}

function closeNavMapOnOverlay(e) {
  if (e.target.id === 'navMapOverlay') {
    closeNavMap();
  }
}

// Navigate to screen from map
function navMapGo(screenId) {
  closeNavMap();
  navigateTo(screenId);
  showToast('→ ' + screenId.replace('screen-', ''));
}

// Navigate to endpoint (shows parent screen + toast)
function navMapEndpoint(name, parentScreen) {
  closeNavMap();
  if (parentScreen) {
    navigateTo(parentScreen);
  }
  setTimeout(() => {
    showToast('📌 ' + name + ' — финальная точка');
  }, 300);
}

// Navigate to tab (shows parent screen + tab message)
function navMapTab(name, parentScreen) {
  closeNavMap();
  if (parentScreen) {
    navigateTo(parentScreen);
  }
  setTimeout(() => {
    showToast('🟡 Таб "' + name + '" — переключает контент');
  }, 300);
}

// Toggle section collapse
function toggleSection(titleEl) {
  titleEl.parentElement.classList.toggle('collapsed');
}
```

---

## Nav Map Stats Calculation

Stats are populated from HTML content:

```javascript
function initNavMapStats() {
  const screens = document.querySelectorAll('.screen').length;
  const endpoints = document.querySelectorAll('.nav-map-item.endpoint-item').length;
  const statEls = document.querySelectorAll('.nav-map-stat-value');
  if (statEls[0]) statEls[0].textContent = screens;
  if (statEls[2]) statEls[2].textContent = endpoints;
}
```

Call in DOMContentLoaded or after content loads.

**Полных путей** (middle stat) = count of navigation chains from entry screen to deepest detail screen. Calculate manually based on mockup structure.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Phone (390px) |
| `2` | Tablet (820px) |
| `3` | Desktop (1280px) |
| `+` | Zoom In |
| `-` | Zoom Out |
| `0` | Reset Zoom |
| `M` | Open Navigation Map |
| `T` | Toggle Theme (auto/light/dark) |
| `L` | Cycle Language (RU → EN → DE) |
| `Esc` | Close Navigation Map |

---

*shell v1.8.0*
