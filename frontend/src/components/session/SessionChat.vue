<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { MessageCircle, Send, ArrowDown, SmilePlus, Loader2 } from 'lucide-vue-next'
import { useSession } from '../../composables/useSession'

const props = defineProps({
  currentUser: { type: Object, default: null },
  tall: { type: Boolean, default: false }
})

const {
  chatMessages,
  chatHasMore,
  typingUsers,
  sendChatMessage,
  sendTyping,
  toggleReaction,
  loadOlderChat
} = useSession()

const REACTION_SET = ['🔥', '❤️', '😂', '👍', '🎵', '😮']

const input = ref('')
const scrollEl = ref(null)
const isAtBottom = ref(true)
const newMessageCount = ref(0)
const loadingOlder = ref(false)
const reactionPickerFor = ref(null) // message id with open picker
let prepending = false // suppress new-message pill while loading history upward

const canChat = computed(() => !!props.currentUser?.id)

// Group consecutive messages from the same sender within 5 minutes; insert a
// time divider when the gap to the previous message exceeds 30 minutes.
const groupedMessages = computed(() => {
  const items = []
  let prev = null
  for (const m of chatMessages.value) {
    const ts = new Date(m.created_at).getTime()
    const prevTs = prev ? new Date(prev.created_at).getTime() : 0
    if (!prev || ts - prevTs > 30 * 60 * 1000) {
      items.push({ kind: 'divider', key: `div-${m.id ?? m.client_id}`, ts })
    }
    const newGroup = !prev
      || prev.user_id !== m.user_id
      || ts - prevTs > 5 * 60 * 1000
    items.push({ kind: 'message', key: m.id ?? m.client_id, message: m, showHeader: newGroup })
    prev = m
  }
  return items
})

const typingLabel = computed(() => {
  const names = typingUsers.value.map(u => u.user_name?.split(' ')[0] || 'Someone')
  if (!names.length) return ''
  if (names.length === 1) return `${names[0]} is typing…`
  if (names.length === 2) return `${names[0]} and ${names[1]} are typing…`
  return `${names.length} people are typing…`
})

function isMine(m) {
  return m.user_id === props.currentUser?.id
}

function formatTime(iso) {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatDivider(ts) {
  const d = new Date(ts)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return sameDay ? time : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`
}

// Aggregate reactions into chips: emoji + count, highlighted if mine
function reactionChips(m) {
  const map = new Map()
  for (const r of m.reactions || []) {
    const chip = map.get(r.emoji) || { emoji: r.emoji, count: 0, mine: false, names: [] }
    chip.count++
    chip.names.push(r.user_name?.split(' ')[0])
    if (r.user_id === props.currentUser?.id) chip.mine = true
    map.set(r.emoji, chip)
  }
  return [...map.values()]
}

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  isAtBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 150
  if (isAtBottom.value) newMessageCount.value = 0
}

function scrollToBottom(smooth = true) {
  nextTick(() => {
    const el = scrollEl.value
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
    newMessageCount.value = 0
  })
}

// Stick to bottom for new messages; when scrolled up reading history, show a
// "new messages" pill instead of yanking the view down.
watch(() => chatMessages.value.length, (len, oldLen) => {
  if (len <= oldLen || prepending) return
  const last = chatMessages.value[len - 1]
  if (isMine(last) || isAtBottom.value) {
    scrollToBottom()
  } else {
    newMessageCount.value += len - oldLen
  }
})

async function handleLoadOlder() {
  const el = scrollEl.value
  if (!el || loadingOlder.value) return
  loadingOlder.value = true
  prepending = true
  const prevHeight = el.scrollHeight
  await loadOlderChat()
  // Preserve the scroll anchor after prepending older messages
  await nextTick()
  el.scrollTop += el.scrollHeight - prevHeight
  prepending = false
  loadingOlder.value = false
}

function handleSend() {
  if (sendChatMessage(input.value)) {
    input.value = ''
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function handleReaction(m, emoji) {
  reactionPickerFor.value = null
  if (m.id) toggleReaction(m.id, emoji)
}

onMounted(() => scrollToBottom(false))
</script>

<template>
  <div class="flex flex-col" :class="tall ? 'h-[60vh] min-h-[24rem]' : 'h-96'">
    <!-- Messages -->
    <div ref="scrollEl" @scroll="onScroll" class="relative flex-1 overflow-y-auto px-3 sm:px-4 py-3 space-y-0.5">
      <div v-if="chatHasMore" class="text-center pb-2">
        <button
          @click="handleLoadOlder"
          :disabled="loadingOlder"
          class="inline-flex items-center gap-2 px-3 py-1.5 text-xs text-slate-400 bg-white/5 hover:bg-white/10 rounded-full transition-colors"
        >
          <Loader2 v-if="loadingOlder" class="w-3 h-3 animate-spin" />
          Load earlier messages
        </button>
      </div>

      <div v-if="!chatMessages.length" class="h-full flex flex-col items-center justify-center text-center py-8">
        <MessageCircle class="w-10 h-10 text-slate-600 mb-3" />
        <p class="text-slate-500 text-sm">No messages yet — say hi!</p>
      </div>

      <template v-for="item in groupedMessages" :key="item.key">
        <!-- Time divider -->
        <div v-if="item.kind === 'divider'" class="flex items-center gap-3 py-2">
          <div class="flex-1 h-px bg-white/10"></div>
          <span class="text-[10px] text-slate-500 uppercase tracking-wider">{{ formatDivider(item.ts) }}</span>
          <div class="flex-1 h-px bg-white/10"></div>
        </div>

        <!-- Message -->
        <div v-else class="group relative" :class="item.showHeader ? 'mt-2' : ''">
          <div v-if="item.showHeader" class="flex items-baseline gap-2 mb-0.5">
            <span class="text-sm font-medium" :class="isMine(item.message) ? 'text-accent-primary' : 'text-slate-200'">
              {{ item.message.user_name }}
            </span>
            <span class="text-[10px] text-slate-500">{{ formatTime(item.message.created_at) }}</span>
          </div>
          <div class="flex items-start gap-2">
            <p
              class="text-sm text-slate-300 whitespace-pre-wrap break-words flex-1 min-w-0"
              :class="{ 'opacity-50': item.message.pending }"
            >{{ item.message.content }}</p>
            <!-- Reaction trigger (appears on hover / always tappable on touch) -->
            <button
              v-if="canChat && item.message.id"
              @click="reactionPickerFor = reactionPickerFor === item.message.id ? null : item.message.id"
              class="p-1 rounded-md text-slate-500 hover:text-slate-300 hover:bg-white/10 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity flex-shrink-0"
              aria-label="Add reaction"
            >
              <SmilePlus class="w-4 h-4" />
            </button>
          </div>

          <!-- Reaction picker -->
          <div
            v-if="reactionPickerFor === item.message.id"
            class="absolute right-0 z-10 flex gap-1 p-1.5 rounded-xl bg-slate-800 border border-white/10 shadow-xl"
          >
            <button
              v-for="emoji in REACTION_SET"
              :key="emoji"
              @click="handleReaction(item.message, emoji)"
              class="w-8 h-8 flex items-center justify-center text-lg hover:bg-white/10 rounded-lg transition-colors"
            >{{ emoji }}</button>
          </div>

          <!-- Reaction chips -->
          <div v-if="reactionChips(item.message).length" class="flex flex-wrap gap-1 mt-1">
            <button
              v-for="chip in reactionChips(item.message)"
              :key="chip.emoji"
              @click="canChat && handleReaction(item.message, chip.emoji)"
              class="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border transition-colors"
              :class="chip.mine
                ? 'bg-accent-primary/20 border-accent-primary/50 text-accent-primary'
                : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'"
              :title="chip.names.join(', ')"
            >
              <span>{{ chip.emoji }}</span>
              <span>{{ chip.count }}</span>
            </button>
          </div>
        </div>
      </template>

      <!-- New messages pill -->
      <button
        v-if="newMessageCount > 0"
        @click="scrollToBottom()"
        class="sticky bottom-1 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 bg-accent-primary text-black text-xs font-medium rounded-full shadow-lg"
      >
        <ArrowDown class="w-3 h-3" />
        {{ newMessageCount }} new {{ newMessageCount === 1 ? 'message' : 'messages' }}
      </button>
    </div>

    <!-- Typing indicator -->
    <div class="h-5 px-4 text-xs text-slate-500 italic">
      <span v-if="typingLabel" class="animate-pulse">{{ typingLabel }}</span>
    </div>

    <!-- Input -->
    <div class="p-3 border-t border-white/10">
      <form v-if="canChat" @submit.prevent="handleSend" class="flex items-end gap-2">
        <textarea
          v-model="input"
          @keydown="handleKeydown"
          @input="input.trim() && sendTyping()"
          rows="1"
          maxlength="1000"
          placeholder="Send a message…"
          class="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent-primary/50 resize-none"
        ></textarea>
        <button
          type="submit"
          :disabled="!input.trim()"
          class="p-2.5 bg-accent-primary text-black rounded-xl hover:bg-accent-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Send message"
        >
          <Send class="w-4 h-4" />
        </button>
      </form>
      <p v-else class="text-center text-sm text-slate-500 py-2">Sign in to join the chat</p>
    </div>
  </div>
</template>
