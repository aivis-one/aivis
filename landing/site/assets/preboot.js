(function () {
  var t = null;
  try { t = window.localStorage.getItem('aivis-theme'); } catch (e) { t = null; }
  if (t !== 'dark' && t !== 'light') {
    t = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', t);
})();
