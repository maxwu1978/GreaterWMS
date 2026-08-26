const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

export function isMail2TaskPreview () {
  if (process.env.NODE_ENV !== 'development' || typeof window === 'undefined') return false
  if (!LOCAL_HOSTS.has(window.location.hostname)) return false

  const hash = String(window.location.hash || '')
  const hashQuery = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : ''
  const query = [window.location.search.replace(/^\?/, ''), hashQuery].filter(Boolean).join('&')
  return new URLSearchParams(query).get('preview') === 'mail2task'
}
