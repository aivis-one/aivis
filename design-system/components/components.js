/* AIVIS design system -- behaviour of components, batch 1 (P5.1).
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

/* Batch 2 (P5.2). Tooltip: a tap on the trigger opens or closes it (no hover on a phone); Escape closes it; a tap elsewhere closes it;
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

/* Batch 3 (P5.3). No network, no storage; every text it shows comes from data-* attributes the page fills from its translation tables
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
