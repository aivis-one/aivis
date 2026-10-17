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
