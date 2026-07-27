<script setup>
import { ref, onMounted, provide, computed, watch } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import {
  Music2, ChevronDown, LogOut, Radio, Mail, Home,
  TrendingUp, Users, Layers, Calendar, BarChart3
} from 'lucide-vue-next'
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

const mainNav = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/rooms', label: 'Rooms', icon: Radio },
]

const libraryNav = [
  { to: '/stats', label: 'Stats', icon: TrendingUp },
  { to: '/compare', label: 'Compare', icon: Users },
  { to: '/tiers', label: 'Tier List', icon: Layers },
  { to: '/year-review', label: 'Year Review', icon: Calendar },
  { to: '/results', label: 'Results', icon: BarChart3 },
]

const userInitial = computed(() => (currentUser.value?.name || '?').charAt(0).toUpperCase())

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

// Load users on login too (magic-link verify sets currentUser without a
// remount), or Comparison/TierList see an empty user list until a reload.
watch(currentUser, (user, prev) => {
  if (user && !prev) loadUsers()
})

onMounted(async () => {
  handleSpotifyRedirect()
  await restore()
  if (currentUser.value) loadUsers()
})
</script>

<template>
  <div class="h-screen flex flex-col bg-surface-base text-white overflow-hidden">
    <div class="flex flex-1 gap-2 p-2 min-h-0">
      <!-- Sidebar: icon rail on small screens, full labels on lg+ -->
      <aside v-if="currentUser" class="w-14 sm:w-16 lg:w-64 shrink-0 flex flex-col">
        <div class="bg-bg-primary rounded-lg flex-1 flex flex-col py-4 px-2 lg:px-3 overflow-y-auto scrollbar-hide">
          <RouterLink to="/" class="flex items-center justify-center lg:justify-start gap-2 px-1 lg:px-3 mb-6 text-white">
            <Music2 class="w-7 h-7 text-accent-primary shrink-0" />
            <span class="hidden lg:inline text-lg font-heading font-bold">Album Ranker</span>
          </RouterLink>

          <nav class="flex flex-col gap-1">
            <RouterLink
              v-for="item in mainNav"
              :key="item.to"
              :to="item.to"
              class="nav-item justify-center lg:justify-start"
              :class="{ 'nav-item-active': route.path === item.to }"
              :title="item.label"
            >
              <component :is="item.icon" class="w-6 h-6 shrink-0" />
              <span class="hidden lg:inline">{{ item.label }}</span>
            </RouterLink>
          </nav>

          <div class="my-4 mx-1 lg:mx-3 border-t border-white/10"></div>
          <div class="hidden lg:block px-3 mb-2 text-xs font-bold uppercase tracking-wider text-text-subdued">Your Rankings</div>

          <nav class="flex flex-col gap-1">
            <RouterLink
              v-for="item in libraryNav"
              :key="item.to"
              :to="item.to"
              class="nav-item justify-center lg:justify-start"
              :class="{ 'nav-item-active': route.path === item.to }"
              :title="item.label"
            >
              <component :is="item.icon" class="w-6 h-6 shrink-0" />
              <span class="hidden lg:inline">{{ item.label }}</span>
            </RouterLink>
          </nav>
        </div>
      </aside>

      <!-- Main panel -->
      <main class="flex-1 min-w-0 bg-bg-primary rounded-lg overflow-y-auto relative">
        <!-- Top bar -->
        <header
          v-if="currentUser"
          class="sticky top-0 z-40 flex items-center justify-end px-4 sm:px-6 py-3 bg-bg-primary/80 backdrop-blur-md"
        >
          <div class="relative">
            <button
              @click="showUserMenu = !showUserMenu"
              class="flex items-center gap-2 p-1 pr-2 rounded-full bg-black/40 hover:bg-surface-highlight transition-colors"
            >
              <span class="w-8 h-8 rounded-full bg-accent-primary text-black font-bold flex items-center justify-center">
                {{ userInitial }}
              </span>
              <ChevronDown class="w-4 h-4 text-text-subdued" />
            </button>

            <div
              v-if="showUserMenu"
              class="absolute right-0 mt-2 w-56 bg-surface-elevated rounded-md overflow-hidden shadow-2xl shadow-black/60"
            >
              <div class="px-4 py-3 border-b border-white/10">
                <div class="text-sm font-semibold">{{ currentUser.name }}</div>
                <div class="text-xs text-text-subdued truncate">{{ currentUser.email }}</div>
              </div>
              <button
                @click="signOut"
                class="w-full px-4 py-3 text-left text-sm hover:bg-white/10 transition-colors flex items-center gap-2 text-text-subdued hover:text-white"
              >
                <LogOut class="w-4 h-4" />
                Sign Out
              </button>
            </div>
          </div>
        </header>

        <div class="px-4 sm:px-6 pb-8 max-w-7xl mx-auto" :class="currentUser ? '' : 'pt-8'">
          <!-- Logged in, or on the magic-link landing page -->
          <RouterView v-if="currentUser || isAuthRoute" />

          <!-- Login screen -->
          <div v-else-if="ready" class="max-w-sm mx-auto text-center py-16">
            <Music2 class="w-16 h-16 mx-auto mb-4 text-accent-primary" />
            <h2 class="text-2xl font-heading font-bold mb-2">Album Ranker</h2>

            <template v-if="!linkSent">
              <p class="text-text-subdued mb-6">Sign in with your email — we'll send you a magic link.</p>
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
              <h3 class="text-lg font-semibold mb-2">Check your inbox</h3>
              <p class="text-text-subdued">We sent a sign-in link to <span class="text-white">{{ email }}</span>. It expires in 15 minutes.</p>
              <button @click="linkSent = false" class="mt-6 text-sm text-text-subdued hover:text-white">Use a different email</button>
            </template>
          </div>

          <!-- Booting -->
          <div v-else class="text-center py-24 text-text-subdued">Loading…</div>
        </div>
      </main>
    </div>

    <!-- Click outside to close menu -->
    <div
      v-if="showUserMenu"
      class="fixed inset-0 z-30"
      @click="showUserMenu = false"
    />

    <!-- Now-playing bar (in flow, docked below the panels like Spotify) -->
    <MiniPlayer />

    <!-- Global Toast Notifications -->
    <div class="fixed bottom-24 right-4 z-50 flex flex-col gap-2" :class="{ 'bottom-4': !isInSession }" role="status" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="px-4 py-3 rounded-lg shadow-xl text-sm max-w-xs animate-slide-in"
          :class="toast.type === 'success'
            ? 'bg-accent-primary text-black font-semibold'
            : toast.type === 'error'
              ? 'bg-red-500 text-white font-semibold'
              : 'bg-surface-elevated text-white'"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
