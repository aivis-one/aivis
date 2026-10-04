/* animation-studio v1.0.0 -- assets/techniques/scroll.js (pack copy, pruned)
   #scr-counter-roll only.

   Project-specific decisions carried here rather than left to the implementer:

   1. Duration. The catalog asset rolls for 900ms, which is outside the
      300-600ms entrance band. Set to 560ms, the value of this design system's
      --motion-ambient, which is the slowest semantic step it defines.
   2. The original text stays in the DOM, visually hidden but readable by
      assistive technology, while the rolling figure is aria-hidden. A screen
      reader hears the final figure once, not a stream of intermediate numbers.
   3. The figure as written is parsed, not guessed: a thousands separator may be
      a comma (10,000), a space or a no-break space (10 000, Russian), and a
      decimal separator a point or a comma. The rolling figure is written back
      with the same separator, and when the roll ends the element holds its
      original text node again, byte for byte: nothing of the technique is left
      in the page at rest.
   4. Nothing is added to the page: the technique only animates a figure that is
      already in the text. Under reduce, and with no IntersectionObserver, the
      element is not touched at all. */

window.ls = window.ls || {};
window.ls.motion = window.ls.motion || {};

window.ls.motion.counterRoll = (function () {
  var REDUCE = '(prefers-reduced-motion: reduce)';
  var DUR = 560;
  /* digits in groups of three after a comma, point, space, no-break space or narrow no-break space
     (10,000  10 000  10 000), else a plain integer or a decimal (3.5  3,5) */
  var FIGURE = /\d{1,3}(?:[,.   ]\d{3})+(?!\d)|\d+(?:[.,]\d+)?/;

  function parse(text) {
    var m = String(text).match(FIGURE);
    if (!m) { return null; }
    var raw = m[0];
    var grouped = /^\d{1,3}(?:[,.   ]\d{3})+$/.test(raw);
    if (grouped) {
      return { value: parseInt(raw.replace(/\D/g, ''), 10), raw: raw, sep: raw.charAt(raw.search(/\D/)), dec: 0, decSep: '' };
    }
    var d = raw.match(/[.,](\d+)$/);
    if (d) {
      return { value: parseFloat(raw.replace(',', '.')), raw: raw, sep: '', dec: d[1].length, decSep: raw.charAt(raw.length - d[1].length - 1) };
    }
    return { value: parseInt(raw, 10), raw: raw, sep: '', dec: 0, decSep: '' };
  }

  /* the figure at value n, written with the separators of the original */
  function format(n, p) {
    var s = p.dec ? n.toFixed(p.dec) : String(Math.round(n));
    var parts = s.split('.');
    var whole = parts[0];
    if (p.sep) { whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, p.sep); }
    return p.dec ? whole + p.decSep + parts[1] : whole;
  }

  function roll(el, p, done) {
    var start = performance.now();
    function frame(now) {
      var t = Math.min(1, (now - start) / DUR);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = format(p.value * eased, p);
      if (t < 1) { requestAnimationFrame(frame); } else { done && done(); }
    }
    requestAnimationFrame(frame);
  }

  function bind(root) {
    root = root || document;
    var nodes = root.querySelectorAll('.ls-mo-counter');
    if (!nodes.length) { return 0; }

    var reduced = window.matchMedia && window.matchMedia(REDUCE).matches;
    if (reduced || !('IntersectionObserver' in window)) { return 0; }   /* the figure stays as written */

    Array.prototype.forEach.call(nodes, function (host) {
      var original = host.textContent;
      var parsed = parse(original);
      if (!parsed) { return; }

      var source = document.createElement('span');
      source.className = 'ls-mo-counter__source';
      source.textContent = original;

      var display = document.createElement('span');
      display.className = 'ls-mo-counter__display';
      display.setAttribute('aria-hidden', 'true');
      display.textContent = format(0, parsed);

      /* hold the width of the final figure, so the line does not reflow while the digits grow */
      var w = host.getBoundingClientRect().width;
      if (w) { host.style.minInlineSize = w + 'px'; }
      host.textContent = '';
      host.appendChild(source);
      host.appendChild(display);

      function rest() {                  /* the element as it was written */
        host.textContent = original;
        host.style.minInlineSize = '';
        if (!host.getAttribute('style')) { host.removeAttribute('style'); }
      }

      var seen = false;
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || seen) { return; }
          seen = true;                   /* B6 entrance-once */
          io.disconnect();
          roll(display, parsed, rest);
        });
      }, { threshold: 0.4 });
      io.observe(host);
    });
    return nodes.length;
  }

  return { bind: bind, parse: parse, format: format };
})();

document.addEventListener('DOMContentLoaded', function () {
  window.ls.motion.counterRoll.bind(document);
});
