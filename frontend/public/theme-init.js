// =============================================================================
// AIVIS.ONE Frontend -- Theme & Language Pre-Init
// =============================================================================
// Extracted from index.html inline script for CSP compliance.
// Runs before Vue mounts to prevent FOUC (Flash of Unstyled Content).
// =============================================================================

(function () {
  var t = localStorage.getItem('aivis-theme')
  if (t === 'dark' || t === 'light') {
    document.documentElement.setAttribute('data-theme', t)
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark')
  }
  // The two <meta name="theme-color"> tags in index.html are media-scoped, so
  // they follow the OS and CANNOT see an explicit in-app choice. When one is
  // stored, point BOTH at that theme's --bg-page: whichever tag the browser
  // matches then gives the same answer, which avoids depending on tag order.
  syncThemeColour(t === 'dark' || t === 'light' ? t : null)

  var l = localStorage.getItem('aivis-lang')
  if (l) {
    document.documentElement.lang = l
    if (l === 'ar') document.documentElement.dir = 'rtl'
  }
})()

// Exported on window so useTheme can reuse it when the user toggles at runtime;
// duplicating the colour literals in two files is how index.html and
// manifest.json came to disagree in the first place.
function syncThemeColour(explicit) {
  var LIGHT = '#F6F8FA'
  var DARK = '#070A0E'
  var tags = document.querySelectorAll('meta[name="theme-color"]')
  for (var i = 0; i < tags.length; i++) {
    var media = tags[i].getAttribute('media') || ''
    var own = media.indexOf('dark') !== -1 ? DARK : LIGHT
    tags[i].setAttribute('content', explicit ? (explicit === 'dark' ? DARK : LIGHT) : own)
  }
}
window.__aivisSyncThemeColour = syncThemeColour
