<script setup>
import { ref, onMounted } from 'vue'
import { ListMusic, Plus } from 'lucide-vue-next'

const lists = ref([])
const loading = ref(true)
const showCreate = ref(false)
const title = ref('')
const description = ref('')
const busy = ref(false)

async function load() {
  try {
    const res = await fetch('/api/lists')
    if (res.ok) lists.value = (await res.json()).lists
  } catch (e) {
    console.error('Failed to load lists:', e)
  }
  loading.value = false
}

async function createList() {
  if (!title.value.trim() || busy.value) return
  busy.value = true
  try {
    const res = await fetch('/api/lists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.value.trim(), description: description.value.trim() || null }),
    })
    if (res.ok) {
      title.value = ''
      description.value = ''
      showCreate.value = false
      await load()
    }
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <ListMusic class="w-8 h-8 text-accent-primary" />
        Lists
      </h1>
      <button @click="showCreate = !showCreate" class="btn-primary flex items-center gap-2">
        <Plus class="w-4 h-4" /> New list
      </button>
    </div>

    <form v-if="showCreate" @submit.prevent="createList" class="glass p-4 mb-6 space-y-3 max-w-xl">
      <input v-model="title" placeholder="List title (e.g. Best albums of the 90s)" class="input-base w-full" autofocus />
      <input v-model="description" placeholder="Description (optional)" class="input-base w-full" />
      <div class="flex gap-2">
        <button type="submit" :disabled="!title.trim() || busy" class="btn-primary">Create</button>
        <button type="button" @click="showCreate = false" class="btn-secondary">Cancel</button>
      </div>
    </form>

    <div v-if="loading" class="text-center py-12 text-text-subdued">Loading…</div>

    <div v-else-if="lists.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <RouterLink v-for="list in lists" :key="list.id" :to="`/lists/${list.id}`"
                  class="card-interactive rounded-lg p-4 block">
        <div class="grid grid-cols-2 gap-1 w-24 h-24 mb-3 rounded-md overflow-hidden bg-surface-highlight">
          <template v-if="list.covers.length">
            <img v-for="(cover, i) in list.covers" :key="i" :src="cover" class="w-full h-full object-cover"
                 :class="list.covers.length === 1 ? 'col-span-2 row-span-2' : ''" />
          </template>
          <div v-else class="col-span-2 row-span-2 flex items-center justify-center">
            <ListMusic class="w-8 h-8 text-text-subdued" />
          </div>
        </div>
        <p class="font-semibold truncate">{{ list.title }}</p>
        <p v-if="list.description" class="text-sm text-text-subdued truncate">{{ list.description }}</p>
        <p class="text-xs text-text-subdued mt-1">by {{ list.user_name }} · {{ list.item_count }} albums</p>
      </RouterLink>
    </div>

    <div v-else class="text-center py-16 text-text-subdued">
      <ListMusic class="w-12 h-12 mx-auto mb-3 opacity-40" />
      <p>No lists yet. Rank a discography, collect hidden gems — make the first one.</p>
    </div>
  </div>
</template>
