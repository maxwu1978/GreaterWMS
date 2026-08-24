<template>
  <q-page class="dashboard-page flex flex-top column q-pa-sm">
    <operations-board />
    <mail-task-board />
  </q-page>
</template>

<script>
import OperationsBoard from './operationsBoard.vue'
import MailTaskBoard from './mailTaskBoard.vue'

export default {
  name: 'Pagedashboard',
  components: {
    OperationsBoard,
    MailTaskBoard
  }
}
</script>
