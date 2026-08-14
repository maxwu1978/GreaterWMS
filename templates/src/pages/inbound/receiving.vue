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
      <template v-slot:body-cell-putaway_driver="props">
        <q-td :props="props">
          <span>{{ props.row.putaway_driver || '-' }}</span>
          <q-btn
            v-if="props.row.status === 'PUTAWAY_PENDING'"
            flat
            dense
            color="primary"
            :label="props.row.putaway_driver ? 'Reassign' : 'Assign'"
            @click="openDriverDialog(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="driverDialog">
      <q-card style="min-width: 320px">
        <q-card-section class="text-h6">Assign Putaway Driver</q-card-section>
        <q-card-section>
          <q-select
            v-model="selectedDriver"
            outlined
            dense
            use-input
            fill-input
            hide-selected
            :options="driverOptions"
            label="Driver"
            @filter="filterDrivers"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn color="primary" label="Assign" :disable="!selectedDriver || assigning" :loading="assigning" @click="assignDriver" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { getauth, postauth } from 'boot/axios_request.js'

export default {
  name: 'PhysicalReceiving',
  data () {
    return {
      loading: false,
      rows: [],
      driverDialog: false,
      assigning: false,
      assignmentRow: null,
      selectedDriver: '',
      driverOptions: [],
      columns: [
        { name: 'receipt_no', label: 'Receipt', field: 'receipt_no', align: 'left' },
        { name: 'customer', label: 'Customer', field: 'customer', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'left' },
        { name: 'reconciliation_status', label: 'ASN Check', field: 'reconciliation_status', align: 'left' },
        { name: 'quantity', label: 'Qty', field: row => this.quantity(row), align: 'right' },
        { name: 'putaway_driver', label: 'Putaway Driver', field: 'putaway_driver', align: 'left' },
        { name: 'exception_note', label: 'Exception', field: 'exception_note', align: 'left' }
      ]
    }
  },
  mounted () {
    this.load()
  },
  watch: {
    '$route.query.receipt_no' () {
      this.load()
    }
  },
  methods: {
    load () {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      const receiptNo = this.$route.query && this.$route.query.receipt_no
      const path = receiptNo
        ? 'receiving/records/?receipt_no=' + encodeURIComponent(receiptNo)
        : 'receiving/records/'
      getauth(path)
        .then(response => { this.rows = response.results || [] })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    quantity (row) {
      return (row.details || []).reduce((total, detail) => total + Number(detail.actual_qty || 0), 0)
    },
    openDriverDialog (row) {
      this.assignmentRow = row
      this.selectedDriver = row.putaway_driver || ''
      this.driverDialog = true
      this.loadDrivers('')
    },
    loadDrivers (needle) {
      getauth('driver/?driver_name__icontains=' + encodeURIComponent(needle || ''))
        .then(response => {
          const rows = Array.isArray(response) ? response : (response.results || [])
          this.driverOptions = rows.map(item => item.driver_name).filter(Boolean)
        })
        .catch(() => {})
    },
    filterDrivers (value, update) {
      update(() => this.loadDrivers(value))
    },
    assignDriver () {
      if (!this.assignmentRow || !this.selectedDriver) return
      this.assigning = true
      postauth('receiving/putaway/assign/', {
        receipt_no: this.assignmentRow.receipt_no,
        driver_name: this.selectedDriver
      })
        .then(() => {
          this.driverDialog = false
          this.load()
        })
        .catch(() => {})
        .finally(() => { this.assigning = false })
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
