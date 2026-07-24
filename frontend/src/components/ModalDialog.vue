<script setup>
import { ref } from 'vue'
import { useModal } from '../composables/useModal'

defineProps({
  maxWidth: { type: String, default: 'max-w-md' }
})

const emit = defineEmits(['close'])

const container = ref(null)
useModal(container, () => emit('close'))
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
    @click.self="emit('close')"
    role="dialog"
    aria-modal="true"
  >
    <div ref="container" class="glass p-6 w-full" :class="maxWidth">
      <slot />
    </div>
  </div>
</template>
