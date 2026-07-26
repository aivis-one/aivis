// =============================================================================
// AIVIS.ONE Frontend -- Theme & Language Pre-Init
// =============================================================================
// Extracted from index.html inline script for CSP compliance.
// Runs before Vue mounts to prevent FOUC (Flash of Unstyled Content).
// =============================================================================

(function () {
  var t = localStorage.getItem('cbs-theme')
  if (t === 'dark' || t === 'light') {
    document.documentElement.setAttribute('data-theme', t)
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark')
  }
  var l = localStorage.getItem('cbs-lang')
  if (l) {
    document.documentElement.lang = l
    if (l === 'ar') document.documentElement.dir = 'rtl'
  }
})()
