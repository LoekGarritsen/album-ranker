<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, Trophy, Heart, Radio, Disc3 } from 'lucide-vue-next'

const router = useRouter()

const open = ref(false)
const items = ref([])
const unread = ref(0)
let timer = null

async function poll() {
  try {
    const res = await fetch('/api/notifications')
    if (res.ok) {
      const data = await res.json()
      items.value = data.notifications
      unread.value = data.unread
    }
  } catch {}
}

async function toggleOpen() {
  open.value = !open.value
  if (open.value && unread.value > 0) {
    await fetch('/api/notifications/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    unread.value = 0
    items.value = items.value.map(n => ({ ...n, read: 1 }))
  }
}

function describe(n) {
  const p = n.payload || {}
  switch (n.type) {
    case 'session_started':
      return `${p.by_name} started ${p.mode === 'hangout' ? 'a hangout' : 'a listening room'}: ${p.name}`
    case 'club_round':
      return {
        nominating: `Club round "${p.title}" is open for nominations`,
        voting: `Voting opened for club round "${p.title}"`,
        rating: `Blind rating started: ${p.album?.name || p.title}`,
        revealed: `Scores revealed for "${p.title}"`,
      }[p.status] || `Club round "${p.title}" updated`
    case 'rating_like':
      return `${p.by_name} liked your ${p.score}/10 on ${p.item_name}`
    case 'album_added':
      return `New in the library: ${p.name} by ${p.artist}`
    default:
      return n.type
  }
}

function iconFor(type) {
  return { session_started: Radio, club_round: Trophy, rating_like: Heart, album_added: Disc3 }[type] || Bell
}

function go(n) {
  open.value = false
  const p = n.payload || {}
  if (n.type === 'session_started' && p.code) router.push(`/session/${p.code}`)
  else if (n.type === 'club_round') router.push('/club')
  else if (n.type === 'rating_like') router.push('/results')
  else if (n.type === 'album_added') router.push('/')
}

function timeAgo(ts) {
  if (!ts) return ''
  const then = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z')
  const secs = Math.floor((Date.now() - then.getTime()) / 1000)
  if (secs < 60) return 'now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}

onMounted(() => {
  poll()
  timer = setInterval(poll, 45000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="relative">
    <button @click="toggleOpen"
            class="relative p-2 rounded-full bg-black/40 hover:bg-surface-highlight transition-colors"
            title="Notifications">
      <Bell class="w-5 h-5" :class="unread ? 'text-white' : 'text-text-subdued'" />
      <span v-if="unread"
            class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-accent-primary text-black text-[10px] font-bold flex items-center justify-center">
        {{ unread > 9 ? '9+' : unread }}
      </span>
    </button>

    <div v-if="open"
         class="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-surface-elevated rounded-md shadow-2xl shadow-black/60 z-50">
      <div class="px-4 py-2.5 border-b border-white/10 text-sm font-semibold">Notifications</div>
      <template v-if="items.length">
        <button v-for="n in items" :key="n.id" @click="go(n)"
                class="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-white/10 transition-colors"
                :class="{ 'opacity-60': n.read }">
          <component :is="iconFor(n.type)" class="w-4 h-4 mt-0.5 text-accent-primary shrink-0" />
          <span class="text-sm flex-1 min-w-0">{{ describe(n) }}</span>
          <span class="text-[11px] text-text-subdued shrink-0">{{ timeAgo(n.created_at) }}</span>
        </button>
      </template>
      <div v-else class="px-4 py-8 text-center text-sm text-text-subdued">All quiet.</div>
    </div>

    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />
  </div>
</template>
