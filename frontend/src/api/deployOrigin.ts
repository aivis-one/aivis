// =============================================================================
// AIVIS.ONE Frontend -- Deployment origin check (H35 P-127)
// =============================================================================
//
// The frontend knows the addresses of the server it is deployed to from ONE
// place: the values the build is given (frontend/Dockerfile build args, set by
// `aivis frontend build` from what the installer asked for). There is no
// default and no fallback anywhere in the code: a build without a value, or
// with a value that is not an origin, stops here with the variable's name.
//
// AN ORIGIN, EXACTLY. Scheme and host (and a port, if any) -- what
// `new URL(value).origin` gives back unchanged. Refused, each by name:
//   - not set / empty / surrounding blanks;
//   - not a URL;
//   - a scheme other than https:// (http:// only when the caller allows it:
//     `vite serve` against a backend on localhost);
//   - anything `origin` would drop or rewrite: a path, a trailing '/', a
//     query, a fragment, credentials, a default port, uppercase in the host.
// No normalisation: a value that is not already exact is a second value, and
// the same string goes into the CSP (frontend/nginx.conf) where only an exact
// origin matches, and into client.ts, which appends paths that begin with '/'.
//
// Used by vite.config.ts (every production build), by client.ts (the running
// bundle, and `vite serve`), and by frontend/Dockerfile for the files origin,
// which only the CSP carries. Kept free of imports and of non-erasable
// TypeScript so that Node can run it directly in the Dockerfile.
// =============================================================================

export interface OriginRule {
  /** Accept http:// as well as https:// (development only). */
  allowHttp: boolean
}

export function requireOrigin(name: string, value: string | undefined, rule: OriginRule): string {
  if (value === undefined) {
    throw new Error(`${name} is not set -- it is the deployment address and has no default`)
  }
  if (value === '') {
    throw new Error(`${name} is empty -- it is the deployment address and has no default`)
  }
  if (value.trim() !== value) {
    throw new Error(`${name}="${value}" has surrounding blanks`)
  }
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error(`${name}="${value}" is not a URL`)
  }
  const schemes = rule.allowHttp ? ['https:', 'http:'] : ['https:']
  if (!schemes.includes(url.protocol)) {
    throw new Error(
      `${name}="${value}" must start with ${rule.allowHttp ? 'https:// or http://' : 'https://'}`,
    )
  }
  if (url.origin !== value) {
    throw new Error(
      `${name}="${value}" must be an origin -- scheme and host only, ` +
        `no path, no trailing '/', no query (expected form: ${url.origin})`,
    )
  }
  return value
}
