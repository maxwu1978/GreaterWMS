<template>
  <div class="q-pa-md receiving-page">
    <div class="row items-center q-mb-sm">
      <div class="text-h6">Physical Receiving</div>
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
      no-data-label="No receiving records"
    >
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="statusColor(props.row.status)">{{ props.row.status }}</q-badge>
        </q-td>
      </template>
      <template v-slot:body-cell-reconciliation_status="props">
        <q-td :props="props">{{ props.row.reconciliation_status }}</q-td>
      </template>
      <template v-slot:body-cell-quantity="props">
        <q-td :props="props">{{ quantity(props.row) }}</q-td>
      </template>
    </q-table>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'PhysicalReceiving',
  data () {
    return {
      loading: false,
      rows: [],
      columns: [
        { name: 'receipt_no', label: 'Receipt', field: 'receipt_no', align: 'left' },
        { name: 'customer', label: 'Customer', field: 'customer', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'left' },
        { name: 'reconciliation_status', label: 'ASN Check', field: 'reconciliation_status', align: 'left' },
        { name: 'quantity', label: 'Qty', field: row => this.quantity(row), align: 'right' },
        { name: 'exception_note', label: 'Exception', field: 'exception_note', align: 'left' }
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
      getauth('receiving/records/')
        .then(response => { this.rows = response.results || [] })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    quantity (row) {
      return (row.details || []).reduce((total, detail) => total + Number(detail.actual_qty || 0), 0)
    },
    statusColor (status) {
      if (status === 'QC_EXCEPTION') return 'negative'
      if (status === 'CLOSED') return 'positive'
      if (status === 'PUTAWAY_PENDING') return 'primary'
      return 'grey-7'
    }
  }
}
</script>
