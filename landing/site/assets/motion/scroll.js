/* animation-studio v1.0.0 -- assets/techniques/scroll.js (pack copy, pruned)
   #scr-counter-roll only.

   Two project-specific decisions are carried here rather than left to the
   implementer:

   1. Duration. The catalog asset rolls for 900ms, which is outside the
      300-600ms entrance band. Set to 560ms, the value of this design system's
      --motion-ambient, which is the slowest semantic step it defines.
   2. The original text stays in the DOM, visually hidden but readable by
      assistive technology. The rolling figure is aria-hidden. A screen reader
      hears the final figure once, not a stream of intermediate numbers. */

window.ls = window.ls || {};
window.ls.motion = window.ls.motion || {};

window.ls.motion.counterRoll = (function () {
  var REDUCE = '(prefers-reduced-motion: reduce)';
  var DUR = 560;

  function parse(text) {
    var m = String(text).match(/-?[\d.,]+/);
    if (!m) { return null; }
    var n = parseFloat(m[0].replace(/,/g, ''));
    return isNaN(n) ? null : { value: n, raw: m[0] };
  }

  function roll(el, target, done) {
    var start = performance.now();
    function frame(now) {
      var t = Math.min(1, (now - start) / DUR);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased).toLocaleString();
      if (t < 1) { requestAnimationFrame(frame); } else { done && done(); }
    }
    requestAnimationFrame(frame);
  }

  function bind(root) {
    root = root || document;
    var nodes = root.querySelectorAll('.ls-mo-counter');
    if (!nodes.length) { return 0; }

    var reduced = window.matchMedia && window.matchMedia(REDUCE).matches;

    Array.prototype.forEach.call(nodes, function (host) {
      var parsed = parse(host.textContent);
      if (!parsed) { return; }

      var original = document.createElement('span');
      original.className = 'ls-mo-counter__source';
      original.textContent = host.textContent;

      var display = document.createElement('span');
      display.className = 'ls-mo-counter__display';
      display.setAttribute('aria-hidden', 'true');
      display.textContent = reduced ? parsed.raw : '0';

      host.textContent = '';
      host.appendChild(original);
      host.appendChild(display);
      original.style.position = 'absolute';
      original.style.width = '1px';
      original.style.height = '1px';
      original.style.overflow = 'hidden';
      original.style.clip = 'rect(0 0 0 0)';

      /* degrade: no IntersectionObserver, or reduce -- the final figure is
         rendered immediately as text. */
      if (reduced || !('IntersectionObserver' in window)) {
        display.textContent = parsed.raw;
        return;
      }

      var seen = false;
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || seen) { return; }
          seen = true;                       /* B6 entrance-once */
          io.disconnect();
          roll(display, parsed.value, function () {
            display.textContent = parsed.raw;
          });
        });
      }, { threshold: 0.4 });
      io.observe(host);
    });
    return nodes.length;
  }

  return { bind: bind };
})();

document.addEventListener('DOMContentLoaded', function () {
  window.ls.motion.counterRoll.bind(document);
});
