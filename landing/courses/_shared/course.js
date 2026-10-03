/* AIVIS.ONE course template: navigation, theme, scaling, copy. No network, no storage beyond one optional preference (the theme). The page language is the page address. */
(function () {
  'use strict';
  var root = document.documentElement;
  var deck = document.getElementById('deck');
  var stage = document.getElementById('stage');
  var box = document.getElementById('stageBox');
  var wrap = document.getElementById('stageWrap');
  var slides = [].slice.call(stage.querySelectorAll('.slide'));
  var total = slides.length;
  var cur = 0;
  var prevB = document.getElementById('prev');
  var nextB = document.getElementById('next');
  var counter = document.getElementById('counter');
  var bar = document.getElementById('progressBar');
  var cue = document.getElementById('moreCue');
  var PHONE = window.matchMedia('(max-aspect-ratio: 1/1), (max-width: 720px), (max-height: 520px)');

  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  /* ---------- scale the 16:9 slide to the window (desktop only) ---------- */
  function fit() {
    if (PHONE.matches) { root.style.setProperty('--sc', '1'); return; }
    var w = wrap.clientWidth - 48, h = wrap.clientHeight - 16;
    var s = Math.min(w / 1280, h / 720);
    root.style.setProperty('--sc', String(Math.max(0.3, s)));
  }
  window.addEventListener('resize', fit);
  if (PHONE.addEventListener) PHONE.addEventListener('change', fit);

  /* ---------- slides ---------- */
  function show(i, dir) {
    i = Math.max(0, Math.min(total - 1, i));
    if (i === cur && slides[i].classList.contains('active')) return;
    stage.setAttribute('data-dir', dir || (i < cur ? 'prev' : 'next'));
    slides.forEach(function (s, k) { s.classList.toggle('active', k === i); s.scrollTop = 0; });
    cur = i;
    counter.textContent = (i + 1) + ' / ' + total;
    bar.style.width = (((i + 1) / total) * 100) + '%';
    prevB.disabled = i === 0;
    nextB.disabled = i === total - 1;
    try { history.replaceState(null, '', '#' + (i + 1)); } catch (e) {}
    more();
  }
  /* mark a card that has more to scroll */
  function more() {
    var any = false;
    slides.forEach(function (s) {
      var m = s.classList.contains('active') && s.scrollHeight - s.clientHeight - s.scrollTop > 8;
      s.classList.toggle('more', m); if (m) any = true;
    });
    box.classList.toggle('has-more', any && PHONE.matches);
  }
  cue.addEventListener('click', function () {
    var s = slides[cur];
    s.scrollBy({ top: Math.max(120, s.clientHeight * 0.75), behavior: 'smooth' });
  });
  slides.forEach(function (s) { s.addEventListener('scroll', more, { passive: true }); });
  window.addEventListener('resize', more);
  function next() { show(cur + 1, 'next'); }
  function prev() { show(cur - 1, 'prev'); }
  prevB.addEventListener('click', prev);
  nextB.addEventListener('click', next);

  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var t = e.target && e.target.tagName;
    var k = e.key;
    if (langBox.contains(e.target)) return;
    if (k === 'ArrowRight' || k === 'PageDown' || (k === ' ' && t !== 'BUTTON' && t !== 'A')) { e.preventDefault(); next(); }
    else if (k === 'ArrowLeft' || k === 'PageUp') { e.preventDefault(); prev(); }
    else if (k === 'Home') { e.preventDefault(); show(0, 'prev'); }
    else if (k === 'End') { e.preventDefault(); show(total - 1, 'next'); }
  });

  /* swipe: a horizontal gesture changes the slide, a vertical one scrolls the card */
  var sx = 0, sy = 0, st = 0, tracking = false;
  box.addEventListener('touchstart', function (e) {
    if (e.touches.length !== 1) { tracking = false; return; }
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; st = Date.now(); tracking = true;
  }, { passive: true });
  box.addEventListener('touchend', function (e) {
    if (!tracking) return; tracking = false;
    var t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.4 && Date.now() - st < 800) { dx < 0 ? next() : prev(); }
  }, { passive: true });

  /* ---------- language: the address carries it; the control is a list of links, this only opens and closes the list ---------- */
  var langBox = document.getElementById('langBox');
  var langBtn = document.getElementById('langBtn');
  document.addEventListener('click', function (e) { if (langBox.open && !langBox.contains(e.target)) langBox.open = false; });
  langBox.addEventListener('focusout', function (e) { if (langBox.open && e.relatedTarget && !langBox.contains(e.relatedTarget)) langBox.open = false; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && langBox.open) { langBox.open = false; langBtn.focus(); } });

  /* ---------- theme (the design system's data-theme convention) ---------- */
  document.getElementById('themeBtn').addEventListener('click', function () {
    var t = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', t); store('aivis-theme', t);
  });

  /* ---------- copy ---------- */
  [].forEach.call(document.querySelectorAll('[data-copy]'), function (btn) {
    var label = btn.querySelector('.copy-label');
    var idle = label.textContent;
    btn.addEventListener('click', function () {
      /* the prompt text is English in both page languages: the tools are English only */
      var src = document.getElementById(btn.getAttribute('data-copy'));
      var text = src.textContent.replace(/^\n+|\s+$/g, '');
      function ok() {
        btn.classList.add('done');
        label.textContent = btn.getAttribute('data-copied');
        setTimeout(function () { btn.classList.remove('done'); label.textContent = idle; }, 1800);
      }
      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); ok(); } catch (e) {}
        document.body.removeChild(ta);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(ok, fallback); } else { fallback(); }
    });
  });

  /* placeholder links stay on the page */
  [].forEach.call(document.querySelectorAll('a[href="#"]'), function (a) { a.addEventListener('click', function (e) { e.preventDefault(); }); });

  /* ---------- start ---------- */
  var q = new URLSearchParams(location.search);
  if (q.get('theme') === 'dark' || q.get('theme') === 'light') root.setAttribute('data-theme', q.get('theme'));
  fit();
  var h = parseInt((location.hash || '').slice(1), 10);
  show(isNaN(h) ? 0 : h - 1, 'next');
  deck.classList.add('ready');
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(more);
})();
