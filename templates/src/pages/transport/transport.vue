<template>
  <div class="q-pa-md transport-page">
    <div class="row items-center q-mb-sm">
      <div class="text-h6">Local Transport</div>
      <q-space />
      <q-btn flat round icon="refresh" :loading="loading" @click="load" />
    </div>
    <q-table
      flat
      bordered
      dense
      row-key="id"
      :data="rows"
      :columns="columns"
      :loading="loading"
      hide-bottom
      no-data-label="No transport orders"
    >
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="statusColor(props.row.status)">{{ props.row.status }}</q-badge>
        </q-td>
      </template>
    </q-table>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'TransportOrders',
  data () {
    return {
      loading: false,
      rows: [],
      columns: [
        { name: 'transport_no', label: 'Transport', field: 'transport_no', align: 'left' },
        { name: 'direction', label: 'Direction', field: 'direction', align: 'left' },
        { name: 'reference_no', label: 'Reference', field: 'reference_no', align: 'left' },
        { name: 'customer', label: 'Customer', field: 'customer', align: 'left' },
        { name: 'driver_name', label: 'Driver', field: 'driver_name', align: 'left' },
        { name: 'eta', label: 'ETA', field: 'eta', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'left' }
      ]
    }
  },
  mounted () {
    this.load()
  },
  methods: {
    load () {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth('transport/orders/')
        .then(response => { this.rows = response.results || [] })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    statusColor (status) {
      if (status === 'CANCELLED') return 'negative'
      if (status === 'COMPLETED') return 'positive'
      if (status === 'IN_TRANSIT') return 'primary'
      return 'grey-7'
    }
  }
}
</script>
