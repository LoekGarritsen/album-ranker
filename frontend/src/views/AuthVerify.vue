<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Music2, AlertCircle } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const { verify } = useAuth()

const error = ref(false)

onMounted(async () => {
  const token = route.query.token
  if (!token) { error.value = true; return }
  const ok = await verify(token)
  if (ok) router.replace('/')
  else error.value = true
})
</script>

<template>
  <div class="max-w-sm mx-auto text-center py-24">
    <template v-if="!error">
      <Music2 class="w-12 h-12 mx-auto mb-4 text-accent-primary animate-pulse" />
      <p class="text-slate-400">Signing you in…</p>
    </template>
    <template v-else>
      <AlertCircle class="w-12 h-12 mx-auto mb-4 text-red-400" />
      <h2 class="text-xl font-heading font-semibold mb-2">Link invalid or expired</h2>
      <p class="text-slate-500 mb-6">Magic links work once and expire after 15 minutes.</p>
      <RouterLink to="/" class="btn-primary inline-block">Back to sign in</RouterLink>
    </template>
  </div>
</template>
