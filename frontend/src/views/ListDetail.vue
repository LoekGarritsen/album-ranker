<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Plus, Trash2, GripVertical, X } from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const route = useRoute()
const router = useRouter()
const currentUser = inject('currentUser')
const isAdmin = inject('isAdmin')
const { showToast } = useSession()

const list = ref(null)
const loading = ref(true)
const albums = ref([])
const showAdd = ref(false)
const filter = ref('')
const dragIndex = ref(null)

const isOwner = computed(() =>
  list.value && (list.value.user_id === currentUser.value?.id || isAdmin.value)
)

const availableAlbums = computed(() => {
  const inList = new Set((list.value?.items || []).map(i => i.album_id))
  const q = filter.value.toLowerCase()
  return albums.value
    .filter(a => !inList.has(a.id))
    .filter(a => !q || a.name.toLowerCase().includes(q) || a.artist.toLowerCase().includes(q))
})

async function load() {
  try {
    const res = await fetch(`/api/lists/${route.params.id}`)
    if (res.ok) list.value = await res.json()
  } catch (e) {
    console.error('Failed to load list:', e)
  }
  loading.value = false
}

async function loadAlbums() {
  try {
    const res = await fetch('/api/albums')
    if (res.ok) albums.value = await res.json()
  } catch {}
}

async function addAlbum(album) {
  const res = await fetch(`/api/lists/${list.value.id}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ album_id: album.id }),
  })
  if (res.ok) await load()
}

async function removeItem(item) {
  const res = await fetch(`/api/lists/${list.value.id}/items/${item.id}`, { method: 'DELETE' })
  if (res.ok) await load()
}

async function deleteList() {
  if (!confirm(`Delete "${list.value.title}"?`)) return
  const res = await fetch(`/api/lists/${list.value.id}`, { method: 'DELETE' })
  if (res.ok) {
    showToast('List deleted', 'success')
    router.push('/lists')
  }
}

function onDragStart(index) { dragIndex.value = index }

async function onDrop(index) {
  if (dragIndex.value === null || dragIndex.value === index) return
  const items = [...list.value.items]
  const [moved] = items.splice(dragIndex.value, 1)
  items.splice(index, 0, moved)
  list.value.items = items
  dragIndex.value = null
  await fetch(`/api/lists/${list.value.id}/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_ids: items.map(i => i.id) }),
  })
}

onMounted(() => { load(); loadAlbums() })
</script>

<template>
  <div>
    <RouterLink to="/lists" class="inline-flex items-center gap-1.5 text-sm text-text-subdued hover:text-white mb-4">
      <ArrowLeft class="w-4 h-4" /> All lists
    </RouterLink>

    <div v-if="loading" class="text-center py-12 text-text-subdued">Loading…</div>

    <template v-else-if="list">
      <div class="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 class="text-3xl font-heading font-bold">{{ list.title }}</h1>
          <p v-if="list.description" class="text-text-subdued mt-1">{{ list.description }}</p>
          <p class="text-xs text-text-subdued mt-1">by {{ list.user_name }} · {{ list.items.length }} albums</p>
        </div>
        <div v-if="isOwner" class="flex gap-2">
          <button @click="showAdd = !showAdd" class="btn-primary flex items-center gap-2">
            <Plus class="w-4 h-4" /> Add albums
          </button>
          <button @click="deleteList" class="btn-ghost text-red-400" title="Delete list">
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Add from library -->
      <div v-if="showAdd && isOwner" class="glass p-4 mb-6">
        <div class="flex items-center gap-2 mb-3">
          <input v-model="filter" placeholder="Filter library…" class="input-base flex-1" />
          <button @click="showAdd = false" class="btn-ghost"><X class="w-4 h-4" /></button>
        </div>
        <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2 max-h-72 overflow-y-auto">
          <button v-for="album in availableAlbums" :key="album.id" @click="addAlbum(album)"
                  class="text-left card-interactive rounded-lg p-1.5">
            <img :src="album.cover_url || '/placeholder.svg'" class="w-full aspect-square rounded object-cover bg-surface-highlight mb-1" />
            <p class="text-[11px] truncate">{{ album.name }}</p>
          </button>
        </div>
        <p v-if="!availableAlbums.length" class="text-sm text-text-subdued text-center py-4">Nothing left to add.</p>
      </div>

      <!-- Items (drag to reorder for owners) -->
      <div v-if="list.items.length" class="space-y-2">
        <div v-for="(item, index) in list.items" :key="item.id"
             class="glass p-2.5 flex items-center gap-3"
             :draggable="isOwner"
             @dragstart="onDragStart(index)"
             @dragover.prevent
             @drop="onDrop(index)">
          <GripVertical v-if="isOwner" class="w-4 h-4 text-text-subdued cursor-grab shrink-0" />
          <span class="w-6 text-center font-heading font-bold text-text-subdued shrink-0">{{ index + 1 }}</span>
          <img :src="item.cover_url || '/placeholder.svg'" class="w-11 h-11 rounded object-cover bg-surface-highlight shrink-0" />
          <div class="min-w-0 flex-1">
            <p class="truncate">{{ item.name }}</p>
            <p class="text-xs text-text-subdued truncate">{{ item.artist }}<span v-if="item.note"> — {{ item.note }}</span></p>
          </div>
          <span v-if="item.average_score" class="text-sm font-heading font-bold text-accent-primary shrink-0">
            {{ item.average_score }}
          </span>
          <button v-if="isOwner" @click="removeItem(item)" class="p-1.5 text-text-subdued hover:text-red-400 shrink-0">
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>
      <div v-else class="text-center py-12 text-text-subdued">Empty list — add albums from the library.</div>
    </template>

    <div v-else class="text-center py-12 text-text-subdued">List not found.</div>
  </div>
</template>
