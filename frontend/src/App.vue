<script setup>
import { ref, onMounted, provide, computed } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import { Music2, User, ChevronDown, LogOut, Radio, Mail } from 'lucide-vue-next'
import MiniPlayer from './components/MiniPlayer.vue'
import { useSession } from './composables/useSession'
import { useAuth } from './composables/useAuth'

const { isInSession, toasts, showToast } = useSession()
const { currentUser, ready, requestLink, restore, logout } = useAuth()

const users = ref([])
const showUserMenu = ref(false)

// Login form state
const email = ref('')
const linkSent = ref(false)
const sending = ref(false)
const loginError = ref('')

const route = useRoute()
const router = useRouter()
// The magic-link landing page must render even while logged out.
const isAuthRoute = computed(() => route.path.startsWith('/auth/verify'))
const isAdmin = computed(() => !!currentUser.value?.is_admin)

provide('currentUser', currentUser)
provide('users', users)
provide('isAdmin', isAdmin)

async function loadUsers() {
  try {
    const res = await fetch('/api/users')
    if (res.ok) users.value = await res.json()
  } catch {}
}

async function submitLogin() {
  loginError.value = ''
  const value = email.value.trim().toLowerCase()
  if (!value) return
  sending.value = true
  try {
    const ok = await requestLink(value)
    if (ok) linkSent.value = true
    else loginError.value = 'Could not send the link. Try again.'
  } catch {
    loginError.value = 'Could not send the link. Try again.'
  } finally {
    sending.value = false
  }
}

function signOut() {
  logout()
  showUserMenu.value = false
  users.value = []
}

// Surface the result of the Spotify OAuth round-trip. The backend callback
// redirects to "/?spotify_connected=true" or "/?spotify_error=...".
function handleSpotifyRedirect() {
  const params = new URLSearchParams(window.location.search)
  const connected = params.get('spotify_connected')
  const err = params.get('spotify_error')
  if (!connected && !err) return

  if (connected) showToast('Spotify connected', 'success')
  else showToast('Spotify connection failed. Please try again.', 'error')

  // Strip the query params so a refresh doesn't re-trigger the toast.
  params.delete('spotify_connected')
  params.delete('spotify_error')

  // Return the user to the room they connected from, if any.
  let target = null
  try {
    target = localStorage.getItem('spotifyReturnPath')
    localStorage.removeItem('spotifyReturnPath')
  } catch {}

  if (connected && target && target !== '/') {
    router.replace(target)
  } else {
    const qs = params.toString()
    window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''))
  }
}

onMounted(async () => {
  handleSpotifyRedirect()
  await restore()
  if (currentUser.value) loadUsers()
})
</script>

<template>
  <div class="min-h-screen text-slate-100">
    <!-- Floating Navbar -->
    <nav class="fixed top-4 left-4 right-4 z-50 glass shadow-lg shadow-black/20">
      <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <RouterLink to="/" class="flex items-center gap-2 text-xl font-heading font-semibold">
            <Music2 class="w-6 h-6 text-accent-primary" />
            <span class="hidden sm:inline">Album Ranker</span>
            <span class="sm:hidden">Albums</span>
          </RouterLink>
          <RouterLink v-if="currentUser" to="/rooms" class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
            <Radio class="w-4 h-4" />
            <span class="hidden sm:inline">Rooms</span>
          </RouterLink>
        </div>

        <!-- User menu -->
        <div v-if="currentUser" class="relative">
          <button
            @click="showUserMenu = !showUserMenu"
            class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg"
          >
            <User class="w-4 h-4 text-slate-400" />
            <span class="text-sm">{{ currentUser.name }}</span>
            <ChevronDown class="w-4 h-4 text-slate-400" />
          </button>

          <div
            v-if="showUserMenu"
            class="absolute right-0 mt-2 w-56 bg-bg-secondary border border-white/20 rounded-xl overflow-hidden shadow-2xl"
          >
            <div class="px-4 py-3 border-b border-white/10">
              <div class="text-sm font-medium">{{ currentUser.name }}</div>
              <div class="text-xs text-slate-500 truncate">{{ currentUser.email }}</div>
            </div>
            <button
              @click="signOut"
              class="w-full px-4 py-2 text-left text-sm hover:bg-white/10 transition-colors flex items-center gap-2 text-slate-400"
            >
              <LogOut class="w-4 h-4" />
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </nav>

    <!-- Click outside to close menu -->
    <div
      v-if="showUserMenu"
      class="fixed inset-0 z-40"
      @click="showUserMenu = false"
    />

    <!-- Main content -->
    <main class="pt-24 px-4" :class="isInSession ? 'pb-24' : 'pb-8'">
      <div class="max-w-6xl mx-auto">
        <!-- Logged in, or on the magic-link landing page -->
        <RouterView v-if="currentUser || isAuthRoute" />

        <!-- Login screen -->
        <div v-else-if="ready" class="max-w-sm mx-auto text-center py-16">
          <Music2 class="w-16 h-16 mx-auto mb-4 text-accent-primary" />
          <h2 class="text-2xl font-heading font-semibold mb-2">Album Ranker</h2>

          <template v-if="!linkSent">
            <p class="text-slate-500 mb-6">Sign in with your email — we'll send you a magic link.</p>
            <form @submit.prevent="submitLogin" class="space-y-3">
              <input
                v-model="email"
                type="email"
                required
                placeholder="you@example.com"
                class="input-base text-center"
                autofocus
              />
              <p v-if="loginError" class="text-red-400 text-sm">{{ loginError }}</p>
              <button type="submit" :disabled="sending || !email.trim()" class="btn-primary w-full flex items-center justify-center gap-2">
                <Mail class="w-4 h-4" />
                {{ sending ? 'Sending…' : 'Send magic link' }}
              </button>
            </form>
          </template>

          <template v-else>
            <Mail class="w-10 h-10 mx-auto mb-3 text-accent-primary" />
            <h3 class="text-lg font-medium mb-2">Check your inbox</h3>
            <p class="text-slate-500">We sent a sign-in link to <span class="text-slate-300">{{ email }}</span>. It expires in 15 minutes.</p>
            <button @click="linkSent = false" class="mt-6 text-sm text-slate-400 hover:text-white">Use a different email</button>
          </template>
        </div>

        <!-- Booting -->
        <div v-else class="text-center py-24 text-slate-600">Loading…</div>
      </div>
    </main>

    <!-- Mini Player -->
    <MiniPlayer />

    <!-- Global Toast Notifications -->
    <div class="fixed bottom-20 right-4 z-50 flex flex-col gap-2" :class="{ 'bottom-4': !isInSession }">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="px-4 py-3 rounded-xl shadow-xl text-sm max-w-xs animate-slide-in backdrop-blur-xl border"
          :class="toast.type === 'success'
            ? 'bg-green-500/20 text-green-300 border-green-500/30'
            : toast.type === 'error'
              ? 'bg-red-500/20 text-red-300 border-red-500/30'
              : 'bg-white/10 text-white border-white/20'"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
