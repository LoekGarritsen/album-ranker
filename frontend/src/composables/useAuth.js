import { ref } from 'vue'

const TOKEN_KEY = 'authToken'

// Singleton auth state shared across the app.
const token = ref(localStorage.getItem(TOKEN_KEY) || null)
const currentUser = ref(null)
const ready = ref(false)

let interceptorInstalled = false

function setToken(value) {
  token.value = value
  if (value) localStorage.setItem(TOKEN_KEY, value)
  else localStorage.removeItem(TOKEN_KEY)
}

/**
 * Install a one-time fetch interceptor that attaches the session token to
 * same-origin /api requests (unless an Authorization header is already set,
 * e.g. direct Spotify Web API calls).
 */
function installInterceptor() {
  if (interceptorInstalled) return
  interceptorInstalled = true
  const original = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    let url = typeof input === 'string' ? input : (input && input.url) || ''
    const isApi = url.startsWith('/api') || url.includes(`${window.location.host}/api`)
    if (token.value && isApi) {
      const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined) || {})
      if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token.value}`)
        init = { ...init, headers }
      }
    }
    return original(input, init)
  }
}

export function useAuth() {
  installInterceptor()

  async function requestLink(email) {
    const res = await fetch('/api/auth/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    return res.ok
  }

  async function verify(linkToken) {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: linkToken }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setToken(data.token)
    currentUser.value = data.user
    return true
  }

  /** Restore the session on app load from a stored token. */
  async function restore() {
    if (!token.value) { ready.value = true; return }
    try {
      const res = await fetch('/api/auth/me')
      if (res.ok) currentUser.value = await res.json()
      else { setToken(null); currentUser.value = null }
    } catch {
      // network error — keep token, try again next load
    } finally {
      ready.value = true
    }
  }

  async function logout() {
    try { await fetch('/api/auth/logout', { method: 'POST' }) } catch {}
    setToken(null)
    currentUser.value = null
  }

  return { token, currentUser, ready, requestLink, verify, restore, logout }
}
