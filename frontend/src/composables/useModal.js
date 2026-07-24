import { onMounted, onUnmounted } from 'vue'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Shared modal behavior: Escape to close, focus trap within the container,
 * and focus restore to the invoking element on close.
 *
 * @param {import('vue').Ref<HTMLElement|null>} containerRef - modal root element
 * @param {() => void} onClose - called on Escape
 */
export function useModal(containerRef, onClose) {
  let previouslyFocused = null

  function trapFocus(e) {
    const container = containerRef.value
    if (!container) return
    const focusable = [...container.querySelectorAll(FOCUSABLE)]
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    } else if (!container.contains(document.activeElement)) {
      e.preventDefault()
      first.focus()
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    } else if (e.key === 'Tab') {
      trapFocus(e)
    }
  }

  onMounted(() => {
    previouslyFocused = document.activeElement
    document.addEventListener('keydown', handleKeydown, true)
    // Focus the first focusable element inside the modal
    requestAnimationFrame(() => {
      const container = containerRef.value
      if (!container) return
      const autofocus = container.querySelector('[autofocus]')
      const target = autofocus || container.querySelector(FOCUSABLE)
      target?.focus()
    })
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown, true)
    if (previouslyFocused?.focus) previouslyFocused.focus()
  })
}
