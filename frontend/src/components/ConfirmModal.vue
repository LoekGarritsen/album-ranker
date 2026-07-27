<script setup>
import { AlertTriangle, Loader2 } from 'lucide-vue-next'
import ModalDialog from './ModalDialog.vue'

defineProps({
  title: { type: String, required: true },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Delete' },
  busy: { type: Boolean, default: false }
})

const emit = defineEmits(['confirm', 'close'])
</script>

<template>
  <ModalDialog max-width="max-w-sm" @close="emit('close')">
    <div class="flex items-center gap-3 mb-3">
      <div class="w-10 h-10 bg-red-500/15 rounded-full flex items-center justify-center flex-shrink-0">
        <AlertTriangle class="w-5 h-5 text-red-400" />
      </div>
      <h2 class="text-lg font-heading font-semibold">{{ title }}</h2>
    </div>
    <p v-if="message" class="text-sm text-text-subdued mb-6">{{ message }}</p>

    <div class="flex gap-3">
      <button type="button" @click="emit('close')" class="flex-1 btn-secondary">
        Cancel
      </button>
      <button
        type="button"
        @click="emit('confirm')"
        :disabled="busy"
        class="flex-1 px-4 py-2 bg-red-500 text-white font-bold rounded-full hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
      >
        <Loader2 v-if="busy" class="w-4 h-4 animate-spin" />
        {{ confirmLabel }}
      </button>
    </div>
  </ModalDialog>
</template>
