/* AIVIS.ONE company site v2 -- assets/site.js
   Behaviour that is about THIS page: the mobile drawer (a real dialog with a
   focus trap) and the theme toggle. The theme write goes through
   window.ls.motion.bind.themeSwap (animation pack technique trn-same-doc);
   the localStorage write stays outside that callback. Storage may be absent or
   throw: the page then follows the system preference and still renders.
   No network, no third-party code. */
(function (ls) {
  'use strict';
  var THEME_KEY = 'aivis-theme';

  function focusableIn(root) {
    var nodes = root.querySelectorAll('a[href], button:not([disabled]), [tabindex]');
    var out = [];
    for (var i = 0; i < nodes.length; i++) { if (nodes[i].tabIndex !== -1) { out.push(nodes[i]); } }
    return out;
  }

  function setInert(el, on) {
    if (!el) { return; }
    try { el.inert = on; } catch (e) { /* engine without inert: aria-hidden below still covers it */ }
    if (on) { el.setAttribute('aria-hidden', 'true'); } else { el.removeAttribute('aria-hidden'); }
  }

  function initDrawer() {
    var toggle = document.querySelector('[data-ls-menu-open]');
    var drawer = document.querySelector('[data-ls-drawer]');
    if (!toggle || !drawer) { return; }
    var close = drawer.querySelector('[data-ls-menu-close]');
    var main = document.getElementById('ls-main');
    var footer = document.querySelector('.foot');
    var header = document.querySelector('.site-header');
    var isOpen = false;

    function open() {
      if (isOpen) { return; }
      isOpen = true;
      drawer.classList.add('is-open');
      toggle.setAttribute('aria-expanded', 'true');
      setInert(main, true); setInert(footer, true); setInert(header, true);
      (close || focusableIn(drawer)[0] || drawer).focus();
    }
    function shut() {
      if (!isOpen) { return; }
      isOpen = false;
      drawer.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      setInert(main, false); setInert(footer, false); setInert(header, false);
      toggle.focus();
    }
    toggle.addEventListener('click', function () { if (isOpen) { shut(); } else { open(); } });
    if (close) { close.addEventListener('click', shut); }
    Array.prototype.forEach.call(drawer.querySelectorAll('a'), function (a) { a.addEventListener('click', shut); });
    document.addEventListener('keydown', function (e) {
      if (!isOpen) { return; }
      if (e.key === 'Escape') { shut(); return; }
      if (e.key !== 'Tab') { return; }
      var f = focusableIn(drawer);
      if (!f.length) { e.preventDefault(); return; }
      var first = f[0], last = f[f.length - 1], active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !drawer.contains(active)) { e.preventDefault(); last.focus(); }
      } else if (active === last || !drawer.contains(active)) { e.preventDefault(); first.focus(); }
    });
    /* a drawer left open across a resize to the desktop layout must not trap the page */
    if (window.matchMedia) {
      var mq = window.matchMedia('(min-width: 880px)');
      var onChange = function (ev) { if (ev.matches) { shut(); } };
      if (mq.addEventListener) { mq.addEventListener('change', onChange); } else if (mq.addListener) { mq.addListener(onChange); }
    }
  }

  function initTheme() {
    var btns = document.querySelectorAll('[data-ls-theme-toggle]');
    if (!btns.length) { return; }
    var root = document.documentElement;
    function paint(theme) {
      root.setAttribute('data-theme', theme);
      Array.prototype.forEach.call(btns, function (b) { b.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false'); });
    }
    paint(root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
    Array.prototype.forEach.call(btns, function (btn) { btn.addEventListener('click', toggle); });
    function toggle() {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      var swap = ls.motion && ls.motion.bind && ls.motion.bind.themeSwap;
      if (swap) {
        var tr = swap(function () { paint(next); });
        /* an aborted view transition (tab hidden, a second toggle mid-flight) rejects these promises; the theme is already set, so the rejection is swallowed */
        if (tr) { ['ready', 'finished', 'updateCallbackDone'].forEach(function (k) { if (tr[k] && tr[k].catch) { tr[k].catch(function () {}); } }); }
      } else { paint(next); }
      try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* storage blocked: the choice lasts for this visit only */ }
    }
  }

  /* the language dropdown is a native <details>: it opens and closes without script;
     this only closes it on an outside click, on Escape and on a click of a language */
  function initLang() {
    var box = document.querySelector('[data-ls-lang]');
    if (!box) { return; }
    document.addEventListener('click', function (e) { if (box.open && !box.contains(e.target)) { box.open = false; } });
    /* focus leaving the control (Tab past the list) closes it; a null relatedTarget is a click elsewhere, which the handler above covers */
    box.addEventListener('focusout', function (e) { if (box.open && e.relatedTarget && !box.contains(e.relatedTarget)) { box.open = false; } });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && box.open) { box.open = false; var b = box.querySelector('summary'); if (b) { b.focus(); } }
    });
  }

  function init() { initDrawer(); initTheme(); initLang(); }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})(window.ls = window.ls || {});
