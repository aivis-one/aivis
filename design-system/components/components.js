/* AIVIS design system -- behaviour of components, batch 1.
   Plain script, no dependency; it only wires what markup cannot do alone, by event delegation on the document.
   Tabs: arrow keys, Home and End move between tabs (automatic activation); the panel follows aria-selected.
   Filter chip: a click toggles aria-pressed. Removable chip and dismissible alert or toast: a click removes it.
   Password reveal: switches the input type and the accessible name; the two names come from the button's
   data-label-show and data-label-hide, which the page fills from its translation table (never English literals in a screen). */
(function () {
  'use strict';

  function select(tab) {
    var list = tab.closest('[role="tablist"]');
    if (!list) return;
    list.querySelectorAll('[role="tab"]').forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute('aria-controls'));
      if (panel) panel.hidden = !on;
    });
  }

  document.addEventListener('click', function (e) {
    var tab = e.target.closest('.ds-tab');
    if (tab && tab.getAttribute('aria-disabled') !== 'true') { select(tab); return; }

    var chip = e.target.closest('.ds-chip[aria-pressed]');
    if (chip && !chip.disabled && chip.getAttribute('aria-disabled') !== 'true') {
      chip.setAttribute('aria-pressed', chip.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      return;
    }

    var rm = e.target.closest('.ds-chip__remove');
    if (rm) { var c = rm.closest('.ds-chip'); if (c) c.remove(); return; }

    var close = e.target.closest('.ds-alert__close');
    if (close) { var a = close.closest('.ds-alert, .ds-toast'); if (a) a.remove(); return; }

    var reveal = e.target.closest('.ds-input-reveal');
    if (reveal) {
      var input = reveal.parentElement.querySelector('input');
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      reveal.setAttribute('aria-label', show ? reveal.dataset.labelHide : reveal.dataset.labelShow);
      var use = reveal.querySelector('use');
      if (use) use.setAttribute('href', show ? '#i-eye-off' : '#i-eye');
    }
  });

  document.addEventListener('keydown', function (e) {
    var tab = e.target.closest && e.target.closest('.ds-tab');
    if (!tab) return;
    var list = tab.closest('[role="tablist"]');
    var tabs = Array.prototype.filter.call(list.querySelectorAll('[role="tab"]'), function (t) {
      return t.getAttribute('aria-disabled') !== 'true';
    });
    var i = tabs.indexOf(tab);
    var rtl = getComputedStyle(list).direction === 'rtl';
    var next = null;
    if (e.key === 'ArrowRight') next = tabs[(i + (rtl ? -1 : 1) + tabs.length) % tabs.length];
    else if (e.key === 'ArrowLeft') next = tabs[(i + (rtl ? 1 : -1) + tabs.length) % tabs.length];
    else if (e.key === 'Home') next = tabs[0];
    else if (e.key === 'End') next = tabs[tabs.length - 1];
    if (next) { e.preventDefault(); next.focus(); select(next); }
  });
})();

/* Batch 2. Tooltip: a tap on the trigger opens or closes it (no hover on a phone); Escape closes it; a tap elsewhere closes it;
   the data-dismissed mark keeps an Escape-closed tooltip closed until the pointer or the focus leaves the anchor. */
(function () {
  'use strict';
  var ANCHOR = '.ds-tooltip-anchor';
  function closeAll(except) {
    document.querySelectorAll(ANCHOR + '[data-open="true"]').forEach(function (a) {
      if (a !== except) a.removeAttribute('data-open');
    });
  }
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest(ANCHOR + ' > .ds-tooltip-trigger');
    if (!trigger) { closeAll(null); return; }
    var anchor = trigger.parentElement;
    var touch = e.pointerType === 'touch' || (window.matchMedia && window.matchMedia('(hover: none)').matches);
    if (!touch) return;
    var open = anchor.getAttribute('data-open') === 'true';
    closeAll(anchor);
    if (open) anchor.removeAttribute('data-open'); else anchor.setAttribute('data-open', 'true');
    anchor.removeAttribute('data-dismissed');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll(ANCHOR).forEach(function (a) {
      var shown = a.getAttribute('data-open') === 'true' || a.matches(':hover') || a.matches(':focus-within');
      if (!shown) return;
      a.removeAttribute('data-open');
      a.setAttribute('data-dismissed', 'true');
    });
  });
  function clearDismissed(e) {
    var a = e.target.closest && e.target.closest(ANCHOR);
    if (a) a.removeAttribute('data-dismissed');
  }
  document.addEventListener('mouseout', function (e) {
    var a = e.target.closest && e.target.closest(ANCHOR);
    if (a && !a.contains(e.relatedTarget)) a.removeAttribute('data-dismissed');
  });
  document.addEventListener('focusout', clearDismissed);
})();

/* Batch 3. No network, no storage; every text it shows comes from data-* attributes the page fills from its translation tables
   (data-msg-*, data-label-*), and file sizes are formatted by Intl in the page language.
   OTP input (paste fills all, auto-advance, Backspace steps back), file input
   (type and size checks, local preview, progress set by the app), combobox (ARIA 1.2: aria-activedescendant), reorder list (move buttons).
   Events (all bubble, detail in event.detail): ds-otp-change, ds-otp-complete, ds-file-select, ds-file-reject, ds-file-remove,
   ds-combobox-query, ds-combobox-select, ds-reorder-change. The app listens; this file never submits and never uploads. */
(function () {
  'use strict';
  var uid = 0;
  function nid(p) { uid += 1; return 'ds-' + p + '-' + uid; }
  function emit(el, name, detail) { el.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail })); }
  function lang(el) { var l = el.closest('[lang]'); return (el.dataset && el.dataset.locale) || (l && l.getAttribute('lang')) || document.documentElement.lang || 'en'; }
  function fill(tpl, map) { return String(tpl || '').replace(/\{(\w+)\}/g, function (m, k) { return map[k] === undefined ? m : map[k]; }); }
  function icon(key) {
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('class', 'ds-icon'); s.setAttribute('aria-hidden', 'true'); s.setAttribute('viewBox', '0 0 24 24');
    var u = document.createElementNS('http://www.w3.org/2000/svg', 'use'); u.setAttribute('href', '#i-' + key); s.appendChild(u);
    return s;
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  /* ---------- K28 OTP input ---------- */
  function otpCells(root) { return Array.prototype.slice.call(root.querySelectorAll('.ds-otp__cell')); }
  function otpSync(root) {
    var cells = otpCells(root);
    var code = cells.map(function (c) { return c.value; }).join('');
    cells.forEach(function (c) { c.setAttribute('data-filled', c.value ? 'true' : 'false'); });
    root.setAttribute('data-value', code);
    emit(root, 'ds-otp-change', { value: code, complete: code.length === cells.length });
    if (code.length === cells.length) emit(root, 'ds-otp-complete', { value: code });
  }
  function otpPut(cells, from, digits) {
    var i = from;
    digits.split('').forEach(function (d) { if (i < cells.length) { cells[i].value = d; i += 1; } });
    return Math.min(i, cells.length - 1);
  }
  document.addEventListener('input', function (e) {
    var cell = e.target.closest && e.target.closest('.ds-otp__cell');
    if (!cell) return;
    var root = cell.closest('.ds-otp'), cells = otpCells(root), idx = cells.indexOf(cell);
    var digits = cell.value.replace(/\D/g, '');
    cell.value = '';
    if (!digits) { otpSync(root); return; }
    var next = otpPut(cells, idx, digits);
    var target = digits.length > 1 ? next : Math.min(idx + 1, cells.length - 1);
    cells[target].focus(); cells[target].select();
    otpSync(root);
  });
  document.addEventListener('paste', function (e) {
    var cell = e.target.closest && e.target.closest('.ds-otp__cell');
    if (!cell) return;
    var root = cell.closest('.ds-otp'), cells = otpCells(root);
    var digits = ((e.clipboardData && e.clipboardData.getData('text')) || '').replace(/\D/g, '').slice(0, cells.length);
    if (!digits) return;
    e.preventDefault();
    cells.forEach(function (c) { c.value = ''; });
    var last = otpPut(cells, 0, digits);
    cells[last].focus(); cells[last].select();
    otpSync(root);
  });
  document.addEventListener('keydown', function (e) {
    var cell = e.target.closest && e.target.closest('.ds-otp__cell');
    if (!cell) return;
    var root = cell.closest('.ds-otp'), cells = otpCells(root), idx = cells.indexOf(cell), to = null;
    if (e.key === 'Backspace' && !cell.value && idx > 0) { cells[idx - 1].value = ''; to = idx - 1; otpSync(root); }
    else if (e.key === 'ArrowLeft') to = Math.max(idx - 1, 0);          /* the group is a left-to-right island */
    else if (e.key === 'ArrowRight') to = Math.min(idx + 1, cells.length - 1);
    else if (e.key === 'Home') to = 0;
    else if (e.key === 'End') to = cells.length - 1;
    if (to !== null) { e.preventDefault(); cells[to].focus(); cells[to].select(); }
  });
  document.addEventListener('focusin', function (e) { if (e.target.classList && e.target.classList.contains('ds-otp__cell')) e.target.select(); });

  /* ---------- K30 File input ---------- */
  function sizeText(root, bytes) {
    var loc = lang(root), unit = 'byte', v = bytes;
    if (bytes >= 1048576) { unit = 'megabyte'; v = bytes / 1048576; } else if (bytes >= 1024) { unit = 'kilobyte'; v = bytes / 1024; }
    try { return new Intl.NumberFormat(loc, { style: 'unit', unit: unit, unitDisplay: 'short', maximumFractionDigits: 1 }).format(v); } catch (x) { return String(Math.round(v)); }
  }
  function acceptOk(root, file) {
    var list = (root.dataset.accept || '').split(',').map(function (s) { return s.trim().toLowerCase(); }).filter(Boolean);
    if (!list.length) return true;
    var name = file.name.toLowerCase(), type = (file.type || '').toLowerCase();
    return list.some(function (a) {
      if (a.charAt(0) === '.') return name.slice(-a.length) === a;
      if (a.slice(-2) === '/*') return type.indexOf(a.slice(0, -1)) === 0;
      return type === a;
    });
  }
  function fileItem(root, file, problem) {
    var li = el('li', 'ds-file__item'); li.id = nid('file');
    li._file = file;
    var thumb = el('span', 'ds-file__thumb');
    if (!problem && file.type && file.type.indexOf('image/') === 0 && window.URL && URL.createObjectURL) {
      var img = el('img'); img.alt = ''; img.src = URL.createObjectURL(file); li._url = img.src; thumb.appendChild(img);
    } else thumb.appendChild(icon(file.type && file.type.indexOf('image/') === 0 ? 'image' : 'file-text'));
    var body = el('span', 'ds-file__body');
    body.appendChild(el('span', 'ds-file__name', file.name));
    var meta = el('span', 'ds-file__meta', sizeText(root, file.size) + (problem ? '' : ' · ' + (root.dataset.msgReady || '')));
    meta.className = 'ds-file__meta ds-file__status'; body.appendChild(meta);
    var aside = el('span', 'ds-file__aside');
    var rm = el('button', 'ds-file__remove'); rm.type = 'button'; rm.setAttribute('aria-label', fill(root.dataset.labelRemove, { name: file.name })); rm.appendChild(icon('x'));
    aside.appendChild(rm);
    li.appendChild(thumb); li.appendChild(body); li.appendChild(aside);
    if (problem) {
      li.setAttribute('data-state', 'error');
      var er = el('p', 'ds-field__error'); er.setAttribute('role', 'alert'); er.appendChild(icon('alert-triangle')); er.appendChild(el('span', '', problem));
      li.appendChild(er);
    } else li.setAttribute('data-state', 'selected');
    return li;
  }
  function takeFiles(root, files) {
    var list = root.querySelector('.ds-file__list'), input = root.querySelector('.ds-file__input');
    var max = +root.dataset.maxSize || 0, multi = input.multiple;
    Array.prototype.forEach.call(files, function (f) {
      var problem = null;
      if (!acceptOk(root, f)) problem = fill(root.dataset.msgType, { name: f.name });
      else if (max && f.size > max) problem = fill(root.dataset.msgSize, { name: f.name, max: sizeText(root, max) });
      if (!multi) { Array.prototype.slice.call(list.children).forEach(function (c) { dropItem(c); }); }
      var li = fileItem(root, f, problem); list.appendChild(li);
      emit(root, problem ? 'ds-file-reject' : 'ds-file-select', { file: f, item: li, reason: problem });
    });
    input.value = '';
  }
  function dropItem(li) { if (li._url && URL.revokeObjectURL) URL.revokeObjectURL(li._url); li.remove(); }
  document.addEventListener('change', function (e) {
    var input = e.target.closest && e.target.closest('.ds-file__input');
    if (input) takeFiles(input.closest('.ds-file'), input.files);
  });
  document.addEventListener('click', function (e) {
    var rm = e.target.closest('.ds-file__remove');
    if (!rm) return;
    var li = rm.closest('.ds-file__item'), root = li.closest('.ds-file');
    emit(root, 'ds-file-remove', { file: li._file, item: li });
    dropItem(li);
    var input = root.querySelector('.ds-file__input'); if (input) input.focus();
  });
  /* the app drives the upload and reports back through these three calls */
  window.AivisDS = window.AivisDS || {};
  window.AivisDS.file = {
    progress: function (li, pct) {
      if (!li.isConnected) return;   /* the row was removed while the app was still reporting */
      var root = li.closest('.ds-file'), p = li.querySelector('.ds-file__progress');
      li.setAttribute('data-state', 'uploading');
      if (!p) {
        p = el('div', 'ds-progress ds-file__progress'); var tr = el('div', 'ds-progress__track'); tr.setAttribute('role', 'progressbar');
        tr.setAttribute('aria-label', li._file.name); tr.setAttribute('aria-valuemin', '0'); tr.setAttribute('aria-valuemax', '100');
        tr.appendChild(el('span', 'ds-progress__fill')); p.appendChild(tr); li.appendChild(p);
      }
      var t = p.querySelector('.ds-progress__track'); t.setAttribute('aria-valuenow', String(Math.round(pct)));
      p.querySelector('.ds-progress__fill').style.setProperty('--value', pct + '%');
      var s = li.querySelector('.ds-file__status'); if (s) s.textContent = sizeText(root, li._file.size) + ' · ' + Math.round(pct) + '%';
    },
    done: function (li) {
      if (!li.isConnected) return;   /* the row was removed while the app was still reporting */
      var root = li.closest('.ds-file'), p = li.querySelector('.ds-file__progress'); if (p) p.remove();
      li.setAttribute('data-state', 'done');
      var s = li.querySelector('.ds-file__status'); if (s) s.textContent = sizeText(root, li._file.size) + ' · ' + (root.dataset.msgDone || '');
    },
    fail: function (li, message) {
      if (!li.isConnected) return;   /* the row was removed while the app was still reporting */
      var p = li.querySelector('.ds-file__progress'); if (p) p.remove();
      li.setAttribute('data-state', 'error');
      var er = el('p', 'ds-field__error'); er.setAttribute('role', 'alert'); er.appendChild(icon('alert-triangle')); er.appendChild(el('span', '', message)); li.appendChild(er);
    }
  };

  /* ---------- K38 Combobox ---------- */
  function cbParts(root) {
    return { input: root.querySelector('.ds-combobox__input'), list: root.querySelector('.ds-combobox__list'),
      status: root.querySelector('.ds-combobox__status'), chip: root.querySelector('.ds-combobox__chip'),
      control: root.querySelector('.ds-combobox__control'), empty: root.querySelector('.ds-combobox__empty') };
  }
  function cbVisible(root) { return Array.prototype.filter.call(root.querySelectorAll('.ds-combobox__option'), function (o) { return !o.hidden && o.getAttribute('aria-disabled') !== 'true'; }); }
  function cbActive(root, opt) {
    var p = cbParts(root);
    root.querySelectorAll('.ds-combobox__option[data-active]').forEach(function (o) { o.removeAttribute('data-active'); });
    if (opt) { opt.setAttribute('data-active', 'true'); p.input.setAttribute('aria-activedescendant', opt.id); opt.scrollIntoView({ block: 'nearest' }); }
    else p.input.removeAttribute('aria-activedescendant');
  }
  function cbOpen(root, on) {
    var p = cbParts(root);
    p.list.hidden = !on; p.input.setAttribute('aria-expanded', on ? 'true' : 'false');
    if (!on) cbActive(root, null);
  }
  function cbFilter(root) {
    var p = cbParts(root), q = p.input.value.trim().toLowerCase(), min = +root.dataset.minChars || 0, n = 0;
    root.querySelectorAll('.ds-combobox__option').forEach(function (o, i) {
      if (!o.id) o.id = nid('opt');
      var show = q.length >= min && (root.dataset.filter !== 'local' || !q || o.textContent.toLowerCase().indexOf(q) !== -1);
      o.hidden = !show; if (show) n += 1;
    });
    if (p.empty) p.empty.hidden = n !== 0 || q.length < min;
    if (p.status) p.status.textContent = q.length >= min ? fill(n ? root.dataset.msgCount : root.dataset.msgNone, { n: n }) : '';
    cbOpen(root, q.length >= min);
    cbActive(root, null);
    emit(root, 'ds-combobox-query', { query: p.input.value });
  }
  function cbSelect(root, opt) {
    var p = cbParts(root);
    root.querySelectorAll('.ds-combobox__option[aria-selected="true"]').forEach(function (o) { o.setAttribute('aria-selected', 'false'); });
    opt.setAttribute('aria-selected', 'true'); root.dataset.value = opt.getAttribute('data-value') || '';
    if (p.chip) {
      var slot = p.chip.querySelector('.ds-combobox__chip-slot'); slot.textContent = '';
      Array.prototype.forEach.call(opt.children, function (c) { if (!c.classList.contains('ds-combobox__tick')) slot.appendChild(c.cloneNode(true)); });
      p.chip.hidden = false; p.control.hidden = true;
      var clr = p.chip.querySelector('.ds-combobox__clear'); if (clr) clr.focus();
    } else { p.input.value = opt.querySelector('.ds-combobox__name') ? opt.querySelector('.ds-combobox__name').textContent : opt.textContent.trim(); }
    cbOpen(root, false); p.input.value = p.chip ? '' : p.input.value;
    emit(root, 'ds-combobox-select', { value: root.dataset.value, option: opt });
  }
  document.addEventListener('input', function (e) { var i = e.target.closest && e.target.closest('.ds-combobox__input'); if (i) cbFilter(i.closest('.ds-combobox')); });
  document.addEventListener('keydown', function (e) {
    var i = e.target.closest && e.target.closest('.ds-combobox__input');
    if (!i) return;
    var root = i.closest('.ds-combobox'), p = cbParts(root), opts = cbVisible(root);
    var cur = root.querySelector('.ds-combobox__option[data-active="true"]'), k = opts.indexOf(cur);
    if (e.key === 'ArrowDown') { e.preventDefault(); if (p.list.hidden) { cbFilter(root); opts = cbVisible(root); } if (opts.length) cbActive(root, opts[(k + 1) % opts.length]); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (!p.list.hidden && opts.length) cbActive(root, opts[(k - 1 + opts.length) % opts.length]); }
    else if (e.key === 'Home' && !p.list.hidden && cur) { e.preventDefault(); cbActive(root, opts[0]); }
    else if (e.key === 'End' && !p.list.hidden && cur) { e.preventDefault(); cbActive(root, opts[opts.length - 1]); }
    else if (e.key === 'Enter' && cur) { e.preventDefault(); cbSelect(root, cur); }
    else if (e.key === 'Escape') { if (!p.list.hidden) { e.preventDefault(); cbOpen(root, false); } else if (i.value) { i.value = ''; } }
  });
  document.addEventListener('mousedown', function (e) { if (e.target.closest && e.target.closest('.ds-combobox__option')) e.preventDefault(); });
  document.addEventListener('click', function (e) {
    var o = e.target.closest('.ds-combobox__option');
    if (o && o.getAttribute('aria-disabled') !== 'true') { cbSelect(o.closest('.ds-combobox'), o); return; }
    var c = e.target.closest('.ds-combobox__clear');
    if (c) {
      var root = c.closest('.ds-combobox'), p = cbParts(root);
      p.input.value = ''; root.dataset.value = '';
      root.querySelectorAll('.ds-combobox__option[aria-selected="true"]').forEach(function (x) { x.setAttribute('aria-selected', 'false'); });
      if (p.chip) { p.chip.hidden = true; p.control.hidden = false; }
      cbOpen(root, false); p.input.focus(); emit(root, 'ds-combobox-select', { value: '', option: null }); return;
    }
    document.querySelectorAll('.ds-combobox__input[aria-expanded="true"]').forEach(function (i) { var r = i.closest('.ds-combobox'); if (!r.contains(e.target)) cbOpen(r, false); });
  });
  document.addEventListener('focusin', function (e) {
    document.querySelectorAll('.ds-combobox__input[aria-expanded="true"]').forEach(function (i) { var r = i.closest('.ds-combobox'); if (!r.contains(e.target)) cbOpen(r, false); });
  });

  /* ---------- K39 Reorder list ---------- */
  function roRefresh(list) {
    var items = Array.prototype.slice.call(list.querySelectorAll(':scope > .ds-reorder__item'));
    items.forEach(function (li, i) {
      var name = li.dataset.name || (li.querySelector('.ds-reorder__title') || {}).textContent || '';
      var pos = li.querySelector('.ds-reorder__pos'); if (pos) pos.textContent = String(i + 1);
      var up = li.querySelector('[data-dir="-1"]'), dn = li.querySelector('[data-dir="1"]');
      if (up) { up.disabled = i === 0; up.setAttribute('aria-label', fill(list.dataset.labelUp, { name: name })); }
      if (dn) { dn.disabled = i === items.length - 1; dn.setAttribute('aria-label', fill(list.dataset.labelDown, { name: name })); }
    });
    return items;
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.ds-reorder__move');
    if (!b || b.disabled) return;
    var li = b.closest('.ds-reorder__item'), list = li.parentElement, dir = +b.dataset.dir;
    var sib = dir < 0 ? li.previousElementSibling : li.nextElementSibling;
    if (!sib) return;
    if (dir < 0) list.insertBefore(li, sib); else list.insertBefore(sib, li);
    list.querySelectorAll('[data-moved]').forEach(function (x) { x.removeAttribute('data-moved'); });
    li.setAttribute('data-moved', 'true');
    var items = roRefresh(list), n = items.indexOf(li) + 1, name = li.dataset.name || li.querySelector('.ds-reorder__title').textContent;
    var live = document.getElementById(list.dataset.live);
    if (live) live.textContent = fill(list.dataset.msgMoved, { name: name, n: n, total: items.length });
    var keep = li.querySelector('[data-dir="' + dir + '"]');
    (keep && !keep.disabled ? keep : li.querySelector('.ds-reorder__move:not(:disabled)')).focus();
    emit(list, 'ds-reorder-change', { order: items.map(function (x) { return x.dataset.id || x.id; }) });
  });
  document.addEventListener('focusout', function (e) {
    var li = e.target.closest && e.target.closest('.ds-reorder__item');
    if (li && !li.contains(e.relatedTarget)) li.removeAttribute('data-moved');
  });
  document.querySelectorAll('.ds-reorder').forEach(roRefresh);
})();

/* Batch 4. No network, no storage; every text it shows comes from data-* attributes the page fills from its translation tables
   (data-msg-*, data-label-*). Action menu (the menu button pattern: Enter, Space and Down open, arrows, Home, End, a typed letter, Escape
   returns the focus to the button, Tab closes), document viewer (a dialog: the focus moves in, Tab stays inside, Escape and the scrim close,
   the focus returns to what opened it), document row (the download state), invoice block (the copy button and its polite status).
   Events (all bubble, detail in event.detail): ds-menu-select, ds-menu-open, ds-menu-close, ds-docviewer-open, ds-docviewer-close,
   ds-docrow-download, ds-copy. The app listens; this file never fetches, uploads or stores. AivisDS.docrow.done(row) and .fail(row)
   finish a download the app drove. */
(function () {
  'use strict';
  function emit(el, name, detail) { el.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail })); }

  /* ---------- K26 Action menu ---------- */
  function menuItems(menu) { return Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"], [role="option"]')).filter(function (i) { return i.getAttribute('aria-disabled') !== 'true'; }); }
  function menuClose(menu, refocus) {
    var btn = menu.querySelector('.ds-menu__button'), list = menu.querySelector('.ds-menu__list');
    if (!btn || !list || list.hidden) return;
    list.hidden = true; btn.setAttribute('aria-expanded', 'false');
    if (refocus) btn.focus();
    emit(menu, 'ds-menu-close', {});
  }
  function menuOpen(menu, which) {
    var btn = menu.querySelector('.ds-menu__button'), list = menu.querySelector('.ds-menu__list');
    if (!btn || !list || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
    document.querySelectorAll('.ds-menu').forEach(function (m) { if (m !== menu) menuClose(m, false); });
    list.hidden = false; btn.setAttribute('aria-expanded', 'true');
    var items = menuItems(menu);
    menuItems(menu).forEach(function (i) { i.tabIndex = -1; });
    var chosen = items.filter(function (i) { return i.getAttribute('aria-selected') === 'true'; })[0];
    if (items.length) (which === 'last' ? items[items.length - 1] : (chosen || items[0])).focus();
    emit(menu, 'ds-menu-open', {});
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.ds-menu__button');
    if (btn) {
      var menu = btn.closest('.ds-menu');
      if (btn.getAttribute('aria-expanded') === 'true') menuClose(menu, false); else menuOpen(menu, 'first');
      return;
    }
    var item = e.target.closest('.ds-menu__item');
    if (item) {
      if (item.getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; }
      var m = item.closest('.ds-menu');
      if (item.getAttribute('role') === 'option') {
        m.querySelectorAll('[role="option"]').forEach(function (o) { o.setAttribute('aria-selected', o === item ? 'true' : 'false'); });
        var shown = m.querySelector('.ds-menu__value'), name = item.querySelector('.ds-menu__label');
        if (shown && name) shown.textContent = name.textContent;
      }
      emit(m, 'ds-menu-select', { value: item.dataset.value || item.textContent.trim(), item: item });
      menuClose(m, true);
      return;
    }
    document.querySelectorAll('.ds-menu').forEach(function (mm) { menuClose(mm, false); });
  });
  document.addEventListener('keydown', function (e) {
    var btn = e.target.closest && e.target.closest('.ds-menu__button');
    if (btn) {
      var menu = btn.closest('.ds-menu');
      if (e.key === 'ArrowDown') { e.preventDefault(); menuOpen(menu, 'first'); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); menuOpen(menu, 'last'); }
      return;
    }
    var item = e.target.closest && e.target.closest('.ds-menu__item');
    if (!item) return;
    var m = item.closest('.ds-menu'), items = menuItems(m), i = items.indexOf(item);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); menuClose(m, true); }
    else if (e.key === 'Tab') { menuClose(m, false); }
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      var k = e.key.toLowerCase(), n = items.filter(function (x) { return x.textContent.trim().toLowerCase().indexOf(k) === 0; });
      if (n.length) { var at = n.indexOf(item); n[(at + 1) % n.length].focus(); }
    }
  });

  /* ---------- K36 Document viewer ---------- */
  var viewerOpener = null;
  function focusables(root) {
    return Array.prototype.slice.call(root.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), iframe')).filter(function (x) { return !x.closest('[hidden]'); });
  }
  function viewerOpen(v, opener) {
    if (!v) return;
    viewerOpener = opener || document.activeElement;
    v.hidden = false;
    var d = v.querySelector('.ds-docviewer__dialog');
    if (d) d.focus();
    emit(v, 'ds-docviewer-open', {});
  }
  function viewerClose(v) {
    if (!v || v.hidden) return;
    v.hidden = true;
    var o = viewerOpener; viewerOpener = null;
    if (o && o.isConnected) o.focus();
    emit(v, 'ds-docviewer-close', {});
  }
  document.addEventListener('click', function (e) {
    var op = e.target.closest('[data-docviewer-open]');
    if (op) { viewerOpen(document.getElementById(op.getAttribute('data-docviewer-open')), op); return; }
    var cl = e.target.closest('[data-docviewer-close]');
    if (cl) { viewerClose(cl.closest('.ds-docviewer')); return; }
    if (e.target.classList && e.target.classList.contains('ds-docviewer') && !e.target.classList.contains('ds-docviewer--inline')) viewerClose(e.target);
  });
  document.addEventListener('keydown', function (e) {
    var v = e.target.closest && e.target.closest('.ds-docviewer:not(.ds-docviewer--inline):not([hidden])');
    if (!v) return;
    if (e.key === 'Escape') { e.preventDefault(); viewerClose(v); return; }
    if (e.key !== 'Tab') return;
    var f = focusables(v.querySelector('.ds-docviewer__dialog'));
    if (!f.length) { e.preventDefault(); return; }
    var first = f[0], last = f[f.length - 1], dlg = v.querySelector('.ds-docviewer__dialog');
    if (e.shiftKey && (document.activeElement === first || document.activeElement === dlg)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ---------- K44 Document row ---------- */
  function rowStatus(row, key) {
    var s = row.querySelector('.ds-docrow__status');
    if (s) s.textContent = row.getAttribute('data-msg-' + key) || '';
  }
  function rowIcon(row, key) {
    var u = row.querySelector('.ds-docrow__state use');
    if (u) u.setAttribute('href', '#i-' + key);
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('.ds-docrow .ds-row__link');
    if (!a) return;
    var row = a.closest('.ds-docrow');
    row.setAttribute('data-state', 'downloading'); rowStatus(row, 'downloading');
    emit(row, 'ds-docrow-download', { href: a.getAttribute('href'), row: row });
  });
  window.AivisDS = window.AivisDS || {};
  window.AivisDS.docrow = {
    done: function (row) { row.setAttribute('data-state', 'downloaded'); rowIcon(row, 'check'); rowStatus(row, 'downloaded'); },
    fail: function (row) { row.removeAttribute('data-state'); rowIcon(row, 'download'); rowStatus(row, 'failed'); }
  };

  /* ---------- K43 Copy button ---------- */
  var copyTimers = new WeakMap();
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-copy-target]');
    if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true') return;
    var src = document.getElementById(b.getAttribute('data-copy-target')), box = b.closest('.ds-invoice, .ds-copy') || document;
    var status = box.querySelector('.ds-invoice__status, .ds-copy__status'), label = b.querySelector('.ds-invoice__copy-label, .ds-copy__label'), use = b.querySelector('use');
    if (!src) return;
    var text = src.textContent.trim();
    function ok() {
      b.setAttribute('data-state', 'copied');
      if (label) { if (!b.dataset.labelRest) b.dataset.labelRest = label.textContent; label.textContent = b.dataset.labelCopied || label.textContent; }
      if (use) use.setAttribute('href', '#i-check');
      if (status) status.textContent = b.dataset.msgCopied || '';
      emit(b, 'ds-copy', { text: text });
      clearTimeout(copyTimers.get(b));
      copyTimers.set(b, setTimeout(function () {
        b.removeAttribute('data-state');
        if (label && b.dataset.labelRest) label.textContent = b.dataset.labelRest;
        if (use) use.setAttribute('href', '#i-copy');
      }, 3000));
    }
    function fail() { if (status) status.textContent = b.dataset.msgFailed || ''; }
    function fallback() {
      try {
        var r = document.createRange(); r.selectNodeContents(src);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        if (document.execCommand('copy')) ok(); else fail();
      } catch (x) { fail(); }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
  });
})();

/* Additions to batch 4. Dialog (K52: a dialog for a confirm, an edit or details: the focus moves in, Tab stays inside, Escape and the scrim close,
   the focus returns to what opened it; data-lock on the .ds-dialog keeps the scrim from closing it), and the FAQ of the Accordion (K27: a search
   that hides the items that do not match, and a list built from the headings of a document). No network, no storage; every text comes from data-*
   attributes. Events: ds-dialog-open, ds-dialog-close. The listbox and the copy button are in the blocks above. */
(function () {
  'use strict';
  function emit(el, name, detail) { el.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail })); }

  /* ---------- K52 Dialog ---------- */
  var dialogOpener = null;
  function focusables(root) {
    return Array.prototype.slice.call(root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(function (x) { return !x.closest('[hidden]'); });
  }
  function dialogOpen(d, opener) {
    if (!d) return;
    dialogOpener = opener || document.activeElement;
    d.hidden = false;
    var p = d.querySelector('.ds-dialog__panel');
    if (p) p.focus();
    emit(d, 'ds-dialog-open', {});
  }
  function dialogClose(d) {
    if (!d || d.hidden) return;
    d.hidden = true;
    var o = dialogOpener; dialogOpener = null;
    if (o && o.isConnected) o.focus();
    emit(d, 'ds-dialog-close', {});
  }
  document.addEventListener('click', function (e) {
    var op = e.target.closest('[data-dialog-open]');
    if (op) { dialogOpen(document.getElementById(op.getAttribute('data-dialog-open')), op); return; }
    var cl = e.target.closest('[data-dialog-close]');
    if (cl) { dialogClose(cl.closest('.ds-dialog')); return; }
    var t = e.target;
    if (t.classList && t.classList.contains('ds-dialog') && !t.classList.contains('ds-dialog--inline')) { if (t.getAttribute('data-lock') === 'true') { var lp = t.querySelector('.ds-dialog__panel'); if (lp) lp.focus(); } else dialogClose(t); }
  });
  document.addEventListener('keydown', function (e) {
    var d = e.target.closest && e.target.closest('.ds-dialog:not(.ds-dialog--inline):not([hidden])');
    if (!d) return;
    if (e.key === 'Escape') { e.preventDefault(); dialogClose(d); return; }
    if (e.key !== 'Tab') return;
    var panel = d.querySelector('.ds-dialog__panel'), f = focusables(panel);
    if (!f.length) { e.preventDefault(); return; }
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ---------- K27 FAQ: the search ---------- */
  function faqFilter(input) {
    var list = document.getElementById(input.getAttribute('aria-controls'));
    if (!list) return;
    var q = input.value.trim().toLowerCase(), shown = 0;
    list.querySelectorAll('.ds-accordion__item').forEach(function (item) {
      var hit = !q || item.textContent.toLowerCase().indexOf(q) !== -1;
      item.hidden = !hit;
      if (hit) shown += 1;
    });
    var none = list.parentNode.querySelector('.ds-accordion__none');
    if (none) none.hidden = shown !== 0;
  }
  document.addEventListener('input', function (e) { var i = e.target.closest && e.target.closest('[data-faq-search]'); if (i) faqFilter(i); });

  /* ---------- K27 FAQ: the list read from the headings of a document ---------- */
  /* AivisDS.faq.fromHeadings(source, level) reads the headings of the given level (h2 by default) of a document fragment and the nodes after each
     up to the next heading of that level, and returns a div.ds-accordion of details (one open at a time, by one shared name). It copies; the source stays. */
  var faqCount = 0;
  function fromHeadings(source, level) {
    var tag = (level || 'h2').toUpperCase(), name = 'ds-faq-' + (faqCount += 1);
    var root = document.createElement('div'); root.className = 'ds-accordion ds-accordion--faq';
    var item = null, panel = null;
    Array.prototype.slice.call(source.childNodes).forEach(function (n) {
      if (n.nodeType === 1 && n.tagName === tag) {
        item = document.createElement('details'); item.className = 'ds-accordion__item'; item.setAttribute('name', name);
        var s = document.createElement('summary'); s.className = 'ds-accordion__summary';
        var t = document.createElement('span'); t.textContent = n.textContent.trim(); s.appendChild(t);
        s.insertAdjacentHTML('beforeend', '<svg class="ds-icon ds-icon--md ds-accordion__chev" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-chevron-down"/></svg>');
        panel = document.createElement('div'); panel.className = 'ds-accordion__panel';
        item.appendChild(s); item.appendChild(panel); root.appendChild(item);
      } else if (panel) { panel.appendChild(n.cloneNode(true)); }
    });
    return root;
  }
  window.AivisDS = window.AivisDS || {};
  window.AivisDS.faq = { fromHeadings: fromHeadings };
  document.querySelectorAll('[data-faq-source]').forEach(function (src) {
    var built = fromHeadings(src, src.getAttribute('data-faq-source') || 'h2');
    src.textContent = ''; src.appendChild(built);
  });
})();

/* ---------- K25 App shell: the collapse control of the labelled rail ----------
   A click on [data-nav-toggle] folds the rail to icons only and back: it sets data-nav="collapsed" on the closest .ds-shell (removes it to unfold),
   keeps aria-expanded on the button and switches its accessible name between data-label-collapse and data-label-expand (the page fills both from its
   translation table). It saves nothing: the event ds-nav-toggle (detail.collapsed) is for the app, which keeps the state where it keeps its settings and
   sets data-nav on load. */
(function () {
  'use strict';
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-nav-toggle]');
    if (!btn) return;
    var shell = btn.closest('.ds-shell');
    if (!shell) return;
    var collapsed = shell.getAttribute('data-nav') !== 'collapsed';
    if (collapsed) shell.setAttribute('data-nav', 'collapsed'); else shell.removeAttribute('data-nav');
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    var label = collapsed ? btn.getAttribute('data-label-expand') : btn.getAttribute('data-label-collapse');
    if (label) btn.setAttribute('aria-label', label);
    btn.dispatchEvent(new CustomEvent('ds-nav-toggle', { bubbles: true, detail: { collapsed: collapsed } }));
  });
})();
