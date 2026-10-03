/* animation-studio v1.0.0 -- assets/techniques/transitions.js (pack copy, pruned)
   #trn-same-doc only. trn-shared-element was cut at select: no element on this
   page persists across a state change, so there is nothing to share.

   A6: the callback stays trivial. Long or synchronous work inside a view
   transition callback lands directly on INP. */

window.ls = window.ls || {};
window.ls.motion = window.ls.motion || {};

window.ls.motion.transitions = (function () {
  var REDUCE = '(prefers-reduced-motion: reduce)';

  function supported() {
    return typeof document.startViewTransition === 'function' &&
      !(window.matchMedia && window.matchMedia(REDUCE).matches);
  }

  /* #trn-same-doc -- wrap a DOM swap. Without support, or under reduce, the
     swap simply happens: the same result, minus the animation. This is the
     degrade field and it needs no fallback branch. */
  function swap(update) {
    if (typeof update !== 'function') { return null; }
    if (!supported()) { update(); return null; }
    return document.startViewTransition(update);
  }

  return { swap: swap, supported: supported };
})();
