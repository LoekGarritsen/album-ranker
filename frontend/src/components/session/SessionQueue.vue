<script setup>
import { ListMusic, Plus, X, SkipForward, Music, Disc3, ThumbsUp, ThumbsDown } from 'lucide-vue-next'

const props = defineProps({
  queue: { type: Array, default: () => [] },
  currentUserId: { type: [Number, String], default: null },
  // Room creator/admin can remove anyone's items
  canModerate: { type: Boolean, default: false }
})

const emit = defineEmits(['add', 'remove', 'skip', 'vote'])

function canRemove(item) {
  return props.canModerate || item.added_by === props.currentUserId
}

function myVote(item) {
  return item.votes?.find(v => v.user_id === props.currentUserId)?.vote || 0
}

function formatDuration(ms) {
  if (!ms) return ''
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="glass overflow-hidden">
    <div class="flex items-center gap-3 p-4 border-b border-white/10">
      <ListMusic class="w-5 h-5 text-accent-primary" />
      <span class="font-medium">Up Next</span>
      <span class="text-sm text-slate-400">({{ queue.length }})</span>
      <div class="ml-auto flex items-center gap-1">
        <button
          v-if="queue.length"
          @click="emit('skip')"
          class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors min-h-[36px] min-w-[36px] flex items-center justify-center"
          title="Skip to next in queue"
          aria-label="Skip to next in queue"
        >
          <SkipForward class="w-4 h-4" />
        </button>
        <button
          @click="emit('add')"
          class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors min-h-[36px] min-w-[36px] flex items-center justify-center"
          title="Add to queue"
          aria-label="Add to queue"
        >
          <Plus class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div v-if="!queue.length" class="p-5 text-center">
      <p class="text-sm text-slate-500">
        Queue is empty — anyone can add songs
      </p>
      <button
        @click="emit('add')"
        class="mt-3 inline-flex items-center gap-2 px-4 py-2 glass glass-hover rounded-lg text-sm min-h-[40px]"
      >
        <Plus class="w-4 h-4" />
        Add a song
      </button>
    </div>

    <ul v-else class="max-h-80 overflow-y-auto divide-y divide-white/5">
      <li
        v-for="(item, idx) in queue"
        :key="item.id"
        class="flex items-center gap-3 p-3"
      >
        <span class="text-xs text-slate-500 tabular-nums w-4 text-right flex-shrink-0">{{ idx + 1 }}</span>
        <div class="relative flex-shrink-0">
          <img
            v-if="item.image"
            :src="item.image"
            :alt="item.name"
            class="w-10 h-10 rounded-lg object-cover bg-white/10"
          />
          <div v-else class="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
            <component :is="item.type === 'album' ? Disc3 : Music" class="w-4 h-4 text-slate-500" />
          </div>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium truncate">{{ item.name }}</p>
          <p class="text-xs text-slate-400 truncate">
            {{ item.artist }}<span v-if="item.type === 'album'"> · Album</span>
            <span v-if="item.duration_ms" class="text-slate-500"> · {{ formatDuration(item.duration_ms) }}</span>
          </p>
          <p class="text-xs text-slate-500 truncate">added by {{ item.added_by_name }}</p>
        </div>

        <!-- Like/dislike: net score reorders the queue (best plays next) -->
        <div class="flex items-center gap-0.5 flex-shrink-0">
          <button
            @click="emit('vote', item.id, 'up')"
            class="flex items-center gap-1 px-1.5 py-1 rounded-lg text-xs transition-colors"
            :class="myVote(item) === 1 ? 'text-green-400 bg-green-400/10' : 'text-slate-500 hover:text-green-400 hover:bg-white/10'"
            :aria-label="`Like ${item.name}`"
            :aria-pressed="myVote(item) === 1"
          >
            <ThumbsUp class="w-3.5 h-3.5" />
            <span v-if="item.likes" class="tabular-nums">{{ item.likes }}</span>
          </button>
          <button
            @click="emit('vote', item.id, 'down')"
            class="flex items-center gap-1 px-1.5 py-1 rounded-lg text-xs transition-colors"
            :class="myVote(item) === -1 ? 'text-red-400 bg-red-400/10' : 'text-slate-500 hover:text-red-400 hover:bg-white/10'"
            :aria-label="`Dislike ${item.name}`"
            :aria-pressed="myVote(item) === -1"
          >
            <ThumbsDown class="w-3.5 h-3.5" />
            <span v-if="item.dislikes" class="tabular-nums">{{ item.dislikes }}</span>
          </button>
        </div>

        <button
          v-if="canRemove(item)"
          @click="emit('remove', item.id)"
          class="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-white/10 transition-colors flex-shrink-0"
          :title="`Remove ${item.name}`"
          :aria-label="`Remove ${item.name} from queue`"
        >
          <X class="w-4 h-4" />
        </button>
      </li>
    </ul>
  </div>
</template>
