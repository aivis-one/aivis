import { ref, computed } from 'vue'

export function usePagination(initialPerPage = 10) {
  const page = ref(1)
  const perPage = ref(initialPerPage)
  const total = ref(0)

  const totalPages = computed(() => Math.ceil(total.value / perPage.value))
  const hasNext = computed(() => page.value < totalPages.value)
  const hasPrev = computed(() => page.value > 1)

  function next() {
    if (hasNext.value) page.value++
  }

  function prev() {
    if (hasPrev.value) page.value--
  }

  function goTo(p: number) {
    if (p >= 1 && p <= totalPages.value) page.value = p
  }

  function setTotal(t: number) {
    total.value = t
  }

  function reset() {
    page.value = 1
    total.value = 0
  }

  return { page, perPage, total, totalPages, hasNext, hasPrev, next, prev, goTo, setTotal, reset }
}
