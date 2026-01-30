<script setup>
import { ref, onMounted, provide, computed } from 'vue'
import { RouterView, RouterLink } from 'vue-router'
import { Music2, User, ChevronDown, Plus, Lock, LogOut } from 'lucide-vue-next'

const users = ref([])
const currentUser = ref(null)
const isAdminVerified = ref(false)
const showUserMenu = ref(false)
const showPinModal = ref(false)
const showNewUserModal = ref(false)
const pinInput = ref('')
const pinError = ref('')
const newUserName = ref('')
const newUserError = ref('')

provide('currentUser', currentUser)
provide('users', users)
provide('isAdminVerified', isAdminVerified)

const isAdmin = computed(() => currentUser.value?.is_admin && isAdminVerified.value)

provide('isAdmin', isAdmin)

async function loadUsers() {
  const res = await fetch('/api/users')
  users.value = await res.json()

  // Restore user from localStorage
  const savedUserId = localStorage.getItem('currentUserId')
  if (savedUserId && !currentUser.value) {
    const user = users.value.find(u => u.id === parseInt(savedUserId))
    if (user) {
      currentUser.value = user
      // Don't auto-verify admin, they need to enter PIN again
    }
  }
}

function selectUser(user) {
  if (user.is_admin) {
    currentUser.value = user
    isAdminVerified.value = false
    showUserMenu.value = false
    showPinModal.value = true
  } else {
    currentUser.value = user
    isAdminVerified.value = false
    showUserMenu.value = false
  }
  // Save to localStorage
  localStorage.setItem('currentUserId', user.id.toString())
}

async function verifyPin() {
  pinError.value = ''
  try {
    const res = await fetch('/api/users/verify-pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUser.value.id,
        pin: pinInput.value
      })
    })
    if (res.ok) {
      isAdminVerified.value = true
      showPinModal.value = false
      pinInput.value = ''
    } else {
      pinError.value = 'Invalid PIN'
    }
  } catch (e) {
    pinError.value = 'Error verifying PIN'
  }
}

function cancelPin() {
  showPinModal.value = false
  pinInput.value = ''
  pinError.value = ''
  currentUser.value = null
}

function logout() {
  currentUser.value = null
  isAdminVerified.value = false
  showUserMenu.value = false
  localStorage.removeItem('currentUserId')
}

async function createUser() {
  newUserError.value = ''
  if (!newUserName.value.trim()) return

  try {
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newUserName.value.trim() })
    })
    if (res.ok) {
      const user = await res.json()
      users.value.push(user)
      currentUser.value = user
      localStorage.setItem('currentUserId', user.id.toString())
      showNewUserModal.value = false
      newUserName.value = ''
    } else {
      newUserError.value = 'Name already taken'
    }
  } catch (e) {
    newUserError.value = 'Error creating user'
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="min-h-screen text-slate-100">
    <!-- Navbar -->
    <nav class="fixed top-0 left-0 right-0 z-50 glass border-b border-white/10">
      <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <RouterLink to="/" class="flex items-center gap-2 text-xl font-heading font-semibold">
          <Music2 class="w-6 h-6 text-accent-primary" />
          <span class="hidden sm:inline">Album Ranker</span>
          <span class="sm:hidden">Albums</span>
        </RouterLink>

        <!-- User selector -->
        <div class="relative">
          <button
            @click="showUserMenu = !showUserMenu"
            class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg"
          >
            <User class="w-4 h-4 text-slate-400" />
            <span class="text-sm">
              {{ currentUser?.name || 'Select User' }}
              <Lock v-if="isAdmin" class="w-3 h-3 inline ml-1 text-accent-primary" />
            </span>
            <ChevronDown class="w-4 h-4 text-slate-400" />
          </button>

          <div
            v-if="showUserMenu"
            class="absolute right-0 mt-2 w-56 bg-bg-secondary border border-white/20 rounded-xl overflow-hidden shadow-2xl"
          >
            <div class="px-3 py-2 text-xs text-slate-500 border-b border-white/10">
              Select User
            </div>
            <button
              v-for="user in users"
              :key="user.id"
              @click="selectUser(user)"
              class="w-full px-4 py-2 text-left text-sm hover:bg-white/10 transition-colors flex items-center justify-between"
              :class="{ 'bg-white/10 text-accent-primary': currentUser?.id === user.id }"
            >
              <span>{{ user.name }}</span>
              <Lock v-if="user.is_admin" class="w-3 h-3 text-slate-500" />
            </button>

            <div class="border-t border-white/10">
              <button
                @click="showNewUserModal = true; showUserMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-white/10 transition-colors flex items-center gap-2 text-accent-primary"
              >
                <Plus class="w-4 h-4" />
                Create Account
              </button>
            </div>

            <div v-if="currentUser" class="border-t border-white/10">
              <button
                @click="logout"
                class="w-full px-4 py-2 text-left text-sm hover:bg-white/10 transition-colors flex items-center gap-2 text-slate-400"
              >
                <LogOut class="w-4 h-4" />
                Sign Out
              </button>
            </div>
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
    <main class="pt-20 pb-8 px-4">
      <div class="max-w-6xl mx-auto">
        <div v-if="!currentUser" class="text-center py-16">
          <User class="w-16 h-16 mx-auto mb-4 text-slate-600" />
          <h2 class="text-xl font-heading font-medium text-slate-400 mb-2">Welcome to Album Ranker</h2>
          <p class="text-slate-500 mb-6">Select a user or create an account to get started</p>
          <button
            @click="showNewUserModal = true"
            class="inline-flex items-center gap-2 px-6 py-3 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
          >
            <Plus class="w-5 h-5" />
            Create Account
          </button>
        </div>
        <RouterView v-else />
      </div>
    </main>

    <!-- PIN Modal -->
    <div
      v-if="showPinModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
    >
      <div class="glass p-6 w-full max-w-sm">
        <div class="flex items-center gap-3 mb-4">
          <Lock class="w-6 h-6 text-accent-primary" />
          <h2 class="text-xl font-heading font-semibold">Admin PIN</h2>
        </div>
        <p class="text-sm text-slate-400 mb-4">Enter PIN to access admin features</p>

        <form @submit.prevent="verifyPin">
          <input
            v-model="pinInput"
            type="password"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="4"
            placeholder="Enter 4-digit PIN"
            class="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-center text-2xl tracking-widest placeholder-slate-500 focus:outline-none focus:border-accent-primary transition-colors"
            autofocus
          />
          <p v-if="pinError" class="text-red-400 text-sm mt-2 text-center">{{ pinError }}</p>

          <div class="flex gap-3 mt-6">
            <button
              type="button"
              @click="cancelPin"
              class="flex-1 px-4 py-2 border border-white/20 rounded-xl hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="pinInput.length !== 4"
              class="flex-1 px-4 py-2 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors disabled:opacity-50"
            >
              Unlock
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- New User Modal -->
    <div
      v-if="showNewUserModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
      @click.self="showNewUserModal = false"
    >
      <div class="glass p-6 w-full max-w-sm">
        <h2 class="text-xl font-heading font-semibold mb-4">Create Account</h2>

        <form @submit.prevent="createUser">
          <input
            v-model="newUserName"
            type="text"
            placeholder="Your name"
            class="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-accent-primary transition-colors"
            autofocus
          />
          <p v-if="newUserError" class="text-red-400 text-sm mt-2">{{ newUserError }}</p>

          <div class="flex gap-3 mt-6">
            <button
              type="button"
              @click="showNewUserModal = false; newUserName = ''; newUserError = ''"
              class="flex-1 px-4 py-2 border border-white/20 rounded-xl hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="!newUserName.trim()"
              class="flex-1 px-4 py-2 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
