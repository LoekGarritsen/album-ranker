<script setup>
import { ref, onMounted, onUnmounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Radio, Users, Lock, Plus, X, Loader2, ChevronLeft, Trash2, MessageCircle } from 'lucide-vue-next'
import ModalDialog from '../components/ModalDialog.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import { useSession } from '../composables/useSession'

const router = useRouter()
const currentUser = inject('currentUser')
const isAdmin = inject('isAdmin')
const { showToast } = useSession()

const rooms = ref([])
const loading = ref(true)
const joining = ref(null) // Track which room is being joined

// Create room modal
const showCreateModal = ref(false)
const createForm = ref({
  name: '',
  isPublic: true,
  password: '',
  mode: 'listening'
})
const creating = ref(false)

// Join with password modal
const showPasswordModal = ref(false)
const passwordInput = ref('')
const passwordError = ref('')
const joiningRoom = ref(null)

// Join by room code
const codeInput = ref('')
const codeError = ref('')

// Auto-refresh interval
let refreshInterval = null

async function joinByCode() {
  const code = codeInput.value.trim().toUpperCase()
  if (code.length < 4) return
  codeError.value = ''
  try {
    const res = await fetch(`/api/sessions/${code}`)
    if (!res.ok) {
      codeError.value = 'Room not found'
      return
    }
    const room = await res.json()
    // Reuse the normal join flow so password-protected rooms still prompt
    await joinRoom({ code: room.code, name: room.name, has_password: room.has_password })
  } catch (e) {
    codeError.value = 'Room not found'
  }
}

async function loadRooms(showLoading = true) {
  if (showLoading) loading.value = true
  try {
    const res = await fetch('/api/sessions')
    if (res.ok) {
      rooms.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load rooms:', e)
  }
  if (showLoading) loading.value = false
}

async function createRoom() {
  if (!createForm.value.name.trim()) return

  creating.value = true
  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': currentUser.value?.id?.toString() || ''
      },
      body: JSON.stringify({
        name: createForm.value.name.trim(),
        is_public: createForm.value.isPublic,
        password: createForm.value.password || null,
        mode: createForm.value.mode
      })
    })

    if (res.ok) {
      const data = await res.json()
      router.push(`/session/${data.code}`)
    } else {
      showToast('Failed to create room', 'error')
    }
  } catch (e) {
    console.error('Failed to create room:', e)
    showToast('Failed to create room', 'error')
  }
  creating.value = false
}

function closeCreateModal() {
  showCreateModal.value = false
  createForm.value = { name: '', isPublic: true, password: '', mode: 'listening' }
}

async function joinRoom(room) {
  if (room.has_password) {
    joiningRoom.value = room
    showPasswordModal.value = true
    passwordInput.value = ''
    passwordError.value = ''
    return
  }

  joining.value = room.code
  try {
    const res = await fetch(`/api/sessions/${room.code}/join`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': currentUser.value?.id?.toString() || ''
      }
    })

    if (res.ok) {
      router.push(`/session/${room.code}`)
    } else {
      showToast('Failed to join room', 'error')
    }
  } catch (e) {
    console.error('Failed to join room:', e)
    showToast('Failed to join room', 'error')
  }
  joining.value = null
}

async function submitPassword() {
  if (!joiningRoom.value) return

  passwordError.value = ''
  try {
    const res = await fetch(`/api/sessions/${joiningRoom.value.code}/join`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': currentUser.value?.id?.toString() || ''
      },
      body: JSON.stringify({ password: passwordInput.value })
    })

    if (res.ok) {
      router.push(`/session/${joiningRoom.value.code}`)
    } else {
      passwordError.value = 'Invalid password'
    }
  } catch (e) {
    passwordError.value = 'Failed to join room'
  }
}

function closePasswordModal() {
  showPasswordModal.value = false
  joiningRoom.value = null
  passwordInput.value = ''
  passwordError.value = ''
}

// Delete confirmation modal
const deleteTarget = ref(null)
const deleting = ref(false)

function requestDeleteRoom(room, event) {
  event.stopPropagation()
  deleteTarget.value = room
}

async function confirmDeleteRoom() {
  if (!deleteTarget.value || deleting.value) return
  deleting.value = true
  try {
    const res = await fetch(`/api/sessions/${deleteTarget.value.code}`, {
      method: 'DELETE',
      headers: {
        'X-User-Id': currentUser.value?.id?.toString() || ''
      }
    })
    if (res.ok) {
      showToast(`Room "${deleteTarget.value.name}" deleted`, 'success')
      deleteTarget.value = null
      await loadRooms(false)
    } else {
      showToast('Failed to delete room', 'error')
    }
  } catch (e) {
    console.error('Failed to delete room:', e)
    showToast('Failed to delete room', 'error')
  }
  deleting.value = false
}

onMounted(() => {
  loadRooms()
  // Auto-refresh rooms list every 10 seconds (without loading indicator)
  refreshInterval = setInterval(() => loadRooms(false), 10000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})
</script>

<template>
  <div>
    <router-link to="/" class="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-6 py-2 min-h-[44px]">
      <ChevronLeft class="w-4 h-4" />
      Back to Albums
    </router-link>

    <!-- Header -->
    <div class="flex items-center justify-between mb-6 sm:mb-8 flex-wrap gap-3">
      <div>
        <h1 class="text-2xl sm:text-3xl font-heading font-bold flex items-center gap-3">
          <Radio class="w-7 h-7 text-accent-primary" />
          Listening Rooms
        </h1>
        <p class="text-slate-400 text-sm mt-1">Join a room to listen together in sync</p>
      </div>
      <button
        @click="showCreateModal = true"
        class="flex items-center gap-2 px-4 py-2 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors min-h-[44px]"
      >
        <Plus class="w-5 h-5" />
        <span class="hidden sm:inline">Create Room</span>
        <span class="sm:hidden">Create</span>
      </button>
    </div>

    <!-- Join by code (private rooms aren't in the list) -->
    <form @submit.prevent="joinByCode" class="flex items-center gap-2 mb-6 flex-wrap">
      <input
        v-model="codeInput"
        type="text"
        maxlength="6"
        placeholder="Have a code?"
        class="input-base !w-44 font-mono uppercase tracking-widest placeholder:normal-case placeholder:tracking-normal placeholder:font-sans"
        @input="codeError = ''"
      />
      <button
        type="submit"
        :disabled="codeInput.trim().length < 4"
        class="px-4 py-2 glass glass-hover rounded-xl text-sm min-h-[44px] disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Join
      </button>
      <p v-if="codeError" class="text-red-400 text-sm">{{ codeError }}</p>
    </form>

    <!-- Loading skeleton -->
    <div v-if="loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 6" :key="i" class="glass p-4">
        <div class="flex items-start gap-3">
          <div class="skeleton w-16 h-16 rounded-lg"></div>
          <div class="flex-1 space-y-2">
            <div class="skeleton h-5 w-32 rounded"></div>
            <div class="skeleton h-4 w-24 rounded"></div>
            <div class="skeleton h-3 w-20 rounded mt-2"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="rooms.length === 0" class="text-center py-16">
      <Radio class="w-16 h-16 mx-auto mb-4 text-slate-600" />
      <h2 class="text-xl font-heading font-medium text-slate-400 mb-2">No active rooms</h2>
      <p class="text-slate-500 mb-6">Create a room to start listening with others</p>
      <button
        @click="showCreateModal = true"
        class="inline-flex items-center gap-2 px-6 py-3 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
      >
        <Plus class="w-5 h-5" />
        Create Room
      </button>
    </div>

    <!-- Rooms list -->
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="room in rooms"
        :key="room.code"
        @click="joining !== room.code && joinRoom(room)"
        :class="[
          'card-interactive p-4',
          joining === room.code ? 'opacity-70 cursor-wait' : ''
        ]"
      >
        <div class="flex items-start gap-3">
          <!-- Album cover or placeholder -->
          <div class="relative">
            <img
              v-if="room.cover_url"
              :src="room.cover_url"
              class="w-16 h-16 rounded-lg object-cover bg-white/10"
            />
            <div v-else class="w-16 h-16 rounded-lg bg-white/10 flex items-center justify-center">
              <MessageCircle v-if="room.mode === 'hangout'" class="w-6 h-6 text-purple-400" />
              <Radio v-else class="w-6 h-6 text-slate-500" />
            </div>
            <div v-if="room.has_password" class="absolute -top-1 -right-1 w-5 h-5 bg-slate-700 rounded-full flex items-center justify-center">
              <Lock class="w-3 h-3 text-slate-300" />
            </div>
            <!-- Loading overlay when joining -->
            <div v-if="joining === room.code" class="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
              <Loader2 class="w-6 h-6 animate-spin text-accent-primary" />
            </div>
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <h3 class="font-heading font-semibold truncate">{{ room.name }}</h3>
              <span
                v-if="room.mode === 'hangout'"
                class="px-1.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-[10px] font-medium flex-shrink-0"
              >
                Hangout
              </span>
            </div>
            <p v-if="room.album_name" class="text-sm text-slate-400 truncate">{{ room.album_name }}</p>
            <p v-else-if="room.mode === 'hangout'" class="text-sm text-slate-500 italic">Chat room</p>
            <p v-else class="text-sm text-slate-500 italic">No album selected</p>
            <div class="flex items-center gap-2 mt-2 text-xs text-slate-500">
              <Users class="w-3 h-3" />
              <span>{{ room.participant_count }} {{ room.mode === 'hangout' ? 'hanging out' : 'listening' }}</span>
              <span v-if="room.created_by_name" class="text-slate-600">· by {{ room.created_by_name }}</span>
            </div>
          </div>

          <!-- Admin delete button -->
          <button
            v-if="isAdmin"
            @click="requestDeleteRoom(room, $event)"
            class="p-2 text-slate-500 hover:text-red-400 hover:bg-white/10 rounded-lg transition-colors flex-shrink-0"
            title="Delete room"
            aria-label="Delete room"
          >
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>

    <!-- Create Room Modal -->
    <ModalDialog v-if="showCreateModal" @close="closeCreateModal">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-xl font-heading font-semibold">Create Room</h2>
          <button @click="closeCreateModal" class="p-1 hover:bg-white/10 rounded-lg" aria-label="Close">
            <X class="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <form @submit.prevent="createRoom" class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-2">Room Type</label>
            <div class="grid grid-cols-2 gap-2">
              <button
                type="button"
                @click="createForm.mode = 'listening'"
                class="flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-colors"
                :class="createForm.mode === 'listening'
                  ? 'bg-accent-primary/15 border-accent-primary/60 text-accent-primary'
                  : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'"
              >
                <Radio class="w-5 h-5" />
                <span class="text-sm font-medium">Listening</span>
                <span class="text-[11px] leading-tight" :class="createForm.mode === 'listening' ? 'text-accent-primary/80' : 'text-slate-500'">
                  Rate an album in sync
                </span>
              </button>
              <button
                type="button"
                @click="createForm.mode = 'hangout'"
                class="flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-colors"
                :class="createForm.mode === 'hangout'
                  ? 'bg-purple-500/15 border-purple-400/60 text-purple-300'
                  : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'"
              >
                <MessageCircle class="w-5 h-5" />
                <span class="text-sm font-medium">Hangout</span>
                <span class="text-[11px] leading-tight" :class="createForm.mode === 'hangout' ? 'text-purple-300/80' : 'text-slate-500'">
                  Chat & vibe, music optional
                </span>
              </button>
            </div>
          </div>

          <div>
            <label class="block text-sm text-slate-400 mb-2">Room Name</label>
            <input
              v-model="createForm.name"
              type="text"
              placeholder="Friday Vibes, Album Club, etc."
              class="input-base"
              autofocus
            />
          </div>

          <div class="flex items-center gap-3">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="createForm.isPublic"
                type="checkbox"
                class="w-4 h-4 rounded bg-white/10 border-white/20 text-accent-primary focus:ring-accent-primary"
              />
              <span class="text-sm">Public room</span>
            </label>
            <span class="text-xs text-slate-500">(visible in room list)</span>
          </div>

          <div>
            <label class="block text-sm text-slate-400 mb-2">Password (optional)</label>
            <input
              v-model="createForm.password"
              type="password"
              placeholder="Leave empty for open access"
              class="input-base"
            />
          </div>

          <div class="flex gap-3 pt-2">
            <button
              type="button"
              @click="closeCreateModal"
              class="flex-1 btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="!createForm.name.trim() || creating"
              class="flex-1 btn-primary flex items-center justify-center gap-2"
            >
              <Loader2 v-if="creating" class="w-4 h-4 animate-spin" />
              Create
            </button>
          </div>
        </form>
    </ModalDialog>

    <!-- Password Modal -->
    <ModalDialog v-if="showPasswordModal" max-width="max-w-sm" @close="closePasswordModal">
        <div class="flex items-center gap-3 mb-4">
          <Lock class="w-6 h-6 text-accent-primary" />
          <h2 class="text-xl font-heading font-semibold">Room Password</h2>
        </div>
        <p class="text-sm text-slate-400 mb-4">
          Enter the password for "{{ joiningRoom?.name }}"
        </p>

        <form @submit.prevent="submitPassword">
          <input
            v-model="passwordInput"
            type="password"
            placeholder="Enter password"
            class="input-base"
            autofocus
          />
          <p v-if="passwordError" class="text-red-400 text-sm mt-2">{{ passwordError }}</p>

          <div class="flex gap-3 mt-6">
            <button
              type="button"
              @click="closePasswordModal"
              class="flex-1 btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="!passwordInput"
              class="flex-1 btn-primary"
            >
              Join
            </button>
          </div>
        </form>
    </ModalDialog>

    <!-- Delete Room Confirmation -->
    <ConfirmModal
      v-if="deleteTarget"
      title="Delete room?"
      :message="`${deleteTarget.name} will be closed for everyone in it. This cannot be undone.`"
      confirm-label="Delete room"
      :busy="deleting"
      @confirm="confirmDeleteRoom"
      @close="deleteTarget = null"
    />
  </div>
</template>
