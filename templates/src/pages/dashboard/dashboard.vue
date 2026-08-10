<template>
  <q-page class="flex flex-top column q-pa-sm">
    <operations-board />
  </q-page>
</template>

<script>
import OperationsBoard from './operationsBoard.vue'

export default {
  name: 'Pagedashboard',
  components: {
    OperationsBoard
  }
}
</script>
