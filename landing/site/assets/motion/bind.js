/* animation-studio v1.0.0 -- assets/techniques/bind.js
   Project binding: wires the approved techniques to this page's own hooks.
   No technique logic lives here; it calls the technique modules. */

window.ls = window.ls || {};
window.ls.motion = window.ls.motion || {};

window.ls.motion.bind = (function () {
  var REDUCE = '(prefers-reduced-motion: reduce)';

  /* #trn-same-doc -- the theme toggle. The page owned this swap already; the
     pack wraps the existing path rather than replacing it, so the localStorage
     write and the icon swap keep running exactly as before. */
  function themeSwap(apply) {
    return window.ls.motion.transitions.swap(apply);
  }

  /* #mic-accordion -- native <details> opens and collapses instantly, so both halves are driven here:
     opening sets the open attribute first, lets the collapsed pane render one frame, then expands it;
     closing collapses the pane first and removes the open attribute when the pane's own height
     transition ends (or after a fallback timer, so a lost transitionend never leaves it stuck). A click
     during a collapse reverses it. Under reduce, and with no support, the element behaves as a plain
     <details>: the content toggles, no height animation, nothing lost but the motion. */
  function accordion(root) {
    var reduced = window.matchMedia && window.matchMedia(REDUCE).matches;
    var panes = (root || document).querySelectorAll('.ls-mo-accordion');
    Array.prototype.forEach.call(panes, function (pane) {
      var det = pane.closest('details');
      if (!det) { return; }
      var sum = det.querySelector('summary');
      if (!sum) { return; }
      var closing = null;
      pane.setAttribute('data-open', det.open ? 'true' : 'false');

      function finishClose() {
        if (!closing) { return; }
        clearTimeout(closing);
        closing = null;
        pane.removeEventListener('transitionend', onEnd);
        det.open = false;
      }
      function onEnd(e) {
        if (e.target === pane && e.propertyName === 'grid-template-rows') { finishClose(); }
      }

      /* State first, animation second: a details element opened or closed by anything but this
         click (find-in-page, a script, reduced motion) never leaves its pane out of step. */
      det.addEventListener('toggle', function () {
        if (!closing) { pane.setAttribute('data-open', det.open ? 'true' : 'false'); }
      });

      sum.addEventListener('click', function (e) {
        if (reduced) { return; }
        e.preventDefault();
        if (closing) {                       /* reopen during a collapse */
          clearTimeout(closing);
          closing = null;
          pane.removeEventListener('transitionend', onEnd);
          pane.setAttribute('data-open', 'true');
          return;
        }
        if (det.open) {
          pane.setAttribute('data-open', 'false');
          pane.addEventListener('transitionend', onEnd);
          closing = setTimeout(finishClose, 450);
        } else {
          pane.setAttribute('data-open', 'false');
          det.open = true;
          void pane.offsetHeight;            /* render the collapsed pane once, so the expansion transitions */
          pane.setAttribute('data-open', 'true');
        }
      });
    });
    return panes.length;
  }

  return { themeSwap: themeSwap, accordion: accordion };
})();

document.addEventListener('DOMContentLoaded', function () {
  window.ls.motion.bind.accordion(document);
});
