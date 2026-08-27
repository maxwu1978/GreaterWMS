const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

export function isMail2TaskPreview () {
  // The local Django server serves the production SPA bundle, so checking
  // NODE_ENV would disable the intentionally local-only preview after build.
  // The loopback-host and explicit-query checks keep this unavailable on the
  // production GreaterWMS host and require an intentional preview URL.
  if (typeof window === 'undefined') return false
  if (!LOCAL_HOSTS.has(window.location.hostname)) return false

  const hash = String(window.location.hash || '')
  const hashQuery = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : ''
  const query = [window.location.search.replace(/^\?/, ''), hashQuery].filter(Boolean).join('&')
  return new URLSearchParams(query).get('preview') === 'mail2task'
}
